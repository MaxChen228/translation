from __future__ import annotations

import json
import os
import time
from typing import Optional, Dict, Sequence, Mapping, Callable

import requests
from app.core.settings import get_settings
from app.core.logging import logger
from app.usage.models import LLMUsage


# Public constants
GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"

_PROMPT_CACHE: Dict[str, str] = {}


def reload_prompts() -> None:
    """Clear in-memory prompt cache so next access hits the filesystem."""
    _PROMPT_CACHE.clear()


def _cache_prompt(key: str, loader: Callable[[], str]) -> str:
    if key not in _PROMPT_CACHE:
        _PROMPT_CACHE[key] = loader()
    return _PROMPT_CACHE[key]


def _base_dir() -> str:
    # app/ -> backend directory
    here = os.path.dirname(__file__)
    return os.path.abspath(os.path.join(here, ".."))


def load_system_prompt() -> str:
    def _loader() -> str:
        settings = get_settings()
        path = settings.PROMPT_FILE or "prompt.txt"
        if not os.path.isabs(path):
            path = os.path.join(_base_dir(), path)
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read().strip()
        except Exception as e:
            raise RuntimeError(f"prompt_file_error: {e}")
        if not content:
            raise RuntimeError("prompt_file_empty")
        return content

    return _cache_prompt("system_prompt", _loader)


def load_deck_prompt() -> str:
    def _loader() -> str:
        settings = get_settings()
        path = settings.DECK_PROMPT_FILE or "prompt_deck.txt"
        if not os.path.isabs(path):
            path = os.path.join(_base_dir(), path)
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read().strip()
        except Exception as e:
            raise RuntimeError(f"deck_prompt_file_error: {e}")
        if not content:
            raise RuntimeError("deck_prompt_file_empty")
        return content

    return _cache_prompt("deck_prompt", _loader)


def _load_prompt(path: str, default_filename: str, *, cache_key: str) -> str:
    def _loader() -> str:
        resolved = path or default_filename
        if not os.path.isabs(resolved):
            resolved = os.path.join(_base_dir(), resolved)
        try:
            with open(resolved, "r", encoding="utf-8") as f:
                content = f.read().strip()
        except Exception as e:  # pragma: no cover - configuration error path
            raise RuntimeError(f"prompt_file_error:{default_filename}:{e}")
        if not content:
            raise RuntimeError(f"prompt_file_empty:{default_filename}")
        return content

    return _cache_prompt(cache_key, _loader)


def load_chat_turn_prompt() -> str:
    settings = get_settings()
    return _load_prompt(
        settings.CHAT_TURN_PROMPT_FILE or "prompt_chat_turn.txt",
        "prompt_chat_turn.txt",
        cache_key="chat_turn_prompt",
    )


def load_chat_research_prompt() -> str:
    settings = get_settings()
    return _load_prompt(
        settings.CHAT_RESEARCH_PROMPT_FILE or "prompt_chat_research.txt",
        "prompt_chat_research.txt",
        cache_key="chat_research_prompt",
    )


def load_merge_prompt() -> str:
    settings = get_settings()
    return _load_prompt(
        getattr(settings, "MERGE_PROMPT_FILE", None) or "prompt_merge.txt",
        "prompt_merge.txt",
        cache_key="merge_prompt",
    )


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


def _sanitize_payload_for_storage(payload: Dict[str, object]) -> str:
    try:
        sanitized = json.loads(json.dumps(payload))
        contents = sanitized.get("contents", [])
        if isinstance(contents, list):
            for content in contents:
                parts = content.get("parts") if isinstance(content, dict) else None
                if isinstance(parts, list):
                    for part in parts:
                        if isinstance(part, dict) and "inline_data" in part:
                            inline = part.get("inline_data")
                            if isinstance(inline, dict) and "data" in inline:
                                new_inline = dict(inline)
                                new_inline["data"] = "<inline_data omitted>"
                                part["inline_data"] = new_inline
        return json.dumps(sanitized, ensure_ascii=False)
    except Exception:
        try:
            return json.dumps(payload, ensure_ascii=False)
        except Exception:
            return ""

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
    try:
        parsed_obj = json.loads(content)
        usage_metadata = data.get("usageMetadata") or {}
        sanitized_payload = _sanitize_payload_for_storage(payload)
        response_payload = json.dumps(parsed_obj, ensure_ascii=False)
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
            request_payload=sanitized_payload,
            response_payload=response_payload,
        )
        return parsed_obj, usage
    except Exception as e:
        raise RuntimeError(f"invalid_model_json: {e}\ncontent={content[:400]}")
    finally:
        if mode in ("output", "both"):
            try:
                logger.info(
                    "Gemini response",
                    extra={
                        "event": "llm_response",
                        "direction": "output",
                        "model": chosen,
                        "endpoint": url,
                    },
                )
            except Exception:
                pass
