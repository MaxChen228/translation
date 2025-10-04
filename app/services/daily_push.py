from __future__ import annotations

import datetime as dt
from typing import List

from app.core.settings import get_settings
from app.question_store import QuestionStore
from app.schemas import DailyPushQuestion, BankHint, BankSuggestion


def fetch_daily_push_questions(
    *,
    question_date: dt.date,
    count: int,
    device_id: str,
) -> tuple[List[DailyPushQuestion], int]:
    """Reserve questions for a device and return them along with remaining count."""
    settings = get_settings()
    store = QuestionStore(db_url=settings.QUESTION_DB_URL, db_path=settings.QUESTION_DB_PATH)
    try:
        records = store.reserve_questions_for_delivery(
            question_date=question_date,
            count=count,
            device_id=device_id,
        )
        remaining = store.remaining_questions_for_date(
            question_date=question_date,
            device_id=device_id,
        )
    finally:
        store.close()

    questions: List[DailyPushQuestion] = []
    for record in records:
        raw = dict(record.raw)
        hints = [BankHint(**hint) for hint in record.hints]
        suggestions = [BankSuggestion(**sugg) for sugg in record.suggestions]
        tags = list(raw.get("tags", record.tags)) if raw.get("tags") is not None else list(record.tags)
        suggestion_text = raw.get("suggestion") or record.raw.get("suggestion") or record.reference_en
        questions.append(
            DailyPushQuestion(
                id=record.id,
                zh=record.zh,
                hints=hints,
                suggestions=suggestions,
                suggestion=suggestion_text,
                tags=tags,
                difficulty=record.difficulty,
                referenceEn=record.reference_en,
            )
        )
    return questions, remaining
