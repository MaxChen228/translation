from __future__ import annotations

import json
from typing import Any, Dict, Iterable

from fastapi import HTTPException

from app.schemas import CorrectRequest, CorrectResponse

ALLOWED_ERROR_TYPES = {"morphological", "syntactic", "lexical", "phonological", "pragmatic"}


def _coerce_mapping(obj: Any) -> Dict[str, Any]:
    if isinstance(obj, dict):
        return dict(obj)
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    raise TypeError(f"Unsupported error payload type: {type(obj)}")


def normalize_errors(raw_errors: Iterable[Any]) -> list[Dict[str, Any]]:
    import uuid

    normalized: list[Dict[str, Any]] = []
    invalid = []
    for idx, item in enumerate(list(raw_errors or [])):
        data = _coerce_mapping(item)
        err_type = str(data.get("type", "")).strip().lower()
        if err_type not in ALLOWED_ERROR_TYPES:
            invalid.append({"index": idx, "value": err_type})
        else:
            data["type"] = err_type
        data.pop("originalRange", None)
        data.pop("suggestionRange", None)
        data.pop("correctedRange", None)
        data["id"] = str(uuid.uuid4())
        normalized.append(data)
    if invalid:
        raise HTTPException(status_code=422, detail={"invalid_types": invalid, "allowed": sorted(ALLOWED_ERROR_TYPES)})
    return normalized


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
    if req.reviewNote:
        payload["reviewNote"] = req.reviewNote
        payload["suggestion"] = req.reviewNote  # backward compat for existing prompts
    if req.strictness:
        payload["strictness"] = req.strictness
    return json.dumps(payload, ensure_ascii=False)


def validate_correct_response(obj: dict) -> CorrectResponse:
    """Validate model JSON into CorrectResponse with server-side id assignment.

    - Enforce five error categories (lowercased)
    - Drop any range-like keys
    - Assign UUID for every error id
    """
    obj = dict(obj)
    obj["errors"] = normalize_errors(obj.get("errors") or [])
    return CorrectResponse.model_validate(obj)
