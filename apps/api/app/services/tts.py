"""Text-to-speech with Piper.

Piper is fully offline and CPU-only. Synthesis happens sentence by sentence so
the browser can start playing the first sentence while the rest is still being
generated — the difference between a reply that feels instant and one that
feels like a pause.

Output is raw signed 16-bit little-endian mono PCM; the sample rate comes from
the voice and is sent to the client in the ``speech_start`` control frame.

Note: piper-tts is GPL-3.0 licensed. It is a separate process-level dependency
listed in requirements-voice.txt, not linked into this codebase.
"""

from __future__ import annotations

import logging
import re
from collections.abc import AsyncIterator
from pathlib import Path

from starlette.concurrency import run_in_threadpool

from app.config import settings

logger = logging.getLogger(__name__)

DEFAULT_SAMPLE_RATE = 22050
MAX_SENTENCE_CHARS = 240

_voice = None
_sample_rate = DEFAULT_SAMPLE_RATE

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


def is_available() -> bool:
    try:
        import piper  # noqa: F401
    except ImportError:
        return False
    return True


def split_sentences(text: str) -> list[str]:
    """Split into synthesis units, keeping each one short enough to feel snappy."""
    pieces: list[str] = []
    for sentence in _SENTENCE_SPLIT.split(text.strip()):
        sentence = sentence.strip()
        if not sentence:
            continue
        while len(sentence) > MAX_SENTENCE_CHARS:
            cut = sentence.rfind(" ", 0, MAX_SENTENCE_CHARS)
            if cut <= 0:
                cut = MAX_SENTENCE_CHARS
            pieces.append(sentence[:cut].strip())
            sentence = sentence[cut:].strip()
        if sentence:
            pieces.append(sentence)
    return pieces


def _voice_paths() -> tuple[Path, Path]:
    models_dir = settings.models_path
    name = settings.piper_voice
    return models_dir / f"{name}.onnx", models_dir / f"{name}.onnx.json"


def _ensure_voice_files() -> Path:
    """Download the voice on first use if it is not already cached."""
    model_path, config_path = _voice_paths()
    if model_path.exists() and config_path.exists():
        return model_path

    models_dir = settings.models_path
    models_dir.mkdir(parents=True, exist_ok=True)

    from piper.download_voices import download_voice

    logger.info("Downloading Piper voice %s into %s", settings.piper_voice, models_dir)
    download_voice(settings.piper_voice, models_dir)

    if not model_path.exists():
        raise RuntimeError(
            f"Piper voice {settings.piper_voice} was not found after download. "
            f"Expected {model_path}."
        )
    return model_path


def _load_voice():
    global _voice, _sample_rate
    if _voice is not None:
        return _voice

    try:
        from piper import PiperVoice
    except ImportError as exc:
        raise RuntimeError(
            "piper-tts is not installed. Run: pip install -r requirements-voice.txt"
        ) from exc

    model_path = _ensure_voice_files()
    logger.info("Loading Piper voice from %s", model_path)
    _voice = PiperVoice.load(str(model_path))
    _sample_rate = int(getattr(_voice.config, "sample_rate", DEFAULT_SAMPLE_RATE))
    return _voice


async def warmup() -> None:
    try:
        await run_in_threadpool(_load_voice)
    except Exception as exc:
        logger.warning("Piper warmup skipped: %s", exc)


def sample_rate() -> int:
    return _sample_rate


def _synthesize_sync(text: str) -> bytes:
    voice = _load_voice()
    parts: list[bytes] = []
    for chunk in voice.synthesize(text):
        # piper 1.x yields AudioChunk objects; older builds yield raw bytes.
        audio = getattr(chunk, "audio_int16_bytes", None)
        parts.append(audio if audio is not None else bytes(chunk))
    return b"".join(parts)


async def synthesize(text: str) -> bytes:
    """Synthesize a whole string to PCM16 mono bytes."""
    if not text.strip():
        return b""
    return await run_in_threadpool(_synthesize_sync, text)


async def stream_sentences(text: str) -> AsyncIterator[bytes]:
    """Yield PCM16 audio one sentence at a time, in order."""
    for sentence in split_sentences(text):
        audio = await synthesize(sentence)
        if audio:
            yield audio
