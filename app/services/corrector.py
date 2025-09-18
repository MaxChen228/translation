from __future__ import annotations

import json
from typing import Dict

from app.schemas import CorrectRequest, CorrectResponse


ALLOWED_ERROR_TYPES = {"morphological", "syntactic", "lexical", "phonological", "pragmatic"}


def build_user_content(req: CorrectRequest) -> str:
    """Pack CorrectRequest into compact JSON string for LLM input.

    Only include present fields to reduce tokens.
    """
    payload: Dict[str, object] = {"zh": req.zh, "en": req.en}
    if req.bankItemId:
        payload["bankItemId"] = req.bankItemId
    if req.deviceId:
        payload["deviceId"] = req.deviceId
    if req.hints:
        payload["hints"] = [h.model_dump() if hasattr(h, "model_dump") else dict(h) for h in req.hints]
    if req.suggestion:
        payload["suggestion"] = req.suggestion
    return json.dumps(payload, ensure_ascii=False)


def validate_correct_response(obj: dict) -> CorrectResponse:
    """Validate model JSON into CorrectResponse with server-side id assignment.

    - Enforce five error categories (lowercased)
    - Drop any range-like keys
    - Assign UUID for every error id
    """
    import uuid

    errs = obj.get("errors") or []
    invalid = []
    for idx, e in enumerate(errs):
        t = (e.get("type") or "").strip().lower()
        if t not in ALLOWED_ERROR_TYPES:
            invalid.append({"index": idx, "value": t})
        else:
            e["type"] = t
        e.pop("originalRange", None)
        e.pop("suggestionRange", None)
        e.pop("correctedRange", None)
        e["id"] = str(uuid.uuid4())
    if invalid:
        from fastapi import HTTPException

        raise HTTPException(status_code=422, detail={"invalid_types": invalid, "allowed": sorted(ALLOWED_ERROR_TYPES)})
    return CorrectResponse.model_validate(obj)

