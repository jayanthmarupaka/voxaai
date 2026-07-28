"""Health and readiness."""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import text

from app import llm
from app.config import settings
from app.deps import SessionDep
from app.services import notifications

router = APIRouter(tags=["health"])


@router.get("/health")
async def health(session: SessionDep) -> dict[str, object]:
    try:
        await session.execute(text("SELECT 1"))
        database = "ok"
    except Exception as exc:  # surfaced rather than raised: this is a probe
        database = f"error: {type(exc).__name__}"

    from app.services import stt, tts

    return {
        "status": "ok" if database == "ok" else "degraded",
        "database": database,
        "llm": llm.describe_config(),
        "voice": {
            "stt_available": stt.is_available(),
            "tts_available": tts.is_available(),
            "whisper_model": settings.whisper_model,
            "piper_voice": settings.piper_voice,
        },
        "integrations": {
            "google_oauth_configured": bool(
                settings.google_client_id and settings.google_client_secret
            ),
            "clerk_configured": bool(settings.clerk_issuer),
            "smtp_configured": notifications.is_configured(),
        },
    }
