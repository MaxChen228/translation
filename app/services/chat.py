from __future__ import annotations

import json
from typing import Optional, List, Dict

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
    ChatMessage,
)
from app.services.corrector import normalize_errors

TURN_PROMPT = load_chat_turn_prompt()
RESEARCH_PROMPT = load_chat_research_prompt()


def _serialize_messages(messages: List[ChatMessage]) -> tuple[str, List[Dict[str, object]]]:
    serialized: list[dict] = []
    inline_parts: list[Dict[str, object]] = []

    for msg in messages:
        base = {"role": msg.role, "content": msg.content}
        atts = []
        for attachment in msg.attachments or []:
            if attachment.type != "image":
                continue
            data = (attachment.data or "").strip()
            if not data:
                continue
            index = len(inline_parts) + 1
            inline_parts.append(
                {
                    "inline_data": {
                        "data": data,
                        "mime_type": attachment.mimeType,
                    }
                }
            )
            placeholder = {
                "type": attachment.type,
                "mimeType": attachment.mimeType,
                "index": index,
            }
            atts.append(placeholder)
        if atts:
            base["attachments"] = atts
        serialized.append(base)

    return json.dumps({"messages": serialized}, ensure_ascii=False), inline_parts


def _require_str(obj: dict, key: str, *, allow_empty: bool = False) -> str:
    value = obj.get(key)
    if not isinstance(value, str):
        raise HTTPException(status_code=500, detail=f"chat_missing_field:{key}")
    if not allow_empty and not value.strip():
        raise HTTPException(status_code=500, detail=f"chat_empty_field:{key}")
    return value


def run_turn(req: ChatTurnRequest, provider: LLMProvider) -> ChatTurnResponse:
    payload, inline_parts = _serialize_messages(req.messages)
    try:
        data = provider.generate_json(
            system_prompt=TURN_PROMPT,
            user_content=payload,
            model=req.model,
            inline_parts=inline_parts,
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
    payload, inline_parts = _serialize_messages(req.messages)
    try:
        data = provider.generate_json(
            system_prompt=RESEARCH_PROMPT,
            user_content=payload,
            model=req.model,
            inline_parts=inline_parts,
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
