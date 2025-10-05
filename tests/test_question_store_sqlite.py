import datetime as dt
from typing import Optional

import pytest

from app.question_store import QuestionRecord, QuestionStore, _extract_review_note


@pytest.fixture
def store(tmp_path):
    db_path = tmp_path / "questions.sqlite"
    qs = QuestionStore(db_url=None, db_path=str(db_path))
    try:
        yield qs
    finally:
        qs.close()


def _build_record(
    question_date: dt.date,
    idx: int = 1,
    zh: Optional[str] = None,
    review_note: Optional[str] = "note",
) -> QuestionRecord:
    payload = {
        "id": f"daily-test-{idx:03d}",
        "zh": zh or f"question-{idx}",
        "hints": [{"category": "lexical", "text": "hint"}],
        "tags": ["tag"],
        "difficulty": 2,
        "referenceEn": f"Answer {idx}",
    }
    if review_note is not None:
        payload["reviewNote"] = review_note
    return QuestionRecord.from_payload(
        question_date=question_date,
        item=payload,
        reference_en=payload["referenceEn"],
        model="gemini-test",
        prompt_hash=f"hash-{idx}",
    )


def test_extract_review_note_prefers_suggestions():
    item = {
        "reviewNote": "  ",
        "suggestions": [{"text": " first  "}, {"text": ""}],
    }
    assert _extract_review_note(item) == "first"
    assert _extract_review_note({}) is None


def test_save_many_counts_duplicates(store):
    today = dt.date.today()
    record = _build_record(today, idx=1)

    summary_first = store.save_many([record])
    assert summary_first.inserted == 1
    assert summary_first.duplicates == 0

    summary_second = store.save_many([record])
    assert summary_second.inserted == 0
    assert summary_second.duplicates == 1

    row = store._conn.execute("SELECT review_note FROM generated_questions WHERE id = ?", (record.id,)).fetchone()
    assert row is not None and row[0] == "note"


def test_reserve_questions_zero_count_noop(store):
    today = dt.date.today()
    record = _build_record(today, idx=2)
    store.save_many([record])

    result = store.reserve_questions_for_delivery(question_date=today, count=0, device_id="device-zero")
    assert result == []

    deliveries = store._conn.execute("SELECT COUNT(*) FROM generated_question_deliveries").fetchone()[0]
    assert deliveries == 0


def test_reserve_and_summary_flow(store):
    today = dt.date.today()
    record_one = _build_record(today, idx=3, zh="first-question")
    record_two = _build_record(today, idx=4, zh="second-question")
    store.save_many([record_one, record_two])

    first_batch = store.reserve_questions_for_delivery(question_date=today, count=1, device_id="device-A")
    assert len(first_batch) == 1
    assert store.remaining_questions_for_date(question_date=today, device_id="device-A") == 1

    second_batch = store.reserve_questions_for_delivery(question_date=today, count=5, device_id="device-A")
    assert len(second_batch) == 1
    assert store.remaining_questions_for_date(question_date=today, device_id="device-A") == 0

    third_batch = store.reserve_questions_for_delivery(question_date=today, count=5, device_id="device-B")
    assert len(third_batch) == 2

    summary = store.recent_summary(limit=0)
    assert summary and summary[0]["question_count"] == 4
    assert summary[0]["delivered_devices"] == 2
    assert isinstance(summary[0]["question_date"], dt.date)
