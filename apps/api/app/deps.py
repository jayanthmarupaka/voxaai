"""Request dependencies — above all, the single source of tenancy.

``get_current_business`` is the *only* way an authenticated route learns which
business it is acting for. The business ID is derived from the ``org_id`` claim
of a cryptographically verified Clerk session token; it is never read from a
path, query string, or request body. Any route that accepts a business
identifier from the client is public by design and may only expose
non-sensitive data.
"""

from __future__ import annotations

import logging
import uuid
from typing import Annotated, Any

import httpx
import jwt
from fastapi import Depends, Header, HTTPException, Path, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.config import settings
from app.db import get_session
from app.models import Business, User

logger = logging.getLogger(__name__)

SessionDep = Annotated[AsyncSession, Depends(get_session)]

_jwk_client: jwt.PyJWKClient | None = None


def _get_jwk_client() -> jwt.PyJWKClient:
    global _jwk_client
    if _jwk_client is None:
        if not settings.clerk_issuer:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Authentication is not configured (CLERK_ISSUER missing).",
            )
        _jwk_client = jwt.PyJWKClient(
            f"{settings.clerk_issuer.rstrip('/')}/.well-known/jwks.json",
            cache_keys=True,
            lifespan=3600,
        )
    return _jwk_client


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


async def verify_clerk_token(
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Verify a Clerk session JWT and return its claims."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise _unauthorized("Missing bearer token.")
    token = authorization.split(" ", 1)[1].strip()

    client = _get_jwk_client()
    try:
        signing_key = await run_in_threadpool(client.get_signing_key_from_jwt, token)
        claims: dict[str, Any] = await run_in_threadpool(
            lambda: jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                issuer=settings.clerk_issuer.rstrip("/"),
                # Clerk session tokens carry no `aud` by default; the issuer
                # check plus signature verification is what binds the token to
                # this application.
                options={"verify_aud": False, "require": ["exp", "iat", "sub", "iss"]},
                leeway=10,
            )
        )
    except jwt.PyJWKClientError as exc:
        logger.warning("Could not resolve Clerk signing key: %s", exc)
        raise _unauthorized("Could not verify token signing key.") from exc
    except jwt.InvalidTokenError as exc:
        logger.info("Rejected Clerk token: %s", exc)
        raise _unauthorized("Invalid or expired session token.") from exc

    return claims


async def _fetch_clerk_org_name(org_id: str) -> str | None:
    """Best-effort lookup of an organization's display name."""
    if not settings.clerk_secret_key:
        return None
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(
                f"https://api.clerk.com/v1/organizations/{org_id}",
                headers={"Authorization": f"Bearer {settings.clerk_secret_key}"},
            )
        if response.status_code == 200:
            return response.json().get("name")
    except httpx.HTTPError as exc:
        logger.warning("Clerk organization lookup failed for %s: %s", org_id, exc)
    return None


async def get_current_business(
    session: SessionDep,
    claims: Annotated[dict[str, Any], Depends(verify_clerk_token)],
) -> Business:
    """Resolve the caller's business from the verified ``org_id`` claim.

    A Clerk user who has not selected (or does not belong to) an organization
    has no business context and is rejected — there is no "personal" fallback,
    because that would give a user data access outside any tenant.
    """
    org_id = claims.get("org_id")
    if not org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "No active organization. Create or select a business "
                "organization before using the dashboard."
            ),
        )

    business = await session.scalar(select(Business).where(Business.clerk_org_id == org_id))
    if business is None:
        # The organization exists in Clerk but the webhook has not landed yet
        # (or was never delivered). Create it on demand so the dashboard is
        # usable immediately.
        business = Business(
            clerk_org_id=org_id,
            name=await _fetch_clerk_org_name(org_id) or claims.get("org_slug") or "My Business",
        )
        session.add(business)
        await session.flush()

    clerk_user_id = claims.get("sub")
    if clerk_user_id:
        user = await session.scalar(select(User).where(User.clerk_user_id == clerk_user_id))
        if user is None:
            session.add(
                User(
                    clerk_user_id=clerk_user_id,
                    business_id=business.id,
                    role=str(claims.get("org_role") or "admin"),
                )
            )
        elif user.business_id != business.id:
            # The user switched organizations; follow the active one.
            user.business_id = business.id
        await session.flush()

    return business


CurrentBusiness = Annotated[Business, Depends(get_current_business)]


async def get_public_business(
    session: SessionDep,
    business_id: Annotated[uuid.UUID, Path()],
) -> Business:
    """Look up a business for the unauthenticated customer-facing demo.

    Callers of this dependency must only ever expose non-sensitive fields
    (name, greeting, services, hours) — never documents, bookings, or
    conversations belonging to the business.
    """
    business = await session.get(Business, business_id)
    if business is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Business not found.")
    return business


PublicBusiness = Annotated[Business, Depends(get_public_business)]
