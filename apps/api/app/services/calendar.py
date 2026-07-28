"""Calendar availability and booking.

Two rules this module exists to enforce:

1. A booking is only ever written after availability has been re-checked
   *inside* the same call that writes it. Callers cannot skip the check.
2. Availability means both "inside the business's configured opening hours"
   and "not overlapping anything already on the calendar".

The busy-time source is Google Calendar when the business has connected one,
and the local ``bookings`` table otherwise. Both backends satisfy the same
interface, so the agent code is identical either way.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from google.auth.exceptions import RefreshError
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.config import settings
from app.models import Booking, Business, GoogleCredential
from app.security import decrypt

logger = logging.getLogger(__name__)

GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/calendar.readonly",
]
GOOGLE_TOKEN_URI = "https://oauth2.googleapis.com/token"  # noqa: S105 - a URL, not a secret

WEEKDAY_KEYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")

DEFAULT_BUSINESS_HOURS: dict[str, list[dict[str, str]]] = {
    "mon": [{"open": "09:00", "close": "17:00"}],
    "tue": [{"open": "09:00", "close": "17:00"}],
    "wed": [{"open": "09:00", "close": "17:00"}],
    "thu": [{"open": "09:00", "close": "17:00"}],
    "fri": [{"open": "09:00", "close": "17:00"}],
    "sat": [],
    "sun": [],
}

SLOT_GRANULARITY_MINUTES = 15
DEFAULT_DURATION_MINUTES = 30
MAX_SEARCH_DAYS = 14


class CalendarError(RuntimeError):
    """Recoverable calendar problem — surfaced to the customer as speech."""


class SlotUnavailableError(CalendarError):
    def __init__(self, reason: str, alternatives: list[datetime] | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.alternatives = alternatives or []


@dataclass(frozen=True)
class BusyPeriod:
    start: datetime
    end: datetime


# ---------------------------------------------------------------------------
# Business hours
# ---------------------------------------------------------------------------


def business_timezone(business: Business) -> ZoneInfo:
    try:
        return ZoneInfo(business.timezone or "UTC")
    except ZoneInfoNotFoundError:
        logger.warning("Unknown timezone %r for business %s; falling back to UTC.",
                       business.timezone, business.id)
        return ZoneInfo("UTC")


def _hours_for(business: Business, day: date) -> list[tuple[time, time]]:
    configured = business.business_hours or DEFAULT_BUSINESS_HOURS
    windows = configured.get(WEEKDAY_KEYS[day.weekday()], [])
    parsed: list[tuple[time, time]] = []
    for window in windows:
        try:
            opens = time.fromisoformat(str(window["open"]))
            closes = time.fromisoformat(str(window["close"]))
        except (KeyError, ValueError):
            logger.warning("Skipping malformed business-hours window %r", window)
            continue
        if closes > opens:
            parsed.append((opens, closes))
    return parsed


def is_within_business_hours(business: Business, start: datetime, end: datetime) -> bool:
    """True when ``[start, end)`` fits entirely inside one opening window."""
    tz = business_timezone(business)
    local_start = start.astimezone(tz)
    local_end = end.astimezone(tz)
    if local_start.date() != local_end.date():
        return False  # Overnight bookings are not supported.
    return any(
        opens <= local_start.time() and local_end.time() <= closes
        for opens, closes in _hours_for(business, local_start.date())
    )


def business_hours_summary(business: Business) -> str:
    """Human-readable opening hours, used in prompts and spoken replies."""
    configured = business.business_hours or DEFAULT_BUSINESS_HOURS
    labels = {
        "mon": "Monday", "tue": "Tuesday", "wed": "Wednesday", "thu": "Thursday",
        "fri": "Friday", "sat": "Saturday", "sun": "Sunday",
    }
    lines = []
    for key in WEEKDAY_KEYS:
        windows = configured.get(key, [])
        if not windows:
            lines.append(f"{labels[key]}: closed")
        else:
            spans = ", ".join(f"{w.get('open')}-{w.get('close')}" for w in windows)
            lines.append(f"{labels[key]}: {spans}")
    return "; ".join(lines)


# ---------------------------------------------------------------------------
# Google client
# ---------------------------------------------------------------------------


async def get_google_credential(
    session: AsyncSession, business_id: uuid.UUID
) -> GoogleCredential | None:
    return await session.scalar(
        select(GoogleCredential).where(GoogleCredential.business_id == business_id)
    )


def _build_service(credential: GoogleCredential):
    creds = Credentials(
        token=None,
        refresh_token=decrypt(credential.encrypted_refresh_token),
        token_uri=GOOGLE_TOKEN_URI,
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        scopes=credential.scopes.split() or GOOGLE_SCOPES,
    )
    return build("calendar", "v3", credentials=creds, cache_discovery=False)


# ---------------------------------------------------------------------------
# Busy-time backends
# ---------------------------------------------------------------------------


async def _google_busy(
    credential: GoogleCredential, window_start: datetime, window_end: datetime
) -> list[BusyPeriod]:
    def _query() -> list[BusyPeriod]:
        service = _build_service(credential)
        response = (
            service.freebusy()
            .query(
                body={
                    "timeMin": window_start.astimezone(UTC).isoformat(),
                    "timeMax": window_end.astimezone(UTC).isoformat(),
                    "items": [{"id": credential.calendar_id}],
                }
            )
            .execute()
        )
        calendars = response.get("calendars", {})
        entry = calendars.get(credential.calendar_id, {})
        if entry.get("errors"):
            raise CalendarError(f"Google Calendar returned errors: {entry['errors']}")
        return [
            BusyPeriod(
                start=datetime.fromisoformat(period["start"].replace("Z", "+00:00")),
                end=datetime.fromisoformat(period["end"].replace("Z", "+00:00")),
            )
            for period in entry.get("busy", [])
        ]

    try:
        return await run_in_threadpool(_query)
    except RefreshError as exc:
        raise CalendarError(
            "The Google Calendar connection has expired. Please reconnect it in the dashboard."
        ) from exc
    except HttpError as exc:
        raise CalendarError(f"Google Calendar request failed: {exc}") from exc


async def _local_busy(
    session: AsyncSession, business_id: uuid.UUID, window_start: datetime, window_end: datetime
) -> list[BusyPeriod]:
    rows = await session.scalars(
        select(Booking).where(
            Booking.business_id == business_id,
            Booking.status != "cancelled",
            Booking.ends_at > window_start,
            Booking.starts_at < window_end,
        )
    )
    return [BusyPeriod(start=row.starts_at, end=row.ends_at) for row in rows]


async def get_busy_periods(
    session: AsyncSession, business: Business, window_start: datetime, window_end: datetime
) -> list[BusyPeriod]:
    credential = await get_google_credential(session, business.id)
    if credential is not None:
        return await _google_busy(credential, window_start, window_end)
    logger.info(
        "Business %s has no Google Calendar connected; using local bookings as the "
        "busy-time source.",
        business.id,
    )
    return await _local_busy(session, business.id, window_start, window_end)


def _overlaps(start: datetime, end: datetime, busy: list[BusyPeriod]) -> bool:
    return any(period.start < end and start < period.end for period in busy)


# ---------------------------------------------------------------------------
# Availability
# ---------------------------------------------------------------------------


async def find_available_slots(
    session: AsyncSession,
    business: Business,
    *,
    duration_minutes: int = DEFAULT_DURATION_MINUTES,
    search_from: datetime | None = None,
    on_day: date | None = None,
    limit: int = 5,
    search_days: int = MAX_SEARCH_DAYS,
) -> list[datetime]:
    """Return up to ``limit`` bookable start times, as timezone-aware UTC."""
    tz = business_timezone(business)
    now = datetime.now(UTC)
    cursor = max(search_from or now, now)

    if on_day is not None:
        window_start = datetime.combine(on_day, time.min, tzinfo=tz).astimezone(UTC)
        window_end = window_start + timedelta(days=1)
        days = [on_day]
    else:
        window_start = cursor
        window_end = cursor + timedelta(days=search_days)
        first_day = cursor.astimezone(tz).date()
        days = [first_day + timedelta(days=offset) for offset in range(search_days)]

    busy = await get_busy_periods(session, business, window_start, window_end)

    slots: list[datetime] = []
    step = timedelta(minutes=SLOT_GRANULARITY_MINUTES)
    duration = timedelta(minutes=duration_minutes)

    for day in days:
        for opens, closes in _hours_for(business, day):
            slot_local = datetime.combine(day, opens, tzinfo=tz)
            day_close = datetime.combine(day, closes, tzinfo=tz)
            while slot_local + duration <= day_close:
                slot_utc = slot_local.astimezone(UTC)
                if slot_utc >= cursor and not _overlaps(slot_utc, slot_utc + duration, busy):
                    slots.append(slot_utc)
                    if len(slots) >= limit:
                        return slots
                slot_local += step
    return slots


async def check_availability(
    session: AsyncSession,
    business: Business,
    start: datetime,
    duration_minutes: int = DEFAULT_DURATION_MINUTES,
) -> tuple[bool, str]:
    """``(available, reason)`` for a specific start time."""
    end = start + timedelta(minutes=duration_minutes)

    if start <= datetime.now(UTC):
        return False, "that time is in the past"
    if not is_within_business_hours(business, start, end):
        return False, "that time is outside our opening hours"

    busy = await get_busy_periods(session, business, start, end)
    if _overlaps(start, end, busy):
        return False, "that time is already booked"
    return True, "available"


# ---------------------------------------------------------------------------
# Writes — every one of these re-checks availability first
# ---------------------------------------------------------------------------


async def create_booking(
    session: AsyncSession,
    business: Business,
    *,
    start: datetime,
    duration_minutes: int = DEFAULT_DURATION_MINUTES,
    customer_name: str,
    customer_email: str | None = None,
    customer_phone: str | None = None,
    service: str | None = None,
    conversation_id: uuid.UUID | None = None,
) -> Booking:
    available, reason = await check_availability(session, business, start, duration_minutes)
    if not available:
        alternatives = await find_available_slots(
            session, business, duration_minutes=duration_minutes, search_from=start, limit=3
        )
        raise SlotUnavailableError(reason, alternatives)

    end = start + timedelta(minutes=duration_minutes)
    credential = await get_google_credential(session, business.id)
    google_event_id: str | None = None

    if credential is not None:
        summary = f"{service or 'Appointment'} — {customer_name}"
        description_lines = [f"Booked by the Voxa AI receptionist for {business.name}."]
        if customer_email:
            description_lines.append(f"Email: {customer_email}")
        if customer_phone:
            description_lines.append(f"Phone: {customer_phone}")

        body = {
            "summary": summary,
            "description": "\n".join(description_lines),
            "start": {"dateTime": start.astimezone(UTC).isoformat()},
            "end": {"dateTime": end.astimezone(UTC).isoformat()},
        }

        def _insert() -> str:
            service_client = _build_service(credential)
            created = (
                service_client.events()
                .insert(calendarId=credential.calendar_id, body=body)
                .execute()
            )
            return created["id"]

        try:
            google_event_id = await run_in_threadpool(_insert)
        except HttpError as exc:
            raise CalendarError(f"Could not create the calendar event: {exc}") from exc

    booking = Booking(
        business_id=business.id,
        conversation_id=conversation_id,
        customer_name=customer_name,
        customer_email=customer_email,
        customer_phone=customer_phone,
        service=service,
        starts_at=start,
        ends_at=end,
        google_event_id=google_event_id,
        status="confirmed",
    )
    session.add(booking)
    await session.flush()
    return booking


async def find_booking(
    session: AsyncSession,
    business_id: uuid.UUID,
    *,
    customer_name: str | None = None,
    customer_email: str | None = None,
) -> Booking | None:
    """Most recent upcoming confirmed booking matching the customer."""
    query = (
        select(Booking)
        .where(
            Booking.business_id == business_id,
            Booking.status != "cancelled",
            Booking.starts_at >= datetime.now(UTC),
        )
        .order_by(Booking.starts_at)
    )
    if customer_email:
        query = query.where(Booking.customer_email == customer_email)
    elif customer_name:
        query = query.where(Booking.customer_name.ilike(customer_name))
    return await session.scalar(query.limit(1))


async def reschedule_booking(
    session: AsyncSession,
    business: Business,
    booking: Booking,
    *,
    new_start: datetime,
    duration_minutes: int | None = None,
) -> Booking:
    if booking.business_id != business.id:
        raise CalendarError("Booking does not belong to this business.")

    minutes = duration_minutes or int(
        (booking.ends_at - booking.starts_at).total_seconds() // 60
    )
    available, reason = await check_availability(session, business, new_start, minutes)
    if not available:
        alternatives = await find_available_slots(
            session, business, duration_minutes=minutes, search_from=new_start, limit=3
        )
        raise SlotUnavailableError(reason, alternatives)

    new_end = new_start + timedelta(minutes=minutes)
    credential = await get_google_credential(session, business.id)
    if credential is not None and booking.google_event_id:
        body = {
            "start": {"dateTime": new_start.astimezone(UTC).isoformat()},
            "end": {"dateTime": new_end.astimezone(UTC).isoformat()},
        }

        def _patch() -> None:
            service_client = _build_service(credential)
            service_client.events().patch(
                calendarId=credential.calendar_id,
                eventId=booking.google_event_id,
                body=body,
            ).execute()

        try:
            await run_in_threadpool(_patch)
        except HttpError as exc:
            raise CalendarError(f"Could not move the calendar event: {exc}") from exc

    booking.starts_at = new_start
    booking.ends_at = new_end
    booking.status = "rescheduled"
    await session.flush()
    return booking


async def cancel_booking(
    session: AsyncSession, business: Business, booking: Booking
) -> Booking:
    if booking.business_id != business.id:
        raise CalendarError("Booking does not belong to this business.")

    credential = await get_google_credential(session, business.id)
    if credential is not None and booking.google_event_id:

        def _delete() -> None:
            service_client = _build_service(credential)
            service_client.events().delete(
                calendarId=credential.calendar_id, eventId=booking.google_event_id
            ).execute()

        try:
            await run_in_threadpool(_delete)
        except HttpError as exc:
            # 404/410 means it is already gone, which is the outcome we wanted.
            if exc.status_code not in (404, 410):
                raise CalendarError(f"Could not cancel the calendar event: {exc}") from exc

    booking.status = "cancelled"
    await session.flush()
    return booking
