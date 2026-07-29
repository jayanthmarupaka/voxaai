"""A CLI harness for the agent graph — no browser, no websocket.

    python -m scripts.chat_repl <business-id>
    python -m scripts.chat_repl <business-id> --script book

Useful for demonstrating the three canonical paths quickly:
  book      multi-turn slot filling into a real booking
  question  answered from the seeded document
  escalate  refused and logged as a follow-up
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.graph import get_or_create_conversation, run_turn  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.models import Business  # noqa: E402

SCRIPTS: dict[str, list[str]] = {
    "book": [
        "Hi, can I book a check-up?",
        "Tuesday morning would be great",
        "9:15 works for me",
        "My name is Priya Nair and my email is priya@example.com",
    ],
    "question": [
        "How much is a hygienist appointment?",
        "And do you have parking?",
    ],
    "vague": [
        # The caller never volunteers a concrete time, so the agent has to ask
        # again without parroting itself.
        "Hi, I'd like to book a check-up",
        "Sometime in the morning would be nice",
        "My name is Priya Nair",
        "The first one you said is fine",
    ],
    "escalate": [
        "I want to complain about the treatment I had last week and get a refund.",
    ],
}


async def send(business_id: uuid.UUID, messages: list[str] | None) -> None:
    async with SessionLocal() as session:
        business = await session.get(Business, business_id)
        if business is None:
            print(f"No business with id {business_id}. Run scripts/seed_demo.py first.")
            return

        conversation = await get_or_create_conversation(session, business, None, channel="text")
        await session.commit()
        print(f"— {business.name} —\nassistant: {business.greeting}\n")

        queue = list(messages) if messages else None
        while True:
            if queue is not None:
                if not queue:
                    break
                message = queue.pop(0)
                print(f"you: {message}")
            else:
                try:
                    # Off the event loop: stdin blocks until the user hits enter.
                    message = (await asyncio.to_thread(input, "you: ")).strip()
                except (EOFError, KeyboardInterrupt):
                    break
                if not message or message in {"quit", "exit"}:
                    break

            result = await run_turn(session, business, conversation, message)
            await session.commit()
            print(f"assistant [{result.intent} -> {result.outcome}]: {result.reply}")
            if result.sources:
                print(f"           sources: {', '.join(result.sources)}")
            print()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("business_id", type=uuid.UUID)
    parser.add_argument("--script", choices=sorted(SCRIPTS), help="run a canned conversation")
    args = parser.parse_args()

    asyncio.run(send(args.business_id, SCRIPTS.get(args.script) if args.script else None))


if __name__ == "__main__":
    main()
