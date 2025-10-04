import json
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException

from app.schemas import DeckKnowledgeItem, DeckMakeRequest
from app.services import deck_maker
from app.usage.models import LLMUsage


pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def llm_usage():
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


@pytest.fixture(autouse=True)
def disable_debug_write(monkeypatch):
    monkeypatch.setattr(deck_maker, "_deck_debug_write", lambda payload: None)


async def test_make_deck_success(monkeypatch, llm_usage):
    concepts = [
        DeckKnowledgeItem(i=2, concept="  Concept  ", zh=" zh ", en=" en ", note=" note ", source=" src "),
        DeckKnowledgeItem(concept="Another"),
    ]
    req = DeckMakeRequest(name="  My Deck  ", concepts=concepts)

    response_obj = {
        "name": "Generated Deck",
        "cards": [
            {"front": "Front 1", "back": "Back 1", "frontNote": " note ", "back_note": ""},
            {"zh": "Front 2", "en": "Back 2"},
        ],
    }
    call_mock = AsyncMock(return_value=(response_obj, llm_usage))
    monkeypatch.setattr(deck_maker, "call_gemini_json", call_mock)
    record_mock = Mock(side_effect=lambda usage, route, device_id: usage)
    monkeypatch.setattr(deck_maker, "record_usage", record_mock)

    result = await deck_maker.make_deck_from_request(
        req,
        deck_prompt="prompt",
        chosen_model="gemini-test",
        device_id="dev",
        route="/make_deck",
    )

    assert result.name == "Generated Deck"
    assert len(result.cards) == 2
    assert result.cards[0].frontNote == "note"
    call_mock.assert_awaited_once()
    record_mock.assert_called_once()


async def test_make_deck_missing_concepts_raises():
    req = DeckMakeRequest(name="Empty", concepts=[])
    with pytest.raises(HTTPException) as exc:
        await deck_maker.make_deck_from_request(req, deck_prompt="p", chosen_model="m")
    assert exc.value.detail == "deck_items_empty"


async def test_make_deck_invalid_shape(monkeypatch, llm_usage):
    req = DeckMakeRequest(name="Deck", concepts=[DeckKnowledgeItem(concept="C")])
    monkeypatch.setattr(deck_maker, "call_gemini_json", AsyncMock(return_value=({}, llm_usage)))
    monkeypatch.setattr(deck_maker, "record_usage", Mock(side_effect=lambda usage, route, device_id: usage))

    with pytest.raises(HTTPException) as exc:
        await deck_maker.make_deck_from_request(req, deck_prompt="p", chosen_model="m")
    assert exc.value.detail == "deck_json_invalid_shape"


async def test_make_deck_no_cards_after_filter(monkeypatch, llm_usage):
    req = DeckMakeRequest(name="Deck", concepts=[DeckKnowledgeItem(concept="C")])
    response_obj = {
        "cards": [
            {"front": " ", "back": "B"},
            {"front": "F", "back": " "},
        ]
    }
    monkeypatch.setattr(deck_maker, "call_gemini_json", AsyncMock(return_value=(response_obj, llm_usage)))
    monkeypatch.setattr(deck_maker, "record_usage", Mock(side_effect=lambda usage, route, device_id: usage))

    with pytest.raises(HTTPException) as exc:
        await deck_maker.make_deck_from_request(req, deck_prompt="p", chosen_model="m")
    assert exc.value.detail == "deck_cards_empty"
