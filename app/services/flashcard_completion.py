from __future__ import annotations

import json
import time
from typing import Any, Dict

from fastapi import HTTPException

from app.llm import load_flashcard_completion_prompt
from app.providers.llm import LLMProvider
from app.schemas import (
    FlashcardCompletionCard,
    FlashcardCompletionRequest,
    FlashcardCompletionResponse,
)
from app.usage.recorder import record_usage


class FlashcardCompletionError(RuntimeError):
    pass


def _normalize_card(payload: Dict[str, Any]) -> FlashcardCompletionCard:
    card_payload = payload
    if "card" in payload and isinstance(payload["card"], dict):
        card_payload = payload["card"]

    def pick(key: str, *aliases: str) -> str | None:
        for k in (key, *aliases):
            if k in card_payload:
                value = card_payload[k]
                if value is None:
                    return None
                if isinstance(value, str):
                    trimmed = value.strip()
                    return trimmed if trimmed else None
        return None

    front = pick("front", "zh")
    back = pick("back", "en")
    if not front or not back:
        raise FlashcardCompletionError("missing_front_or_back")

    front_note = pick("frontNote", "front_note", "zh_note")
    back_note = pick("backNote", "back_note", "en_note")

    return FlashcardCompletionCard(
        front=front,
        frontNote=front_note,
        back=back.replace("\n", " ").strip(),
        backNote=back_note,
    )


async def complete_flashcard(
    req: FlashcardCompletionRequest,
    *,
    provider: LLMProvider,
    chosen_model: str,
    device_id: str,
    route: str,
) -> FlashcardCompletionResponse:
    card = req.card
    if not card.front or not card.front.strip():
        raise HTTPException(status_code=422, detail="front_empty")

    system_prompt = load_flashcard_completion_prompt()

    payload = {
        "card": {
            "front": card.front.strip(),
            "frontNote": (card.frontNote or "").strip() or None,
            "back": (card.back or "").strip() or None,
            "backNote": (card.backNote or "").strip() or None,
        },
        "instruction": (req.instruction or "").strip() or None,
        "deckName": (req.deckName or "").strip() or None,
    }

    user_content = json.dumps(payload, ensure_ascii=False)

    debug_info: Dict[str, Any] = {
        "ts": time.time(),
        "route": route,
        "device_id": device_id,
        "model": chosen_model,
        "payload": payload,
    }

    try:
        raw, usage = await provider.generate_json(system_prompt, user_content, model=chosen_model)
    except Exception as exc:  # pragma: no cover - provider errors already covered elsewhere
        debug_info["error"] = str(exc)
        raise HTTPException(status_code=500, detail="llm_call_failed") from exc

    record_usage(usage, route=route, device_id=device_id)

    if not isinstance(raw, dict):
        raise HTTPException(status_code=422, detail="llm_invalid_shape")

    try:
        normalized = _normalize_card(raw)
    except FlashcardCompletionError as exc:
        debug_info["invalid_payload"] = raw
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return FlashcardCompletionResponse(**normalized.model_dump())
