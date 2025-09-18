from __future__ import annotations

import os
import requests
from fastapi import APIRouter

from app.llm import GEMINI_BASE, get_current_model


router = APIRouter()


@router.get("/healthz")
def healthz() -> dict:
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        return {"status": "no_key", "provider": "gemini"}
    try:
        r = requests.get(f"{GEMINI_BASE}/models?key={api_key}", timeout=10)
        if r.status_code // 100 == 2:
            return {"status": "ok", "provider": "gemini", "model": get_current_model()}
        return {"status": "auth_error", "provider": "gemini", "code": r.status_code}
    except Exception as e:
        return {"status": "error", "provider": "gemini", "message": str(e)}

