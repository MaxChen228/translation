from __future__ import annotations

import json
import os
from typing import Optional, Dict

import requests
from app.config import llm_generation_config


# Public constants
GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"


def _base_dir() -> str:
    # app/ -> backend directory
    here = os.path.dirname(__file__)
    return os.path.abspath(os.path.join(here, ".."))


def load_system_prompt() -> str:
    default_path = os.path.join(_base_dir(), "prompt.txt")
    path = os.environ.get("PROMPT_FILE", default_path)
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read().strip()
            if not content:
                raise RuntimeError("prompt_file_empty")
            return content
    except Exception as e:
        raise RuntimeError(f"prompt_file_error: {e}")


def load_deck_prompt() -> str:
    default_path = os.path.join(_base_dir(), "prompt_deck.txt")
    path = os.environ.get("DECK_PROMPT_FILE", default_path)
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read().strip()
            if not content:
                raise RuntimeError("deck_prompt_file_empty")
            return content
    except Exception as e:
        raise RuntimeError(f"deck_prompt_file_error: {e}")


def _env_model_defaults() -> tuple[str, set[str]]:
    generic = os.environ.get("LLM_MODEL")
    gemini_model = os.environ.get("GEMINI_MODEL", generic or "gemini-2.5-flash")
    allowed_env = os.environ.get("ALLOWED_MODELS")
    if allowed_env:
        allowed = {m.strip() for m in allowed_env.split(",") if m.strip()}
    else:
        allowed = {"gemini-2.5-pro", "gemini-2.5-flash"}
    return gemini_model, allowed


def get_current_model() -> str:
    m, _ = _env_model_defaults()
    return m


def allowed_models() -> set[str]:
    _, a = _env_model_defaults()
    return a


def resolve_model(override: Optional[str]) -> str:
    default, allowed = _env_model_defaults()
    if override is None or not str(override).strip():
        return default
    m = str(override).strip()
    if m in allowed:
        return m
    raise ValueError(json.dumps({"invalid_model": m, "allowed": sorted(allowed)}))


def has_api_key() -> bool:
    return bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))


def _gen_config() -> Dict[str, object]:
    # Delegate to centralized config for easier tuning/testing
    return llm_generation_config()


def call_gemini_json(system_prompt: str, user_content: str, *, model: Optional[str] = None, timeout: int = 60) -> dict:
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY/GOOGLE_API_KEY not set")
    chosen = (model or get_current_model()).strip()
    url = f"{GEMINI_BASE}/models/{chosen}:generateContent?key={api_key}"
    payload = {
        "system_instruction": {"parts": [{"text": system_prompt}]},
        "contents": [{"role": "user", "parts": [{"text": user_content}]}],
        "generationConfig": _gen_config(),
    }
    r = requests.post(url, headers={"Content-Type": "application/json"}, json=payload, timeout=timeout)
    if r.status_code // 100 != 2:
        raise RuntimeError(f"gemini_error status={r.status_code} body={r.text[:400]}")
    data = r.json()
    try:
        content = data["candidates"][0]["content"]["parts"][0]["text"]
    except Exception:
        raise RuntimeError(f"gemini_invalid_response: {json.dumps(data)[:400]}")
    try:
        return json.loads(content)
    except Exception as e:
        raise RuntimeError(f"invalid_model_json: {e}\ncontent={content[:400]}")
