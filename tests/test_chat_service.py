import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException

from app.schemas import (
    ChatAttachment,
    ChatMessage,
    ChatTurnRequest,
    ChatResearchRequest,
    ChatResearchResponse,
)
from app.services import chat
from app.usage.models import LLMUsage


pytestmark = pytest.mark.anyio


@pytest.fixture
def fake_usage():
    return LLMUsage(
        timestamp=0.0,
        provider="gemini",
        api_kind="generateContent",
        model="gemini-test",
        api_endpoint="https://example.com",
        inline_parts=0,
        prompt_chars=0,
        input_tokens=1,
        output_tokens=1,
        total_tokens=2,
        latency_ms=12.3,
        status_code=200,
        request_payload="{}",
        response_payload="{}",
    )


def test_serialize_messages_with_images():
    attachment = ChatAttachment(type="image", mimeType="image/png", data="abc123")
    msg = ChatMessage(role="user", content="see image", attachments=[attachment])
    payload, inline_parts = chat._serialize_messages([msg])
    payload_obj = json.loads(payload)
    assert payload_obj["messages"][0]["attachments"][0]["index"] == 1
    assert inline_parts[0]["inline_data"]["data"] == "abc123"


def test_require_str_validates(monkeypatch):
    with pytest.raises(HTTPException):
        chat._require_str({}, "missing")
    with pytest.raises(HTTPException):
        chat._require_str({"value": "   "}, "value")
    assert chat._require_str({"value": "ok"}, "value") == "ok"


@pytest.mark.parametrize(
    "reply, expected_prefix",
    [
        ("", "## 回覆摘要"),
        ("Hello world", "## 回覆摘要"),
        ("## 回覆摘要\n- a\n## 詳細說明\nBody", "## 回覆摘要"),
        ("## 回覆摘要\n- a", "## 回覆摘要"),
        ("## 詳細說明\nAnswer", "## 回覆摘要"),
    ],
)
def test_normalize_markdown_reply_shapes_output(reply, expected_prefix):
    normalized = chat._normalize_markdown_reply(reply)
    assert normalized.startswith(expected_prefix)


@pytest.fixture
def anyio_backend():
    return "asyncio"


async def test_run_turn_success(monkeypatch, fake_usage):
    request = ChatTurnRequest(messages=[ChatMessage(role="user", content="hi")])
    provider = SimpleNamespace(generate_json=AsyncMock(return_value=({
        "reply": "Hello there",
        "state": "ready",
        "checklist": ["item"],
    }, fake_usage)))

    monkeypatch.setattr(chat, "load_chat_turn_prompt", lambda: "system")
    record_mock = Mock()
    monkeypatch.setattr(chat, "record_usage", record_mock)
    monkeypatch.setattr(chat, "logger", Mock())

    resp = await chat.run_turn(request, provider, device_id="dev", route="/chat")
    assert resp.state == "ready"
    assert resp.checklist == ["item"]
    assert "## 回覆摘要" in resp.reply
    provider.generate_json.assert_awaited_once()
    record_mock.assert_called_once_with(fake_usage, route="/chat", device_id="dev")


async def test_run_turn_invalid_reply(monkeypatch, fake_usage):
    request = ChatTurnRequest(messages=[ChatMessage(role="user", content="hi")])
    provider = SimpleNamespace(generate_json=AsyncMock(return_value=({}, fake_usage)))
    monkeypatch.setattr(chat, "load_chat_turn_prompt", lambda: "system")
    monkeypatch.setattr(chat, "record_usage", Mock())
    with pytest.raises(HTTPException):
        await chat.run_turn(request, provider, device_id="dev", route="/chat")


async def test_run_research_success(monkeypatch, fake_usage):
    request = ChatResearchRequest(messages=[ChatMessage(role="user", content="topic")])
    payload = {
        "deckName": " My Deck ",
        "cards": [
            {"front": "Q1", "back": "A1", "frontNote": " note ", "backNote": ""},
            {"front": "Q2", "back": "A2"},
        ],
    }
    provider = SimpleNamespace(generate_json=AsyncMock(return_value=(payload, fake_usage)))
    monkeypatch.setattr(chat, "load_chat_research_prompt", lambda: "research")
    record_mock = Mock()
    monkeypatch.setattr(chat, "record_usage", record_mock)

    result = await chat.run_research(request, provider, device_id="dev", route="/research")
    assert isinstance(result, ChatResearchResponse)
    assert result.deckName == "My Deck"
    assert result.cards[0].frontNote == "note"
    record_mock.assert_called_once_with(fake_usage, route="/research", device_id="dev")


async def test_run_research_missing_cards(monkeypatch, fake_usage):
    request = ChatResearchRequest(messages=[ChatMessage(role="user", content="topic")])
    provider = SimpleNamespace(generate_json=AsyncMock(return_value=({"cards": []}, fake_usage)))
    monkeypatch.setattr(chat, "load_chat_research_prompt", lambda: "research")
    monkeypatch.setattr(chat, "record_usage", Mock())
    logger_mock = Mock()
    monkeypatch.setattr(chat, "logger", logger_mock)

    with pytest.raises(HTTPException):
        await chat.run_research(request, provider, device_id="dev", route="/research")
    logger_mock.warning.assert_called()
