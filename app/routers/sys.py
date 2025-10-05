from __future__ import annotations

import requests
from fastapi import APIRouter

from app.core.settings import get_settings
from app.llm import GEMINI_BASE, get_current_model

router = APIRouter()


@router.get("/healthz")
def healthz() -> dict:
    s = get_settings()
    api_key = s.GEMINI_API_KEY or s.GOOGLE_API_KEY
    if not api_key:
        return {"status": "no_key", "provider": "gemini"}
    try:
        r = requests.get(f"{GEMINI_BASE}/models?key={api_key}", timeout=10)
        if r.status_code // 100 == 2:
            return {"status": "ok", "provider": "gemini", "model": get_current_model()}
        return {"status": "auth_error", "provider": "gemini", "code": r.status_code}
    except Exception as e:
        return {"status": "error", "provider": "gemini", "message": str(e)}
