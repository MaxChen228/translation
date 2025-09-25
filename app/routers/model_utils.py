from __future__ import annotations

import json
from typing import Any

from fastapi import HTTPException

from app.providers.llm import LLMProvider


def _extract_detail(exc: ValueError, override: str | None) -> Any:
    """Best-effort decode detail payload emitted by provider.resolve_model."""
    payload = exc.args[0] if exc.args else None
    if isinstance(payload, dict):  # defensive: upstream might return dict already
        return payload
    if isinstance(payload, str):
        try:
            return json.loads(payload)
        except Exception:
            pass
    return {"invalid_model": str(override)}


def resolve_model_or_422(provider: LLMProvider, override: str | None) -> str:
    """Resolve model via provider; convert ValueError into FastAPI 422 response."""
    try:
        return provider.resolve_model(override)
    except ValueError as exc:
        detail = _extract_detail(exc, override)
        raise HTTPException(status_code=422, detail=detail) from exc
