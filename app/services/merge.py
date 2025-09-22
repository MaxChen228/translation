from __future__ import annotations

import json
from typing import Any, Dict

from fastapi import HTTPException

from app.schemas import MergeErrorsRequest, MergeErrorResponse
from app.services.corrector import normalize_errors


def _encode_error(err: Any) -> Dict[str, Any]:
    if hasattr(err, "model_dump"):
        data = err.model_dump(exclude_none=True)
    elif isinstance(err, dict):
        data = {k: v for k, v in err.items() if v is not None}
    else:
        raise TypeError("Unsupported error payload")
    # 僅保留與語意相關的欄位
    data.pop("originalRange", None)
    data.pop("suggestionRange", None)
    data.pop("correctedRange", None)
    return data


def build_merge_user_content(req: MergeErrorsRequest) -> str:
    payload: Dict[str, Any] = {
        "zh": req.zh,
        "en": req.en,
        "corrected": req.corrected,
        "errors": [_encode_error(err) for err in req.errors],
    }
    if req.rationale:
        payload["rationale"] = req.rationale
    if req.deviceId:
        payload["deviceId"] = req.deviceId
    return json.dumps(payload, ensure_ascii=False)


def validate_merge_response(obj: Dict[str, Any]) -> MergeErrorResponse:
    if obj is None:
        raise HTTPException(status_code=422, detail="merge_empty_response")
    data = dict(obj)
    raw_error = data.get("error") or data.get("mergedError") or data
    normalized = normalize_errors([raw_error])
    if not normalized:
        raise HTTPException(status_code=422, detail="merge_result_missing_error")
    return MergeErrorResponse.model_validate({"error": normalized[0]})
