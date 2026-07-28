"""The full-duplex-ish voice endpoint.

Protocol (``/ws/voice/{business_id}``)

  client -> server
    binary frames                  encoded audio (webm/opus) for the current turn
    {"type": "end_of_turn"}        the customer stopped speaking; transcribe now
    {"type": "text", "text": ...}  typed fallback, skips STT
    {"type": "cancel"}             barge-in: stop speaking immediately

  server -> client
    {"type": "ready", "conversationId": ..., "greeting": ..., "sampleRate": n}
    {"type": "transcript", "text": ...}
    {"type": "reply", "text": ..., "intent": ..., "outcome": ...}
    {"type": "speech_start", "sampleRate": n}
    binary frames                  PCM16 mono audio
    {"type": "speech_end"}
    {"type": "error", "message": ...}

Turns are delimited by the client's silence detector rather than by streaming
partial transcripts, because CPU Whisper cannot keep up with true streaming on
a free-tier instance. Barge-in is supported: audio arriving while the assistant
is speaking cancels synthesis.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.agents.graph import get_or_create_conversation, run_turn
from app.db import SessionLocal
from app.models import Booking, Business, Conversation
from app.services import stt, tts
from app.services.notifications import send_booking_confirmation

logger = logging.getLogger(__name__)

router = APIRouter(tags=["voice"])

MAX_TURN_AUDIO_BYTES = 8 * 1024 * 1024  # ~5 minutes of opus; a generous ceiling
MAX_SESSION_SECONDS = 15 * 60
PCM_FRAME_BYTES = 8192


class VoiceSession:
    def __init__(self, websocket: WebSocket, business: Business) -> None:
        self.websocket = websocket
        self.business = business
        self.buffer = bytearray()
        self.speaking_task: asyncio.Task[None] | None = None
        self.conversation_id: uuid.UUID | None = None

    async def cancel_speech(self) -> None:
        """Barge-in: stop mid-sentence when the customer starts talking."""
        task = self.speaking_task
        if task is not None and not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        self.speaking_task = None

    async def speak(self, text: str) -> None:
        if not text.strip() or not tts.is_available():
            return
        await self.cancel_speech()
        self.speaking_task = asyncio.create_task(self._speak_impl(text))

    async def _speak_impl(self, text: str) -> None:
        try:
            await self.websocket.send_json(
                {"type": "speech_start", "sampleRate": tts.sample_rate()}
            )
            async for audio in tts.stream_sentences(text):
                for offset in range(0, len(audio), PCM_FRAME_BYTES):
                    await self.websocket.send_bytes(audio[offset : offset + PCM_FRAME_BYTES])
            await self.websocket.send_json({"type": "speech_end"})
        except asyncio.CancelledError:
            with contextlib.suppress(Exception):
                await self.websocket.send_json({"type": "speech_end", "cancelled": True})
            raise
        except (WebSocketDisconnect, RuntimeError):
            pass
        except Exception:
            logger.exception("Speech synthesis failed.")
            with contextlib.suppress(Exception):
                await self.websocket.send_json({"type": "speech_end"})


@router.websocket("/ws/voice/{business_id}")
async def voice_socket(websocket: WebSocket, business_id: uuid.UUID) -> None:
    await websocket.accept()

    async with SessionLocal() as session:
        business = await session.get(Business, business_id)
        if business is None:
            await websocket.send_json({"type": "error", "message": "Business not found."})
            await websocket.close(code=4404)
            return

        conversation = await get_or_create_conversation(session, business, None, channel="voice")
        await session.commit()
        conversation_id = conversation.id
        greeting = business.greeting

    voice = VoiceSession(websocket, business)
    voice.conversation_id = conversation_id

    await websocket.send_json(
        {
            "type": "ready",
            "conversationId": str(conversation_id),
            "greeting": greeting,
            "sampleRate": tts.sample_rate(),
            "sttAvailable": stt.is_available(),
            "ttsAvailable": tts.is_available(),
        }
    )
    await voice.speak(greeting)

    try:
        await asyncio.wait_for(_receive_loop(websocket, voice), timeout=MAX_SESSION_SECONDS)
    except TimeoutError:
        with contextlib.suppress(Exception):
            await websocket.send_json({"type": "error", "message": "Session time limit reached."})
            await websocket.close(code=4408)
    except WebSocketDisconnect:
        pass
    finally:
        await voice.cancel_speech()
        await _close_conversation(conversation_id)


async def _receive_loop(websocket: WebSocket, voice: VoiceSession) -> None:
    while True:
        message = await websocket.receive()

        if message["type"] == "websocket.disconnect":
            raise WebSocketDisconnect(message.get("code", 1000))

        if (data := message.get("bytes")) is not None:
            # Any incoming audio means the customer is talking over us.
            await voice.cancel_speech()
            if len(voice.buffer) + len(data) > MAX_TURN_AUDIO_BYTES:
                await websocket.send_json(
                    {"type": "error", "message": "That turn was too long. Please try again."}
                )
                voice.buffer.clear()
                continue
            voice.buffer.extend(data)
            continue

        raw = message.get("text")
        if raw is None:
            continue

        try:
            payload = json.loads(raw)
        except ValueError:
            continue

        kind = payload.get("type")

        if kind == "cancel":
            await voice.cancel_speech()

        elif kind == "text":
            text = str(payload.get("text", "")).strip()[:2000]
            if text:
                await _handle_turn(voice, text)

        elif kind == "end_of_turn":
            audio = bytes(voice.buffer)
            voice.buffer.clear()
            if not audio:
                continue
            if not stt.is_available():
                await websocket.send_json(
                    {
                        "type": "error",
                        "message": (
                            "Speech recognition is not installed on the server. "
                            "Use the text box instead."
                        ),
                    }
                )
                continue
            try:
                transcript = await stt.transcribe(audio, suffix=".webm")
            except Exception:
                await websocket.send_json(
                    {"type": "error", "message": "Sorry, I couldn't hear that clearly."}
                )
                continue
            if not transcript:
                continue
            await websocket.send_json({"type": "transcript", "text": transcript})
            await _handle_turn(voice, transcript)


async def _handle_turn(voice: VoiceSession, text: str) -> None:
    """Run one turn through the graph in its own transaction."""
    async with SessionLocal() as session:
        business = await session.get(Business, voice.business.id)
        conversation = await session.get(Conversation, voice.conversation_id)
        if business is None or conversation is None:
            return

        try:
            result = await run_turn(session, business, conversation, text)
            await session.commit()
        except Exception:
            await session.rollback()
            logger.exception("Voice turn failed.")
            await voice.websocket.send_json(
                {"type": "error", "message": "Something went wrong. Could you say that again?"}
            )
            return

        booking_id = result.booking_id

    await voice.websocket.send_json(
        {
            "type": "reply",
            "text": result.reply,
            "intent": result.intent,
            "outcome": result.outcome,
            "sources": result.sources,
        }
    )
    await voice.speak(result.reply)

    if booking_id is not None:
        asyncio.create_task(_send_confirmation(booking_id))


async def _send_confirmation(booking_id: uuid.UUID) -> None:
    try:
        async with SessionLocal() as session:
            booking = await session.get(Booking, booking_id)
            if booking is None or not booking.customer_email:
                return
            business = await session.get(Business, booking.business_id)
            if business is not None:
                await send_booking_confirmation(booking, business)
    except Exception:
        logger.exception("Confirmation email task failed for booking %s", booking_id)


async def _close_conversation(conversation_id: uuid.UUID) -> None:
    try:
        async with SessionLocal() as session:
            conversation = await session.get(Conversation, conversation_id)
            if conversation is not None and conversation.ended_at is None:
                conversation.ended_at = datetime.now(UTC)
                if conversation.outcome == "in_progress":
                    conversation.outcome = "abandoned"
                await session.commit()
    except Exception:
        logger.exception("Could not close conversation %s", conversation_id)
