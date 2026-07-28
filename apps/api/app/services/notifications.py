"""Booking confirmation email.

Delivery is best-effort by design: a customer who never gave an email address,
or an SMTP outage, must not undo a booking that is already on the calendar.
Every failure path here logs and returns rather than raising.
"""

from __future__ import annotations

import logging
from email.message import EmailMessage
from zoneinfo import ZoneInfo

import aiosmtplib

from app.config import settings
from app.models import Booking, Business

logger = logging.getLogger(__name__)


def is_configured() -> bool:
    return bool(settings.smtp_host and settings.smtp_user and settings.smtp_password)


def _body(booking: Booking, business: Business, tz: ZoneInfo) -> str:
    local_start = booking.starts_at.astimezone(tz)
    local_end = booking.ends_at.astimezone(tz)
    lines = [
        f"Hi {booking.customer_name},",
        "",
        f"Your appointment with {business.name} is confirmed.",
        "",
        f"  When:    {local_start.strftime('%A %d %B %Y, %I:%M %p')}"
        f" - {local_end.strftime('%I:%M %p')} ({business.timezone})",
    ]
    if booking.service:
        lines.append(f"  Service: {booking.service}")
    lines += [
        "",
        "Need to change or cancel? Just reply to this email or call us back.",
        "",
        f"— {business.name}",
    ]
    return "\n".join(lines)


async def send_booking_confirmation(booking: Booking, business: Business) -> bool:
    """Returns True only if the message was actually handed to the SMTP server."""
    if not booking.customer_email:
        logger.info("Booking %s has no email address; skipping confirmation.", booking.id)
        return False
    if not is_configured():
        logger.info("SMTP is not configured; skipping confirmation for booking %s.", booking.id)
        return False

    try:
        tz = ZoneInfo(business.timezone or "UTC")
    except Exception:
        tz = ZoneInfo("UTC")

    message = EmailMessage()
    message["From"] = f"{settings.smtp_from_name} <{settings.smtp_from_email or settings.smtp_user}>"
    message["To"] = booking.customer_email
    message["Subject"] = f"Your appointment with {business.name} is confirmed"
    message.set_content(_body(booking, business, tz))

    try:
        await aiosmtplib.send(
            message,
            hostname=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_user,
            password=settings.smtp_password,
            start_tls=settings.smtp_port == 587,
            use_tls=settings.smtp_port == 465,
            timeout=15,
        )
    except (aiosmtplib.SMTPException, OSError) as exc:
        # Deliberately swallowed: the booking is already confirmed on the
        # calendar and must not be rolled back because email failed.
        logger.warning("Confirmation email for booking %s failed: %s", booking.id, exc)
        return False

    logger.info("Sent booking confirmation for %s to %s", booking.id, booking.customer_email)
    return True
