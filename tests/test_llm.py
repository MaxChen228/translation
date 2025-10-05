import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx
import pytest

from app import llm

pytestmark = pytest.mark.anyio


class DummySettings:
    def __init__(self, **overrides):
        self.GEMINI_API_KEY = overrides.get("GEMINI_API_KEY", "key-123")
        self.GOOGLE_API_KEY = overrides.get("GOOGLE_API_KEY")
        self.GEMINI_MODEL = overrides.get("GEMINI_MODEL", "gemini-default")
        self._allowed = overrides.get("allowed", {"gemini-default", "gemini-alt"})
        self._config = overrides.get("config", {"temperature": 0.1})
        self.LLM_LOG_MODE = overrides.get("LLM_LOG_MODE", "off")
        self.LLM_LOG_PRETTY = overrides.get("LLM_LOG_PRETTY", True)

    def allowed_models_set(self) -> set[str]:
        return set(self._allowed)

    def generation_config(self) -> dict:
        return dict(self._config)


@pytest.fixture(autouse=True)
def clear_prompt_cache():
    llm.reload_prompts()
    yield
    llm.reload_prompts()


@pytest.fixture
def anyio_backend():
    return "asyncio"


def test_load_prompt_caches(monkeypatch):
    calls = []

    def fake_config(prompt_id: str):
        return SimpleNamespace(cache_key=f"cache:{prompt_id}")

    def fake_read(prompt_id: str):
        calls.append(prompt_id)
        return f"prompt:{prompt_id}"

    monkeypatch.setattr(llm, "get_prompt_config", fake_config)
    monkeypatch.setattr(llm, "read_prompt", fake_read)

    first = llm.load_system_prompt()
    second = llm.load_system_prompt()
    assert first == second == "prompt:system"
    assert calls == ["system"]

    deck = llm.load_deck_prompt()
    assert deck == "prompt:deck"
    assert calls == ["system", "deck"]


def test_resolve_model_with_override(monkeypatch):
    monkeypatch.setattr(llm, "get_settings", lambda: DummySettings())
    assert llm.resolve_model(" gemini-alt ") == "gemini-alt"
    with pytest.raises(ValueError) as exc:
        llm.resolve_model("unknown")
    error_payload = json.loads(str(exc.value))
    assert error_payload["invalid_model"] == "unknown"
    assert "gemini-alt" in error_payload["allowed"]


def test_has_api_key(monkeypatch):
    monkeypatch.setattr(llm, "get_settings", lambda: DummySettings(GEMINI_API_KEY="", GOOGLE_API_KEY=""))
    assert llm.has_api_key() is False
    monkeypatch.setattr(llm, "get_settings", lambda: DummySettings(GEMINI_API_KEY="abc"))
    assert llm.has_api_key() is True


async def test_call_gemini_json_success(monkeypatch):
    settings = DummySettings(LLM_LOG_MODE="both", config={"temperature": 0.5})
    monkeypatch.setattr(llm, "get_settings", lambda: settings)

    response_payload = {"result": "ok"}
    usage_metadata = {
        "promptTokenCount": 10,
        "candidatesTokenCount": 4,
        "totalTokenCount": 14,
    }
    fake_response = SimpleNamespace(
        status_code=200,
        json=lambda: {
            "candidates": [{"content": {"parts": [{"text": json.dumps(response_payload)}]}}],
            "usageMetadata": usage_metadata,
        },
        text="OK",
    )

    client = SimpleNamespace(post=AsyncMock(return_value=fake_response))
    monkeypatch.setattr(llm, "get_http_client", lambda: client)

    fake_logger = Mock()
    monkeypatch.setattr(llm, "logger", fake_logger)

    result, usage = await llm.call_gemini_json(
        system_prompt="sys",
        user_content="hello",
        inline_parts=[{"inline_data": {"data": "abc"}}],
    )

    assert result == response_payload
    assert usage.model == settings.GEMINI_MODEL
    assert usage.total_tokens == 14
    stored = json.loads(usage.request_payload)
    inline = stored["contents"][0]["parts"][1]["inline_data"]["data"]
    assert inline == "<inline_data omitted>"
    fake_logger.info.assert_called()


async def test_call_gemini_json_invalid_response(monkeypatch):
    settings = DummySettings()
    monkeypatch.setattr(llm, "get_settings", lambda: settings)

    bad_response = SimpleNamespace(
        status_code=200,
        json=lambda: {"unexpected": "shape"},
        text="bad",
    )
    client = SimpleNamespace(post=AsyncMock(return_value=bad_response))
    monkeypatch.setattr(llm, "get_http_client", lambda: client)
    monkeypatch.setattr(llm, "logger", Mock())

    with pytest.raises(RuntimeError) as exc:
        await llm.call_gemini_json("sys", "user")
    assert "gemini_invalid_response" in str(exc.value)


async def test_call_gemini_json_http_error(monkeypatch):
    settings = DummySettings()
    monkeypatch.setattr(llm, "get_settings", lambda: settings)

    error_response = SimpleNamespace(
        status_code=500,
        json=lambda: {"error": "server"},
        text="server error",
    )
    client = SimpleNamespace(post=AsyncMock(return_value=error_response))
    monkeypatch.setattr(llm, "get_http_client", lambda: client)
    logger_mock = Mock()
    monkeypatch.setattr(llm, "logger", logger_mock)

    with pytest.raises(RuntimeError) as exc:
        await llm.call_gemini_json("sys", "user", max_retries=1)
    assert "gemini_error" in str(exc.value)
    assert client.post.await_count == 2  # initial + retry


async def test_call_gemini_json_transport_retry(monkeypatch):
    settings = DummySettings()
    monkeypatch.setattr(llm, "get_settings", lambda: settings)

    error = httpx.TimeoutException("boom")
    client = SimpleNamespace(post=AsyncMock(side_effect=[error, error]))
    monkeypatch.setattr(llm, "get_http_client", lambda: client)
    monkeypatch.setattr(llm, "logger", Mock())

    with pytest.raises(RuntimeError) as exc:
        await llm.call_gemini_json("sys", "user", max_retries=1)
    assert "gemini_transport_error" in str(exc.value)
    assert client.post.await_count == 2
