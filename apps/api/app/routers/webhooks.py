"""Clerk webhooks — keep ``businesses`` / ``users`` in step with Clerk.

The payload is untrusted until the Svix signature has been verified, so nothing
is read from the body before that check passes.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select
from svix.webhooks import Webhook, WebhookVerificationError

from app.config import settings
from app.deps import SessionDep
from app.models import Business, User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])


@router.post("/clerk", status_code=status.HTTP_204_NO_CONTENT)
async def clerk_webhook(request: Request, session: SessionDep) -> None:
    if not settings.clerk_webhook_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="CLERK_WEBHOOK_SECRET is not configured.",
        )

    body = await request.body()
    headers = {
        "svix-id": request.headers.get("svix-id", ""),
        "svix-timestamp": request.headers.get("svix-timestamp", ""),
        "svix-signature": request.headers.get("svix-signature", ""),
    }

    try:
        payload = Webhook(settings.clerk_webhook_secret).verify(body, headers)
    except WebhookVerificationError as exc:
        logger.warning("Rejected Clerk webhook with an invalid signature: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid webhook signature."
        ) from exc

    event_type = payload.get("type", "")
    data = payload.get("data", {}) or {}

    if event_type in {"organization.created", "organization.updated"}:
        await _upsert_business(session, data)
    elif event_type == "organization.deleted":
        await _delete_business(session, data)
    elif event_type in {"organizationMembership.created", "organizationMembership.updated"}:
        await _upsert_membership(session, data)
    else:
        logger.debug("Ignoring Clerk event %s", event_type)


async def _upsert_business(session: SessionDep, data: dict) -> None:
    org_id = data.get("id")
    if not org_id:
        return
    business = await session.scalar(select(Business).where(Business.clerk_org_id == org_id))
    name = data.get("name") or data.get("slug") or "My Business"
    if business is None:
        session.add(Business(clerk_org_id=org_id, name=name))
    else:
        business.name = name
    await session.flush()


async def _delete_business(session: SessionDep, data: dict) -> None:
    org_id = data.get("id")
    if not org_id:
        return
    business = await session.scalar(select(Business).where(Business.clerk_org_id == org_id))
    if business is not None:
        await session.delete(business)
        await session.flush()


async def _upsert_membership(session: SessionDep, data: dict) -> None:
    org_id = (data.get("organization") or {}).get("id")
    public_user = data.get("public_user_data") or {}
    clerk_user_id = public_user.get("user_id")
    if not org_id or not clerk_user_id:
        return

    business = await session.scalar(select(Business).where(Business.clerk_org_id == org_id))
    if business is None:
        business = Business(
            clerk_org_id=org_id,
            name=(data.get("organization") or {}).get("name") or "My Business",
        )
        session.add(business)
        await session.flush()

    user = await session.scalar(select(User).where(User.clerk_user_id == clerk_user_id))
    email = public_user.get("identifier")
    role = data.get("role") or "admin"
    if user is None:
        session.add(
            User(
                clerk_user_id=clerk_user_id,
                business_id=business.id,
                email=email,
                role=role,
            )
        )
    else:
        user.business_id = business.id
        user.email = email or user.email
        user.role = role
    await session.flush()
