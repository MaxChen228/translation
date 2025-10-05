from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Dict, List, Optional

from fastapi import HTTPException

from app.core.logging import logger
from app.llm import (
    load_chat_research_prompt,
    load_chat_turn_prompt,
)
from app.providers.llm import LLMProvider
from app.schemas import (
    ChatMessage,
    ChatResearchRequest,
    ChatResearchResponse,
    ChatTurnRequest,
    ChatTurnResponse,
)
from app.usage.recorder import record_usage


def _safe_dump(value, limit: int = 2000) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, default=str)[:limit]
    except Exception:
        return str(value)[:limit]


def _serialize_messages(messages: List[ChatMessage]) -> tuple[str, List[Dict[str, object]]]:
    serialized: list[dict] = []
    inline_parts: list[Dict[str, object]] = []

    for msg in messages:
        base: Dict[str, object] = {"role": msg.role, "content": msg.content}
        atts: List[Dict[str, object]] = []
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


def _first_non_empty_line(text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return ""


def _summary_list(text: str) -> str:
    lines: list[str] = []
    for raw in text.splitlines():
        stripped = raw.strip()
        if not stripped:
            continue
        if stripped.startswith(('-', '*')):
            stripped = stripped.lstrip('-* ').strip()
        if stripped.startswith('##'):
            continue
        if stripped.startswith('>'):
            stripped = stripped.lstrip('>').strip()
        if stripped:
            lines.append(stripped)
        if len(lines) >= 3:
            break
    if not lines:
        first_line = _first_non_empty_line(text)
        cleaned = first_line.lstrip('-*# ').strip()
        lines = [cleaned or "已回覆您的請求，有任何需要請告訴我。"]
    return "\n".join(f"- {line}" for line in lines)


def _normalize_markdown_reply(reply: str) -> str:
    stripped = reply.strip()
    if not stripped:
        return (
            "## 回覆摘要\n"
            "- 目前沒有可以分享的資訊\n\n"
            "## 詳細說明\n"
            "尚未取得有效內容，請提供更多線索。"
        )

    has_summary = "## 回覆摘要" in stripped
    has_detail = "## 詳細說明" in stripped

    if has_summary and has_detail:
        return stripped

    if not has_summary and not has_detail:
        summary = _summary_list(stripped)
        return (
            f"## 回覆摘要\n{summary}\n\n"
            f"## 詳細說明\n{stripped}"
        )

    if has_summary and not has_detail:
        return (
            f"{stripped}\n\n"
            "## 詳細說明\n"
            "上述摘要即為目前掌握的資訊，若需要更多細節請提供補充資料。"
        ).strip()

    if not has_summary and has_detail:
        summary = _summary_list(stripped)
        return (
            f"## 回覆摘要\n{summary}\n\n"
            f"{stripped}"
        ).strip()

    return stripped


async def run_turn(req: ChatTurnRequest, provider: LLMProvider, *, device_id: str, route: str) -> ChatTurnResponse:
    payload, inline_parts = _serialize_messages(req.messages)
    try:
        system_prompt = load_chat_turn_prompt()
        data, usage = await provider.generate_json(
            system_prompt=system_prompt,
            user_content=payload,
            model=req.model,
            inline_parts=inline_parts,
        )
        record_usage(usage, route=route, device_id=device_id)
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
        "reply": _normalize_markdown_reply(_require_str(data, "reply")),
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


async def run_research(
    req: ChatResearchRequest,
    provider: LLMProvider,
    *,
    device_id: str,
    route: str,
) -> ChatResearchResponse:
    payload, inline_parts = _serialize_messages(req.messages)
    try:
        system_prompt = load_chat_research_prompt()
        data, usage = await provider.generate_json(
            system_prompt=system_prompt,
            user_content=payload,
            model=req.model,
            inline_parts=inline_parts,
            timeout=90,
        )
        record_usage(usage, route=route, device_id=device_id)
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

    raw_name = data.get("deckName") or data.get("name")
    if not isinstance(raw_name, str) or not raw_name.strip():
        deck_name = "AI Generated Deck"
    else:
        deck_name = raw_name.strip()

    cards = data.get("cards")
    if not isinstance(cards, list) or not cards:
        logger.warning(
            "chat_research_missing_cards",
            extra={"payload": _safe_dump(data)},
        )
        raise HTTPException(status_code=500, detail="chat_invalid_research_response:cards_empty")

    normalized_cards: list[dict[str, Optional[str]]] = []
    for idx, raw in enumerate(cards):
        if not isinstance(raw, dict):  # pragma: no cover - defensive
            logger.warning(
                "chat_research_card_not_object",
                extra={"index": idx, "payload": _safe_dump(data)},
            )
            raise HTTPException(status_code=500, detail=f"chat_invalid_research_card:{idx}")
        try:
            front = _require_str(raw, "front")
            back = _require_str(raw, "back")
            front_note = raw.get("frontNote")
            back_note = raw.get("backNote")
            if front_note is not None and not isinstance(front_note, str):
                raise ValueError("frontNote must be string")
            if back_note is not None and not isinstance(back_note, str):
                raise ValueError("backNote must be string")
            normalized_cards.append(
                {
                    "front": front.strip(),
                    "back": back.strip(),
                    "frontNote": front_note.strip() if isinstance(front_note, str) and front_note.strip() else None,
                    "backNote": back_note.strip() if isinstance(back_note, str) and back_note.strip() else None,
                }
            )
        except HTTPException:
            logger.warning(
                "chat_research_card_missing_field",
                extra={"index": idx, "card": _safe_dump(raw, limit=1000)},
            )
            raise
        except Exception as exc:  # pragma: no cover
            logger.warning(
                "chat_research_card_error",
                extra={"index": idx, "card": _safe_dump(raw, limit=1000), "error": str(exc)},
            )
            raise HTTPException(status_code=500, detail=f"chat_invalid_research_card:{idx}:{exc}") from exc

    result_payload = {
        "deckName": deck_name,
        "generatedAt": datetime.now(timezone.utc),
        "cards": normalized_cards,
    }

    try:
        return ChatResearchResponse.model_validate(result_payload)
    except Exception as exc:
        logger.warning(
            "chat_research_invalid_response",
            extra={"normalized": _safe_dump(result_payload), "error": str(exc)},
        )
        raise HTTPException(status_code=500, detail=f"chat_invalid_research_response:{exc}") from exc
