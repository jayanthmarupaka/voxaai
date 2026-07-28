"""Turning text into something that sounds right when spoken aloud.

TTS reads literally, so markdown, 24-hour clock times and ISO dates all have to
be normalised before synthesis.
"""

from __future__ import annotations

import re
from datetime import datetime
from zoneinfo import ZoneInfo

_MARKDOWN_PATTERNS = (
    (re.compile(r"```.*?```", re.DOTALL), " "),
    (re.compile(r"`([^`]*)`"), r"\1"),
    (re.compile(r"\*\*([^*]*)\*\*"), r"\1"),
    (re.compile(r"(?<!\w)[*_]([^*_]+)[*_](?!\w)"), r"\1"),
    (re.compile(r"^#{1,6}\s*", re.MULTILINE), ""),
    (re.compile(r"^\s*[-*+]\s+", re.MULTILINE), ""),
    (re.compile(r"\[([^\]]+)\]\([^)]+\)"), r"\1"),
)


def _ordinal(day: int) -> str:
    if 11 <= day % 100 <= 13:
        return f"{day}th"
    suffix = {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
    return f"{day}{suffix}"


def spoken_time(moment: datetime, tz: ZoneInfo) -> str:
    """'2:30 PM' / '9 AM' in the business's local timezone."""
    local = moment.astimezone(tz)
    hour = local.hour % 12 or 12
    meridiem = "AM" if local.hour < 12 else "PM"
    if local.minute == 0:
        return f"{hour} {meridiem}"
    return f"{hour}:{local.minute:02d} {meridiem}"


def spoken_date(moment: datetime, tz: ZoneInfo, *, today: datetime | None = None) -> str:
    """'today' / 'tomorrow' / 'Thursday the 5th of August'."""
    local = moment.astimezone(tz)
    reference = (today or datetime.now(tz)).astimezone(tz)
    delta = (local.date() - reference.date()).days
    if delta == 0:
        return "today"
    if delta == 1:
        return "tomorrow"
    if 2 <= delta <= 6:
        return local.strftime("%A")
    return f"{local.strftime('%A')} the {_ordinal(local.day)} of {local.strftime('%B')}"


def spoken_datetime(moment: datetime, tz: ZoneInfo, *, today: datetime | None = None) -> str:
    return f"{spoken_date(moment, tz, today=today)} at {spoken_time(moment, tz)}"


def spoken_list(items: list[str]) -> str:
    """'a', 'a or b', 'a, b, or c'."""
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} or {items[1]}"
    return f"{', '.join(items[:-1])}, or {items[-1]}"


def normalise_for_speech(text: str) -> str:
    """Strip formatting and collapse whitespace so TTS reads it cleanly."""
    cleaned = text or ""
    for pattern, replacement in _MARKDOWN_PATTERNS:
        cleaned = pattern.sub(replacement, cleaned)
    cleaned = cleaned.replace("&", " and ")
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()
