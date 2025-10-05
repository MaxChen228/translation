from __future__ import annotations

import datetime as dt
from typing import List

from app.core.settings import get_settings
from app.question_store import QuestionStore
from app.schemas import DailyPushQuestion, BankHint


def fetch_daily_push_questions(
    *,
    question_date: dt.date,
    count: int,
    device_id: str,
    force_reset: bool = False,
) -> tuple[List[DailyPushQuestion], int]:
    """Reserve questions for a device and return them along with remaining count."""
    settings = get_settings()
    store = QuestionStore(db_url=settings.QUESTION_DB_URL, db_path=settings.QUESTION_DB_PATH)
    try:
        if force_reset:
            store.reset_deliveries_for_device(
                question_date=question_date,
                device_id=device_id,
            )

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
        tags = list(raw.get("tags", record.tags)) if raw.get("tags") is not None else list(record.tags)
        review_note = raw.get("reviewNote") or record.raw.get("reviewNote") or record.review_note
        questions.append(
            DailyPushQuestion(
                id=record.id,
                zh=record.zh,
                hints=hints,
                reviewNote=review_note,
                tags=tags,
                difficulty=record.difficulty,
                referenceEn=record.reference_en,
            )
        )
    return questions, remaining
