from __future__ import annotations

import json
import os
import time
from typing import Optional, Dict, Sequence, Mapping

import requests
from app.core.settings import get_settings
from app.core.logging import logger
from app.usage.models import LLMUsage


# Public constants
GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"


def _base_dir() -> str:
    # app/ -> backend directory
    here = os.path.dirname(__file__)
    return os.path.abspath(os.path.join(here, ".."))


def load_system_prompt() -> str:
    settings = get_settings()
    # Allow relative path (resolved against backend base), or absolute path
    path = settings.PROMPT_FILE or "prompt.txt"
    if not os.path.isabs(path):
        path = os.path.join(_base_dir(), path)
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read().strip()
            if not content:
                raise RuntimeError("prompt_file_empty")
            return content
    except Exception as e:
        raise RuntimeError(f"prompt_file_error: {e}")


def load_deck_prompt() -> str:
    settings = get_settings()
    path = settings.DECK_PROMPT_FILE or "prompt_deck.txt"
    if not os.path.isabs(path):
        path = os.path.join(_base_dir(), path)
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read().strip()
            if not content:
                raise RuntimeError("deck_prompt_file_empty")
            return content
    except Exception as e:
        raise RuntimeError(f"deck_prompt_file_error: {e}")


def _load_prompt(path: str, default_filename: str) -> str:
    if not path:
        path = default_filename
    if not os.path.isabs(path):
        path = os.path.join(_base_dir(), path)
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read().strip()
            if not content:
                raise RuntimeError(f"prompt_file_empty:{default_filename}")
            return content
    except Exception as e:  # pragma: no cover - configuration error path
        raise RuntimeError(f"prompt_file_error:{default_filename}:{e}")


def load_chat_turn_prompt() -> str:
    settings = get_settings()
    return _load_prompt(settings.CHAT_TURN_PROMPT_FILE or "prompt_chat_turn.txt", "prompt_chat_turn.txt")


def load_chat_research_prompt() -> str:
    settings = get_settings()
    return _load_prompt(settings.CHAT_RESEARCH_PROMPT_FILE or "prompt_chat_research.txt", "prompt_chat_research.txt")


def _env_model_defaults() -> tuple[str, set[str]]:
    settings = get_settings()
    gemini_model = settings.GEMINI_MODEL or "gemini-2.5-flash"
    allowed = settings.allowed_models_set()
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
    s = get_settings()
    return bool(s.GEMINI_API_KEY or s.GOOGLE_API_KEY)


def _gen_config() -> Dict[str, object]:
    # Centralized generation config from settings
    return get_settings().generation_config()



def call_gemini_json(
    system_prompt: str,
    user_content: str,
    *,
    model: Optional[str] = None,
    inline_parts: Optional[Sequence[Mapping[str, object]]] = None,
    timeout: int = 60,
) -> tuple[dict, LLMUsage]:
    s = get_settings()
    api_key = s.GEMINI_API_KEY or s.GOOGLE_API_KEY
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY/GOOGLE_API_KEY not set")
    chosen = (model or get_current_model()).strip()
    url = f"{GEMINI_BASE}/models/{chosen}:generateContent?key={api_key}"
    parts = [{"text": user_content}]
    inline_count = len(list(inline_parts or []))
    if inline_parts:
        for part in inline_parts:
            if part:
                parts.append(dict(part))
    payload = {
        "system_instruction": {"parts": [{"text": system_prompt}]},
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": _gen_config(),
    }

    mode = (s.LLM_LOG_MODE or "off").strip().lower()
    if mode in ("input", "both"):
        try:
            logger.info(
                "Gemini request",
                extra={
                    "event": "llm_request",
                    "direction": "input",
                    "model": chosen,
                    "endpoint": url,
                    "payload": payload,
                },
            )
        except Exception:
            pass
    started = time.perf_counter()
    r = requests.post(url, headers={"Content-Type": "application/json"}, json=payload, timeout=timeout)
    latency_ms = (time.perf_counter() - started) * 1000.0
    success = r.status_code // 100 == 2
    if not success:
        logger.warning(
            "Gemini call failed",
            extra={
                "event": "llm_call",
                "provider": "gemini",
                "model": chosen,
                "status": r.status_code,
                "latency_ms": latency_ms,
            },
        )
        raise RuntimeError(f"gemini_error status={r.status_code} body={r.text[:400]}")
    logger.info(
        "Gemini call ok",
        extra={
            "event": "llm_call",
            "provider": "gemini",
            "model": chosen,
            "status": r.status_code,
            "latency_ms": latency_ms,
        },
    )
    data = r.json()
    try:
        content = data["candidates"][0]["content"]["parts"][0]["text"]
    except Exception:
        raise RuntimeError(f"gemini_invalid_response: {json.dumps(data)[:400]}")
    parsed_obj: object | None = None
    usage_metadata = data.get("usageMetadata") or {}
    usage = LLMUsage(
        timestamp=time.time(),
        provider="gemini",
        api_kind="generateContent",
        model=chosen,
        api_endpoint=url,
        inline_parts=inline_count,
        prompt_chars=len(user_content),
        input_tokens=int(usage_metadata.get("promptTokenCount") or 0),
        output_tokens=int(usage_metadata.get("candidatesTokenCount") or 0),
        total_tokens=int(usage_metadata.get("totalTokenCount") or 0),
        latency_ms=latency_ms,
        status_code=r.status_code,
    )
    try:
        parsed_obj = json.loads(content)
        return parsed_obj, usage
    except Exception as e:
        raise RuntimeError(f"invalid_model_json: {e}\ncontent={content[:400]}")
    finally:
        if mode in ("output", "both"):
            try:
                logged_obj: object = parsed_obj if parsed_obj is not None else {"raw": content}
                extra = {
                    "event": "llm_response",
                    "direction": "output",
                    "model": chosen,
                    "endpoint": url,
                    "response": logged_obj,
                }
                if isinstance(logged_obj, dict):
                    state_value = logged_obj.get("state")
                    if state_value is not None:
                        extra["state"] = state_value
                    checklist_value = logged_obj.get("checklist")
                    if checklist_value is not None:
                        extra["checklist"] = checklist_value
                logger.info(
                    "Gemini response",
                    extra=extra,
                )
            except Exception:
                pass
