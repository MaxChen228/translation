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
from app.core.logging import logger

TURN_PROMPT = load_chat_turn_prompt()
RESEARCH_PROMPT = load_chat_research_prompt()


def _safe_dump(value, limit: int = 2000) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, default=str)[:limit]
    except Exception:
        return str(value)[:limit]


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
        logger.warning(
            "chat_turn_generate_error",
            exc_info=exc,
            extra={
                "model": req.model,
                "messages": _safe_dump(json.loads(payload) if payload else {}),
                "inline_parts": len(inline_parts),
            },
        )
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    response_payload = {
        "reply": _require_str(data, "reply"),
        "state": str(data.get("state", "gathering") or "gathering"),
        "checklist": data.get("checklist"),
    }
    try:
        return ChatTurnResponse.model_validate(response_payload)
    except Exception as exc:
        logger.warning(
            "chat_turn_invalid_response",
            extra={"payload": _safe_dump(data), "error": str(exc)},
        )
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
        logger.warning(
            "chat_research_generate_error",
            exc_info=exc,
            extra={
                "model": req.model,
                "messages": _safe_dump(json.loads(payload) if payload else {}),
                "inline_parts": len(inline_parts),
            },
        )
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    items = data.get("items")
    if not isinstance(items, list) or not items:
        logger.warning(
            "chat_research_missing_items",
            extra={"payload": _safe_dump(data)},
        )
        raise HTTPException(status_code=500, detail="chat_invalid_research_response:items_empty")

    normalized: list[dict[str, str]] = []
    for idx, raw in enumerate(items):
        if not isinstance(raw, dict):  # pragma: no cover - defensive
            logger.warning(
                "chat_research_item_not_object",
                extra={"index": idx, "payload": _safe_dump(data)},
            )
            raise HTTPException(status_code=500, detail=f"chat_invalid_research_item:{idx}")
        try:
            normalized.append(
                {
                    "term": _require_str(raw, "term"),
                    "explanation": _require_str(raw, "explanation"),
                    "context": _require_str(raw, "context"),
                    "type": _require_str(raw, "type", allow_empty=False),
                }
            )
        except HTTPException:
            logger.warning(
                "chat_research_item_missing_field",
                extra={"index": idx, "item": _safe_dump(raw, limit=1000)},
            )
            raise
        except Exception as exc:  # pragma: no cover
            logger.warning(
                "chat_research_item_error",
                extra={"index": idx, "item": _safe_dump(raw, limit=1000), "error": str(exc)},
            )
            raise HTTPException(status_code=500, detail=f"chat_invalid_research_item:{idx}:{exc}") from exc

    try:
        return ChatResearchResponse.model_validate({"items": normalized})
    except Exception as exc:
        logger.warning(
            "chat_research_invalid_response",
            extra={"normalized": _safe_dump(normalized), "error": str(exc)},
        )
        raise HTTPException(status_code=500, detail=f"chat_invalid_research_response:{exc}") from exc
