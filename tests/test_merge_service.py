from __future__ import annotations

import json
from uuid import UUID

from app.schemas import ErrorDTO, ErrorHintsDTO, MergeErrorsRequest
from app.services.merge import build_merge_user_content, validate_merge_response


def make_error(span: str, type_: str = "lexical") -> ErrorDTO:
    return ErrorDTO(
        span=span,
        type=type_,
        explainZh="說明",
        suggestion="修正版",
        hints=ErrorHintsDTO(before="a ", after=" b", occurrence=1),
    )


def test_build_merge_user_content_contains_core_fields():
    req = MergeErrorsRequest(
        zh="中文",
        en="user text",
        corrected="corrected",
        errors=[make_error("foo"), make_error("bar", "syntactic")],
        rationale="合併成慣用語",
        deviceId="device-1",
    )
    payload = build_merge_user_content(req)
    data = json.loads(payload)
    assert data["zh"] == "中文"
    assert data["en"] == "user text"
    assert len(data["errors"]) == 2
    assert data["errors"][0]["span"] == "foo"
    assert data["rationale"] == "合併成慣用語"
    assert data["deviceId"] == "device-1"


def test_validate_merge_response_normalizes_error():
    raw = {
        "error": {
            "span": "foo",
            "type": "lexical",
            "explainZh": "explain",
            "suggestion": "bar",
        }
    }
    resp = validate_merge_response(raw)
    assert resp.error.type == "lexical"
    assert resp.error.span == "foo"
    # ensure UUID assigned
    UUID(resp.error.id)


def test_validate_merge_response_fallback_keys():
    raw = {
        "span": "foo",
        "type": "lexical",
        "explainZh": "explain",
        "suggestion": "bar",
    }
    resp = validate_merge_response(raw)
    UUID(resp.error.id)
