from __future__ import annotations

import asyncio
import json
import time
from typing import Callable, Dict, Mapping, Optional, Sequence, Union

import httpx

from app.core.http_client import get_http_client
from app.core.logging import logger
from app.core.settings import get_settings
from app.services.prompt_manager import get_prompt_config, read_prompt
from app.usage.models import LLMUsage


GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"

_PROMPT_CACHE: Dict[str, str] = {}


def reload_prompts() -> None:
    _PROMPT_CACHE.clear()


def _cache_prompt(key: str, loader: Callable[[], str]) -> str:
    if key not in _PROMPT_CACHE:
        _PROMPT_CACHE[key] = loader()
    return _PROMPT_CACHE[key]


def _load_prompt_by_id(prompt_id: str) -> str:
    config = get_prompt_config(prompt_id)
    return _cache_prompt(config.cache_key, lambda: read_prompt(prompt_id))


def load_system_prompt() -> str:
    return _load_prompt_by_id("system")


def load_deck_prompt() -> str:
    return _load_prompt_by_id("deck")


def load_chat_turn_prompt() -> str:
    return _load_prompt_by_id("chat_turn")


def load_chat_research_prompt() -> str:
    return _load_prompt_by_id("chat_research")


def load_merge_prompt() -> str:
    return _load_prompt_by_id("merge")


def load_flashcard_completion_prompt() -> str:
    return _load_prompt_by_id("flashcard_completion")


def _env_model_defaults() -> tuple[str, set[str]]:
    settings = get_settings()
    gemini_model = settings.GEMINI_MODEL or "gemini-2.5-flash"
    allowed = settings.allowed_models_set()
    return gemini_model, allowed


def get_current_model() -> str:
    m, _ = _env_model_defaults()
    return m


def allowed_models() -> set[str]:
    _, allowed = _env_model_defaults()
    return allowed


def resolve_model(override: Optional[str]) -> str:
    default, allowed = _env_model_defaults()
    if override is None or not str(override).strip():
        return default
    candidate = str(override).strip()
    if candidate in allowed:
        return candidate
    raise ValueError(json.dumps({"invalid_model": candidate, "allowed": sorted(allowed)}))


def has_api_key() -> bool:
    settings = get_settings()
    return bool(settings.GEMINI_API_KEY or settings.GOOGLE_API_KEY)


def _gen_config() -> Dict[str, object]:
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


async def call_gemini_json(
    system_prompt: str,
    user_content: str,
    *,
    model: Optional[str] = None,
    inline_parts: Optional[Sequence[Mapping[str, object]]] = None,
    timeout: Optional[Union[int, float]] = 60,
    max_retries: int = 2,
) -> tuple[dict, LLMUsage]:
    settings = get_settings()
    api_key = settings.GEMINI_API_KEY or settings.GOOGLE_API_KEY
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY/GOOGLE_API_KEY not set")

    chosen_model = (model or get_current_model()).strip()
    url = f"{GEMINI_BASE}/models/{chosen_model}:generateContent?key={api_key}"

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

    client = get_http_client()
    log_mode = (settings.LLM_LOG_MODE or "off").strip().lower()
    if log_mode in ("input", "both"):
        try:
            logger.info(
                "Gemini request",
                extra={
                    "event": "llm_request",
                    "direction": "input",
                    "model": chosen_model,
                    "endpoint": url,
                },
            )
        except Exception:
            pass

    retryable_status = {429, 500, 502, 503, 504}
    attempt = 0
    last_error: Optional[str] = None

    while attempt <= max_retries:
        started = time.perf_counter()
        try:
            request_timeout = timeout
            if timeout is None:
                request_timeout = httpx.Timeout(connect=10.0, read=None, write=None, pool=None)

            response = await client.post(
                url,
                headers={"Content-Type": "application/json"},
                json=payload,
                timeout=request_timeout,
            )
            latency_ms = (time.perf_counter() - started) * 1000.0
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            latency_ms = (time.perf_counter() - started) * 1000.0
            last_error = str(exc)
            logger.warning(
                "Gemini transport error",
                extra={
                    "event": "llm_call",
                    "provider": "gemini",
                    "model": chosen_model,
                    "status": getattr(getattr(exc, "response", None), "status_code", -1),
                    "latency_ms": latency_ms,
                    "attempt": attempt + 1,
                },
            )
            if attempt >= max_retries:
                raise RuntimeError(f"gemini_transport_error: {exc}") from exc
        else:
            if response.status_code // 100 == 2:
                logger.info(
                    "Gemini call ok",
                    extra={
                        "event": "llm_call",
                        "provider": "gemini",
                        "model": chosen_model,
                        "status": response.status_code,
                        "latency_ms": latency_ms,
                        "attempt": attempt + 1,
                    },
                )
                data = response.json()
                try:
                    content = data["candidates"][0]["content"]["parts"][0]["text"]
                except Exception as exc:
                    raise RuntimeError(f"gemini_invalid_response: {json.dumps(data)[:400]}") from exc

                try:
                    parsed_obj = json.loads(content)
                    usage_metadata = data.get("usageMetadata") or {}
                    sanitized_payload = _sanitize_payload_for_storage(payload)
                    response_payload = json.dumps(parsed_obj, ensure_ascii=False)
                    usage = LLMUsage(
                        timestamp=time.time(),
                        provider="gemini",
                        api_kind="generateContent",
                        model=chosen_model,
                        api_endpoint=url,
                        inline_parts=inline_count,
                        prompt_chars=len(user_content),
                        input_tokens=int(usage_metadata.get("promptTokenCount") or 0),
                        output_tokens=int(usage_metadata.get("candidatesTokenCount") or 0),
                        total_tokens=int(usage_metadata.get("totalTokenCount") or 0),
                        latency_ms=latency_ms,
                        status_code=response.status_code,
                        request_payload=sanitized_payload,
                        response_payload=response_payload,
                    )
                    if log_mode in ("output", "both"):
                        try:
                            logger.info(
                                "Gemini response",
                                extra={
                                    "event": "llm_response",
                                    "direction": "output",
                                    "model": chosen_model,
                                    "endpoint": url,
                                },
                            )
                        except Exception:
                            pass
                    return parsed_obj, usage
                except Exception as exc:
                    raise RuntimeError(f"invalid_model_json: {exc}\ncontent={content[:400]}") from exc

            last_error = response.text[:400]
            logger.warning(
                "Gemini call failed",
                extra={
                    "event": "llm_call",
                    "provider": "gemini",
                    "model": chosen_model,
                    "status": response.status_code,
                    "latency_ms": latency_ms,
                    "attempt": attempt + 1,
                },
            )
            if response.status_code not in retryable_status or attempt >= max_retries:
                raise RuntimeError(f"gemini_error status={response.status_code} body={last_error}")

        attempt += 1
        await asyncio.sleep(min(0.5 * attempt, 2.0))

    raise RuntimeError(f"gemini_error: {last_error or 'unknown error'}")
