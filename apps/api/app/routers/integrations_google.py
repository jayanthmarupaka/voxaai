"""Google Calendar OAuth connect/disconnect for the owner dashboard.

The ``state`` parameter is a short-lived signed JWT binding the callback to the
business that started the flow, which is what stops an attacker from attaching
their own calendar to someone else's business.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import httpx
import jwt
from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import RedirectResponse

from app.config import settings
from app.deps import CurrentBusiness, SessionDep
from app.models import GoogleCredential
from app.schemas import GoogleStatus
from app.security import encrypt
from app.services.calendar import GOOGLE_SCOPES, GOOGLE_TOKEN_URI, get_google_credential

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/integrations/google", tags=["integrations"])

GOOGLE_AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_USERINFO_ENDPOINT = "https://www.googleapis.com/oauth2/v3/userinfo"
STATE_TTL_SECONDS = 600


def _state_secret() -> str:
    if not settings.token_encryption_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="TOKEN_ENCRYPTION_KEY is not configured.",
        )
    return settings.token_encryption_key


def _require_oauth_config() -> None:
    if not settings.google_client_id or not settings.google_client_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google OAuth is not configured (GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET).",
        )


@router.get("/status", response_model=GoogleStatus)
async def google_status(business: CurrentBusiness, session: SessionDep) -> GoogleStatus:
    credential = await get_google_credential(session, business.id)
    configured = bool(settings.google_client_id and settings.google_client_secret)
    if credential is None:
        return GoogleStatus(connected=False, oauth_configured=configured)
    return GoogleStatus(
        connected=True,
        calendar_id=credential.calendar_id,
        google_account_email=credential.google_account_email,
        connected_at=credential.connected_at,
        oauth_configured=configured,
    )


@router.get("/authorize")
async def authorize(business: CurrentBusiness) -> dict[str, str]:
    """Return the consent URL for the dashboard to redirect the owner to."""
    _require_oauth_config()

    state = jwt.encode(
        {
            "bid": str(business.id),
            "exp": datetime.now(UTC) + timedelta(seconds=STATE_TTL_SECONDS),
        },
        _state_secret(),
        algorithm="HS256",
    )
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_redirect_uri,
        "response_type": "code",
        "scope": " ".join(GOOGLE_SCOPES),
        "access_type": "offline",
        # Without this Google omits the refresh token on repeat authorisations.
        "prompt": "consent",
        "include_granted_scopes": "true",
        "state": state,
    }
    return {"url": f"{GOOGLE_AUTH_ENDPOINT}?{urlencode(params)}"}


@router.get("/callback")
async def callback(
    session: SessionDep,
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
) -> RedirectResponse:
    """Google redirects the owner's browser here — no Clerk session available.

    Tenancy therefore comes from the signed ``state`` token, not from a
    parameter the caller could choose freely.
    """
    settings_page = f"{settings.web_base_url.rstrip('/')}/dashboard/settings"

    if error:
        return RedirectResponse(f"{settings_page}?google=denied", status_code=303)
    if not code or not state:
        return RedirectResponse(f"{settings_page}?google=invalid", status_code=303)

    try:
        claims = jwt.decode(state, _state_secret(), algorithms=["HS256"])
        business_id = uuid.UUID(claims["bid"])
    except (jwt.InvalidTokenError, KeyError, ValueError):
        logger.warning("Rejected Google OAuth callback with an invalid state token.")
        return RedirectResponse(f"{settings_page}?google=invalid_state", status_code=303)

    _require_oauth_config()

    async with httpx.AsyncClient(timeout=15.0) as client:
        token_response = await client.post(
            GOOGLE_TOKEN_URI,
            data={
                "code": code,
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "redirect_uri": settings.google_redirect_uri,
                "grant_type": "authorization_code",
            },
        )
        if token_response.status_code != 200:
            logger.error("Google token exchange failed: %s", token_response.text[:300])
            return RedirectResponse(f"{settings_page}?google=exchange_failed", status_code=303)
        tokens = token_response.json()

        account_email = None
        access_token = tokens.get("access_token")
        if access_token:
            userinfo = await client.get(
                GOOGLE_USERINFO_ENDPOINT,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if userinfo.status_code == 200:
                account_email = userinfo.json().get("email")

    refresh_token = tokens.get("refresh_token")
    if not refresh_token:
        # Happens when the account has already granted access and `prompt` was
        # not honoured; the user must revoke and retry.
        return RedirectResponse(f"{settings_page}?google=no_refresh_token", status_code=303)

    credential = await get_google_credential(session, business_id)
    if credential is None:
        credential = GoogleCredential(business_id=business_id)
        session.add(credential)

    credential.encrypted_refresh_token = encrypt(refresh_token)
    credential.scopes = tokens.get("scope", " ".join(GOOGLE_SCOPES))
    credential.calendar_id = "primary"
    credential.google_account_email = account_email
    credential.connected_at = datetime.now(UTC)
    await session.flush()

    return RedirectResponse(f"{settings_page}?google=connected", status_code=303)


@router.delete("/disconnect", status_code=status.HTTP_204_NO_CONTENT)
async def disconnect(business: CurrentBusiness, session: SessionDep) -> None:
    credential = await get_google_credential(session, business.id)
    if credential is not None:
        await session.delete(credential)
        await session.flush()
