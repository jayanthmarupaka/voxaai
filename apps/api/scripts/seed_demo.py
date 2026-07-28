"""Seed two demo businesses so tenant isolation is visible, not just claimed.

    python -m scripts.seed_demo

Creates a dental practice and a hair salon with different prices, opening hours
and services, then indexes a knowledge document for each. Asking the salon
about dental prices should escalate rather than answer.

Re-running is safe: it updates the existing rows instead of duplicating them.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.models import Business, Document  # noqa: E402
from app.services.rag import index_document  # noqa: E402

WEEKDAY_HOURS = {
    "mon": [{"open": "09:00", "close": "17:00"}],
    "tue": [{"open": "09:00", "close": "17:00"}],
    "wed": [{"open": "09:00", "close": "17:00"}],
    "thu": [{"open": "09:00", "close": "17:00"}],
    "fri": [{"open": "09:00", "close": "16:00"}],
    "sat": [],
    "sun": [],
}

DENTAL_DOC = """
Northgate Dental Practice — patient information

Prices
  Routine check-up: £45
  Hygienist clean: £60
  White filling: £120 to £180 depending on size
  Emergency appointment: £75, seen the same day where possible

Appointments
  Check-ups take 30 minutes. Hygienist appointments take 45 minutes.
  We ask for 24 hours' notice to cancel; late cancellations are charged £25.

Practice information
  We are open Monday to Thursday 9am to 5pm, and Friday 9am to 4pm.
  We are closed at weekends.
  Free parking is available behind the building.
  We accept NHS patients for children under 18 only. Adults are private.

Payment
  We take card and cash. We offer a monthly payment plan at £15 per month
  which covers two check-ups and two hygienist visits per year.
"""

SALON_DOC = """
Ivy Lane Hair Studio — service guide

Prices
  Cut and finish: £38
  Restyle: £52
  Half head of highlights: £85
  Full head of highlights: £120
  Balayage: £145
  Root touch-up: £45

Timings
  A cut and finish takes 45 minutes. Colour appointments take 2 hours.
  Balayage takes 2 and a half hours.

Salon information
  Open Tuesday to Saturday, 9am to 6pm. Closed Sunday and Monday.
  A skin test is required at least 48 hours before any colour service.
  We do not take card payments under £10.
"""

SEEDS = [
    {
        "clerk_org_id": "org_demo_dental",
        "name": "Northgate Dental Practice",
        "timezone": "Europe/London",
        "greeting": (
            "Thanks for calling Northgate Dental. I can book you in or answer questions "
            "about the practice — what can I do for you?"
        ),
        "business_hours": WEEKDAY_HOURS,
        "services": [
            {"name": "Check-up", "duration_minutes": 30},
            {"name": "Hygienist", "duration_minutes": 45},
            {"name": "Emergency appointment", "duration_minutes": 30},
        ],
        "document": ("northgate-dental-info.txt", DENTAL_DOC),
    },
    {
        "clerk_org_id": "org_demo_salon",
        "name": "Ivy Lane Hair Studio",
        "timezone": "Europe/London",
        "greeting": "Hi, Ivy Lane Hair Studio — would you like to book in, or ask about a service?",
        "business_hours": {
            "mon": [],
            "tue": [{"open": "09:00", "close": "18:00"}],
            "wed": [{"open": "09:00", "close": "18:00"}],
            "thu": [{"open": "09:00", "close": "18:00"}],
            "fri": [{"open": "09:00", "close": "18:00"}],
            "sat": [{"open": "09:00", "close": "18:00"}],
            "sun": [],
        },
        "services": [
            {"name": "Cut and finish", "duration_minutes": 45},
            {"name": "Highlights", "duration_minutes": 120},
            {"name": "Balayage", "duration_minutes": 150},
        ],
        "document": ("ivy-lane-services.txt", SALON_DOC),
    },
]


async def main() -> None:
    async with SessionLocal() as session:
        for seed in SEEDS:
            filename, text = seed.pop("document")  # type: ignore[misc]

            business = await session.scalar(
                select(Business).where(Business.clerk_org_id == seed["clerk_org_id"])
            )
            if business is None:
                business = Business(**seed)
                session.add(business)
            else:
                for key, value in seed.items():
                    setattr(business, key, value)
            await session.flush()

            document = await session.scalar(
                select(Document).where(
                    Document.business_id == business.id, Document.filename == filename
                )
            )
            if document is None:
                document = Document(business_id=business.id, filename=filename)
                session.add(document)

            document.mime_type = "text/plain"
            document.raw_text = text.strip()
            document.byte_size = len(text.encode())
            document.status = "pending"
            await session.flush()

            chunks = await index_document(session, document)
            print(f"{business.name}: {chunks} chunks indexed  (id={business.id})")

        await session.commit()

    print("\nOpen /demo/<id> for either business. Asking one about the other's")
    print("prices should escalate — that is the tenant boundary working.")


if __name__ == "__main__":
    asyncio.run(main())
