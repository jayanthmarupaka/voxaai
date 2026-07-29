"""Exercise the voice websocket end to end without a browser or a microphone.

    python -m scripts.voice_smoke <business-id>

Two things are proven here that the text REPL cannot prove:
  1. the server speaks   — a typed turn comes back as PCM audio from Piper
  2. the server listens  — that same audio, fed back in as a turn, is
                           transcribed by Whisper and answered

Round-tripping our own TTS through STT is a cheap way to test the microphone
path on a machine with no microphone.
"""

from __future__ import annotations

import argparse
import asyncio
import io
import json
import sys
import wave
from pathlib import Path

import websockets

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

QUESTION = "How much is a hygienist appointment?"


async def collect_reply(ws) -> tuple[dict, bytes]:
    """Read messages until speech_end, returning the reply and its audio."""
    reply: dict = {}
    audio = bytearray()
    transcript: str | None = None
    while True:
        message = await asyncio.wait_for(ws.recv(), timeout=120)
        if isinstance(message, bytes):
            audio.extend(message)
            continue
        event = json.loads(message)
        kind = event.get("type")
        if kind == "transcript":
            transcript = event.get("text")
            print(f"  transcript : {transcript!r}")
        elif kind == "reply":
            reply = event
            print(f"  reply      : {event.get('text')!r}")
            print(f"  routed to  : {event.get('intent')} -> {event.get('outcome')}")
        elif kind == "error":
            print(f"  ERROR      : {event.get('message')}")
            return event, bytes(audio)
        elif kind == "speech_end":
            break
    reply["transcript"] = transcript
    return reply, bytes(audio)


def to_wav(pcm: bytes, sample_rate: int) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(pcm)
    return buffer.getvalue()


async def main(business_id: str, host: str) -> int:
    url = f"ws://{host}/ws/voice/{business_id}"
    async with websockets.connect(url, max_size=16 * 1024 * 1024) as ws:
        ready = json.loads(await asyncio.wait_for(ws.recv(), timeout=30))
        if ready.get("type") != "ready":
            print(f"unexpected first message: {ready}")
            return 1
        sample_rate = ready.get("sampleRate") or 22050
        print(f"connected — conversation {ready['conversationId']}, {sample_rate} Hz")
        print(f"greeting: {ready['greeting']}\n")

        # The server speaks the greeting as soon as the socket opens, so drain
        # that audio before the first turn or every reply is off by one.
        print("[0] greeting spoken on connect")
        _, greeting_audio = await collect_reply(ws)
        print(f"  audio      : {len(greeting_audio):,} bytes of PCM16\n")

        print(f"[1] typed turn: {QUESTION!r}")
        await ws.send(json.dumps({"type": "text", "text": QUESTION}))
        reply, audio = await collect_reply(ws)
        seconds = len(audio) / (sample_rate * 2)
        print(f"  audio      : {len(audio):,} bytes of PCM16 (~{seconds:.1f}s)\n")

        if not audio:
            print("no audio came back — TTS is not working")
            return 1

        print("[2] speaking that answer back at the server (Piper -> Whisper)")
        wav = to_wav(audio, sample_rate)
        for offset in range(0, len(wav), 32768):
            await ws.send(wav[offset : offset + 32768])
        await ws.send(json.dumps({"type": "end_of_turn"}))
        echo, echo_audio = await collect_reply(ws)
        print(f"  audio      : {len(echo_audio):,} bytes returned")

        if not echo.get("transcript"):
            print("\nSTT produced no transcript — the listening path is broken")
            return 1
        print("\nBoth directions work: Piper spoke, Whisper heard it, the agent replied.")
        return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("business_id")
    parser.add_argument("--host", default="127.0.0.1:8000")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(main(args.business_id, args.host)))
