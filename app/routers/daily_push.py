from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.schemas import DailyPushPullRequest, DailyPushPullResponse
from app.services.daily_push import fetch_daily_push_questions

router = APIRouter(prefix="/daily_push", tags=["daily_push"])


@router.post("/pull", response_model=DailyPushPullResponse)
def pull_daily_questions(payload: DailyPushPullRequest) -> DailyPushPullResponse:
    device_id = payload.deviceId.strip()
    if not device_id:
        raise HTTPException(status_code=422, detail="deviceId_required")

    question_date = payload.date
    try:
        questions, remaining = fetch_daily_push_questions(
            question_date=question_date,
            count=payload.count,
            device_id=device_id,
            force_reset=payload.forceReset,
        )
    except Exception as exc:  # pragma: no cover - defensive logging
        raise HTTPException(status_code=500, detail=f"daily_push_failed:{exc}") from exc

    return DailyPushPullResponse(
        requested=payload.count,
        delivered=len(questions),
        remaining=remaining,
        questions=questions,
    )
