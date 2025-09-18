from __future__ import annotations

import os
from typing import Dict


def _backend_base_dir() -> str:
    here = os.path.dirname(__file__)
    # app/ -> backend dir
    return os.path.abspath(os.path.join(here, ".."))


def content_dir() -> str:
    return os.path.abspath(os.path.join(_backend_base_dir(), os.environ.get("CONTENT_DIR", "data")))


def deck_debug_enabled() -> bool:
    return os.environ.get("DECK_DEBUG_LOG", "1").lower() in ("1", "true", "yes", "on")


def llm_generation_config() -> Dict[str, object]:
    def _float(name: str, default: float) -> float:
        v = os.environ.get(name)
        if v is None:
            return default
        try:
            return float(v)
        except Exception:
            return default

    def _int(name: str, default: int) -> int:
        v = os.environ.get(name)
        if v is None:
            return default
        try:
            return int(v)
        except Exception:
            return default

    return {
        "response_mime_type": "application/json",
        "temperature": _float("LLM_TEMPERATURE", 0.1),
        "topP": _float("LLM_TOP_P", 0.1),
        "topK": _int("LLM_TOP_K", 1),
        "maxOutputTokens": _int("LLM_MAX_OUTPUT_TOKENS", 320),
    }

