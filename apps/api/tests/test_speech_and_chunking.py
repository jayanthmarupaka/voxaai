"""Speech normalisation and chunking — pure functions, no I/O."""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from app.agents.speech import (
    normalise_for_speech,
    spoken_date,
    spoken_list,
    spoken_time,
)
from app.services.rag import chunk_text
from app.services.tts import split_sentences

TZ = ZoneInfo("UTC")


def test_markdown_is_stripped_so_tts_does_not_read_symbols():
    assert normalise_for_speech("**Bold** and `code` and *italic*") == "Bold and code and italic"
    assert normalise_for_speech("- one\n- two") == "one two"
    assert normalise_for_speech("## Heading") == "Heading"
    assert normalise_for_speech("[our prices](https://example.com)") == "our prices"
    assert normalise_for_speech("Tue & Wed") == "Tue and Wed"


def test_times_are_spoken_not_printed():
    assert spoken_time(datetime(2026, 8, 3, 14, 30, tzinfo=UTC), TZ) == "2:30 PM"
    assert spoken_time(datetime(2026, 8, 3, 9, 0, tzinfo=UTC), TZ) == "9 AM"
    assert spoken_time(datetime(2026, 8, 3, 0, 0, tzinfo=UTC), TZ) == "12 AM"
    assert spoken_time(datetime(2026, 8, 3, 12, 0, tzinfo=UTC), TZ) == "12 PM"


def test_dates_use_relative_words_when_close():
    today = datetime(2026, 8, 3, 9, 0, tzinfo=UTC)
    assert spoken_date(today, TZ, today=today) == "today"
    assert spoken_date(today.replace(day=4), TZ, today=today) == "tomorrow"
    assert spoken_date(today.replace(day=6), TZ, today=today) == "Thursday"
    assert spoken_date(today.replace(day=20), TZ, today=today) == "Thursday the 20th of August"


def test_ordinals_handle_the_teens():
    today = datetime(2026, 8, 1, 9, 0, tzinfo=UTC)
    assert "11th" in spoken_date(today.replace(day=11), TZ, today=today)
    assert "12th" in spoken_date(today.replace(day=12), TZ, today=today)
    assert "13th" in spoken_date(today.replace(day=13), TZ, today=today)
    assert "21st" in spoken_date(today.replace(day=21), TZ, today=today)


def test_spoken_list_reads_naturally():
    assert spoken_list(["9 AM"]) == "9 AM"
    assert spoken_list(["9 AM", "10 AM"]) == "9 AM or 10 AM"
    assert spoken_list(["9 AM", "10 AM", "11 AM"]) == "9 AM, 10 AM, or 11 AM"
    assert spoken_list([]) == ""


def test_sentences_split_for_incremental_synthesis():
    assert split_sentences("One. Two! Three?") == ["One.", "Two!", "Three?"]
    assert split_sentences("   ") == []


def test_long_sentences_are_broken_up():
    long_sentence = " ".join(["word"] * 200)
    pieces = split_sentences(long_sentence)
    assert len(pieces) > 1
    assert all(len(piece) <= 240 for piece in pieces)


def test_chunking_covers_the_whole_document_with_overlap():
    text = ". ".join(f"Sentence number {index} about pricing" for index in range(120))
    chunks = chunk_text(text)
    assert len(chunks) > 1
    assert all(chunk.strip() for chunk in chunks)
    # Nothing is silently dropped: the first and last content both survive.
    assert "Sentence number 0" in chunks[0]
    assert "Sentence number 119" in chunks[-1]


def test_chunking_empty_text_returns_nothing():
    assert chunk_text("") == []
    assert chunk_text("   \n\n  ") == []
