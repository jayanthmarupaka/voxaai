"""Speech-to-text with faster-whisper.

The model is loaded lazily and once, then reused. Transcription is CPU-bound,
so every call runs in a worker thread to keep the event loop free for other
WebSocket sessions.
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path

from starlette.concurrency import run_in_threadpool

from app.config import settings

logger = logging.getLogger(__name__)

_model = None
_load_error: str | None = None


def is_available() -> bool:
    try:
        import faster_whisper  # noqa: F401
    except ImportError:
        return False
    return True


def _load_model():
    """Load the Whisper model. Called once, off the event loop."""
    global _model, _load_error
    if _model is not None:
        return _model
    if _load_error is not None:
        raise RuntimeError(_load_error)

    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        _load_error = (
            "faster-whisper is not installed. Run: "
            "pip install -r requirements-voice.txt"
        )
        raise RuntimeError(_load_error) from exc

    models_dir = settings.models_path
    models_dir.mkdir(parents=True, exist_ok=True)

    logger.info(
        "Loading Whisper model %s (%s) into %s",
        settings.whisper_model,
        settings.whisper_compute_type,
        models_dir,
    )
    _model = WhisperModel(
        settings.whisper_model,
        device="cpu",
        compute_type=settings.whisper_compute_type,
        download_root=str(models_dir),
    )
    return _model


async def warmup() -> None:
    """Preload at startup so the first customer does not pay the load cost."""
    try:
        await run_in_threadpool(_load_model)
    except Exception as exc:
        logger.warning("Whisper warmup skipped: %s", exc)


def _transcribe_sync(audio_path: str) -> str:
    model = _load_model()
    segments, _info = model.transcribe(
        audio_path,
        beam_size=1,
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 300},
        condition_on_previous_text=False,
    )
    return " ".join(segment.text.strip() for segment in segments).strip()


async def transcribe(audio: bytes, suffix: str = ".webm") -> str:
    """Transcribe one utterance of encoded audio (webm/opus, wav, ...).

    faster-whisper decodes container formats via PyAV, so no external ffmpeg
    binary is required.
    """
    if not audio:
        return ""

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as handle:
        handle.write(audio)
        temp_path = handle.name

    try:
        return await run_in_threadpool(_transcribe_sync, temp_path)
    except Exception:
        logger.exception("Transcription failed.")
        raise
    finally:
        Path(temp_path).unlink(missing_ok=True)  # noqa: ASYNC240 - one unlink, not worth a thread
