from __future__ import annotations

import json
from typing import Optional

from fastapi import HTTPException

from app.llm import (
    load_chat_turn_prompt,
    load_chat_research_prompt,
)
from app.providers.llm import LLMProvider
from app.schemas import (
    ChatTurnRequest,
    ChatTurnResponse,
    ChatResearchRequest,
    ChatResearchResponse,
)
from app.services.corrector import normalize_errors

TURN_PROMPT = load_chat_turn_prompt()
RESEARCH_PROMPT = load_chat_research_prompt()


def _serialize_messages(messages) -> str:
    data = [m.model_dump() if hasattr(m, "model_dump") else dict(m) for m in messages]
    return json.dumps({"messages": data}, ensure_ascii=False)


def _require_str(obj: dict, key: str, *, allow_empty: bool = False) -> str:
    value = obj.get(key)
    if not isinstance(value, str):
        raise HTTPException(status_code=500, detail=f"chat_missing_field:{key}")
    if not allow_empty and not value.strip():
        raise HTTPException(status_code=500, detail=f"chat_empty_field:{key}")
    return value


def run_turn(req: ChatTurnRequest, provider: LLMProvider) -> ChatTurnResponse:
    payload = _serialize_messages(req.messages)
    try:
        data = provider.generate_json(
            system_prompt=TURN_PROMPT,
            user_content=payload,
            model=req.model,
        )
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover - passthrough to HTTP layer
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    response_payload = {
        "reply": _require_str(data, "reply"),
        "state": str(data.get("state", "gathering") or "gathering"),
        "checklist": data.get("checklist"),
    }
    try:
        return ChatTurnResponse.model_validate(response_payload)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"chat_invalid_turn_response:{exc}") from exc


def run_research(req: ChatResearchRequest, provider: LLMProvider) -> ChatResearchResponse:
    payload = _serialize_messages(req.messages)
    try:
        data = provider.generate_json(
            system_prompt=RESEARCH_PROMPT,
            user_content=payload,
            model=req.model,
            timeout=90,
        )
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    errors = normalize_errors(data.get("errors") or [])
    response_payload = {
        "title": _require_str(data, "title"),
        "summary": _require_str(data, "summary"),
        "sourceZh": data.get("sourceZh"),
        "attemptEn": data.get("attemptEn"),
        "correctedEn": _require_str(data, "correctedEn", allow_empty=True),
        "errors": errors,
    }
    try:
        return ChatResearchResponse.model_validate(response_payload)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"chat_invalid_research_response:{exc}") from exc
