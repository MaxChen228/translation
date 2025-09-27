from __future__ import annotations

import json
import os
import time
import uuid
from typing import Dict

from fastapi import HTTPException

from app.llm import call_gemini_json
from app.schemas import DeckMakeRequest, DeckMakeResponse, DeckCard
from app.core.settings import get_settings
from app.usage.recorder import record_usage


def _deck_debug_enabled() -> bool:
    return get_settings().deck_debug_enabled()


def _deck_debug_write(payload: Dict):
    if not _deck_debug_enabled():
        return
    try:
        here = os.path.dirname(__file__)
        base = os.path.abspath(os.path.join(here, "..", ".."))
        log_dir = os.path.join(base, "_test_logs")
        os.makedirs(log_dir, exist_ok=True)
        ts = time.strftime("%Y%m%d_%H%M%S")
        fn = f"deck_{ts}_{uuid.uuid4().hex[:8]}.json"
        path = os.path.join(log_dir, fn)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


async def make_deck_from_request(
    req: DeckMakeRequest,
    deck_prompt: str,
    chosen_model: str,
    *,
    device_id: str = "unknown",
    route: str = "",
) -> DeckMakeResponse:
    # Compact user JSON to save tokens but retain all knowledge points
    def _clean_str(value: object | None) -> str | None:
        if value is None:
            return None
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        stripped = str(value).strip()
        return stripped or None

    knowledge_points: list[Dict[str, object]] = []
    for idx, it in enumerate(req.items):
        data = it.model_dump(mode="json", exclude_none=True)
        entry: Dict[str, object] = {
            "index": idx + 1,
        }

        title = _clean_str(getattr(it, "title", None)) or _clean_str(getattr(it, "suggestion", None))
        explanation = _clean_str(getattr(it, "explanation", None)) or _clean_str(getattr(it, "explainZh", None))
        example = _clean_str(getattr(it, "example", None)) or _clean_str(getattr(it, "en", None))
        note = _clean_str(getattr(it, "note", None))
        source = _clean_str(getattr(it, "source", None))

        if title:
            entry["title"] = title
        if explanation:
            entry["explanation"] = explanation
        if example:
            entry["example"] = example
        if note:
            entry["note"] = note
        if source:
            entry["source"] = source

        tags = getattr(it, "tags", None)
        if tags:
            entry["tags"] = tags

        if data:
            entry["raw"] = data

        # Even if some fields are missing, keep the knowledge point so LLM sees everything
        if len(entry) == 1:  # only index present and nothing else meaningful
            continue
        knowledge_points.append(entry)

    if not knowledge_points:
        raise HTTPException(status_code=422, detail="deck_items_empty")

    compact = {"name": req.name or "未命名", "items": knowledge_points}
    user_content = json.dumps(compact, ensure_ascii=False)

    debug_info: Dict[str, object] = {
        "ts": time.time(),
        "provider": "gemini",
        "model": chosen_model,
        "system_prompt": deck_prompt,
        "user_content": user_content,
        "items_in": len(req.items),
        "items_compacted": len(knowledge_points),
    }
    try:
        obj, usage = await call_gemini_json(
            deck_prompt,
            user_content,
            model=chosen_model,
            timeout=None,
        )
    except Exception as e:
        debug_info.update({"json_error": str(e)})
        _deck_debug_write(debug_info)
        raise
    usage_with_context = record_usage(usage, route=route, device_id=device_id)
    # Validate shape
    if not isinstance(obj, dict) or not isinstance(obj.get("cards"), list):
        debug_info.update({"parsed_obj_head": json.dumps(obj, ensure_ascii=False)[:800]})
        _deck_debug_write(debug_info)
        raise HTTPException(status_code=422, detail="deck_json_invalid_shape")
    # Ensure name falls back to request
    name = (obj.get("name") or req.name or "未命名").strip()
    cards_raw = obj.get("cards") or []
    cards = []
    for c in cards_raw:
        # 支援 camelCase 與 snake_case 鍵名
        fron = (c.get("front") or c.get("zh") or "").strip()
        back = (c.get("back") or c.get("en") or "").strip()
        if not fron or not back:
            continue
        f_note_raw = c.get("frontNote") or c.get("front_note") or ""
        b_note_raw = c.get("backNote") or c.get("back_note") or ""
        f_note = f_note_raw.strip() or None
        b_note = b_note_raw.strip() or None
        cards.append(DeckCard(front=fron, back=back, frontNote=f_note, backNote=b_note))
    debug_info.update({
        "cards_parsed": len(cards),
        "cards_raw_len": len(cards_raw),
        "name_resolved": name,
        "usage": usage_with_context.model_dump(),
    })
    _deck_debug_write(debug_info)
    if not cards:
        raise HTTPException(status_code=422, detail="deck_cards_empty")
    return DeckMakeResponse(name=name, cards=cards)
