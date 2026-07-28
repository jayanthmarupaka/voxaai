"""Business-hours and availability rules — no network, no database."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.models import Business
from app.services.calendar import (
    DEFAULT_BUSINESS_HOURS,
    BusyPeriod,
    _overlaps,
    business_hours_summary,
    is_within_business_hours,
)


def make_business(**kwargs) -> Business:
    business = Business(
        clerk_org_id="org_unit_test",
        name="Unit Test Co",
        timezone=kwargs.pop("timezone", "UTC"),
        greeting="Hello",
        business_hours=kwargs.pop("business_hours", DEFAULT_BUSINESS_HOURS),
        services=kwargs.pop("services", []),
    )
    return business


# 2026-08-03 is a Monday; 2026-08-08 is a Saturday.
MONDAY_10AM = datetime(2026, 8, 3, 10, 0, tzinfo=UTC)
SATURDAY_10AM = datetime(2026, 8, 8, 10, 0, tzinfo=UTC)


def test_slot_inside_opening_hours_is_allowed():
    business = make_business()
    assert is_within_business_hours(business, MONDAY_10AM, MONDAY_10AM + timedelta(minutes=30))


def test_slot_before_opening_is_rejected():
    business = make_business()
    early = MONDAY_10AM.replace(hour=7)
    assert not is_within_business_hours(business, early, early + timedelta(minutes=30))


def test_slot_running_past_closing_is_rejected():
    business = make_business()
    late = MONDAY_10AM.replace(hour=16, minute=45)
    assert not is_within_business_hours(business, late, late + timedelta(minutes=30))


def test_closed_day_is_rejected():
    business = make_business()
    assert not is_within_business_hours(
        business, SATURDAY_10AM, SATURDAY_10AM + timedelta(minutes=30)
    )


def test_hours_are_interpreted_in_the_business_timezone():
    """09:00-17:00 New York means 13:00-21:00 UTC in August (EDT)."""
    business = make_business(timezone="America/New_York")
    # 12:00 UTC is 08:00 in New York — before opening.
    too_early = datetime(2026, 8, 3, 12, 0, tzinfo=UTC)
    assert not is_within_business_hours(business, too_early, too_early + timedelta(minutes=30))

    # 14:00 UTC is 10:00 in New York — open.
    fine = datetime(2026, 8, 3, 14, 0, tzinfo=UTC)
    assert is_within_business_hours(business, fine, fine + timedelta(minutes=30))


def test_overnight_booking_is_rejected():
    business = make_business(
        business_hours={**DEFAULT_BUSINESS_HOURS, "mon": [{"open": "09:00", "close": "23:59"}]}
    )
    start = MONDAY_10AM.replace(hour=23, minute=45)
    assert not is_within_business_hours(business, start, start + timedelta(minutes=60))


def test_malformed_hours_are_ignored_not_crashed():
    business = make_business(business_hours={"mon": [{"open": "not-a-time", "close": "17:00"}]})
    assert not is_within_business_hours(business, MONDAY_10AM, MONDAY_10AM + timedelta(minutes=30))


@pytest.mark.parametrize(
    ("start_hour", "end_hour", "expected"),
    [
        (10, 11, True),   # exactly the busy period
        (10, 10, False),  # zero-length range at the boundary
        (9, 10, False),   # ends exactly when busy starts
        (11, 12, False),  # starts exactly when busy ends
        (9, 12, True),    # fully contains the busy period
        (10, 10.5, True), # inside the busy period
    ],
)
def test_overlap_boundaries(start_hour, end_hour, expected):
    busy = [
        BusyPeriod(
            start=datetime(2026, 8, 3, 10, tzinfo=UTC),
            end=datetime(2026, 8, 3, 11, tzinfo=UTC),
        )
    ]
    start = datetime(2026, 8, 3, tzinfo=UTC) + timedelta(hours=start_hour)
    end = datetime(2026, 8, 3, tzinfo=UTC) + timedelta(hours=end_hour)
    assert _overlaps(start, end, busy) is expected


def test_business_hours_summary_marks_closed_days():
    summary = business_hours_summary(make_business())
    assert "Saturday: closed" in summary
    assert "Monday: 09:00-17:00" in summary
