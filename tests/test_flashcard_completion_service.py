from __future__ import annotations

import asyncio
import os
import tempfile

import pytest
from fastapi import HTTPException

os.environ.setdefault("USAGE_DB_PATH", os.path.join(tempfile.gettempdir(), "usage_test.sqlite"))

from app.schemas import FlashcardCompletionRequest, FlashcardCompletionCard
from app.services.flashcard_completion import complete_flashcard
from app.providers.llm import LLMProvider
from app.usage.models import LLMUsage
from app.usage.recorder import reset_usage


@pytest.fixture(autouse=True)
def clear_usage_storage():
    reset_usage()
    yield
    reset_usage()


class DummyProvider(LLMProvider):
    def __init__(self, payload: dict):
        self.payload = payload

    def resolve_model(self, override: str | None) -> str:
        return "gemini-2.5-flash"

    async def generate_json(self, system_prompt: str, user_content: str, *, model: str | None = None, inline_parts=None, timeout: int = 60):
        usage = LLMUsage(
            id=None,
            provider="gemini",
            api_kind="generateContent",
            model="gemini-2.5-flash",
            api_endpoint="https://example.com",
            device_id="unit-test",
            route="/flashcards/complete",
            inline_parts=0,
            prompt_chars=len(user_content),
            input_tokens=10,
            output_tokens=20,
            total_tokens=30,
            cost_input=0.0,
            cost_output=0.0,
            cost_total=0.0,
            latency_ms=12.0,
            status_code=200,
            timestamp=0.0,
        )
        return self.payload, usage


def make_request(front: str = "新聞媒體") -> FlashcardCompletionRequest:
    return FlashcardCompletionRequest(
        card=FlashcardCompletionCard(front=front, back="", frontNote=None, backNote=None),
        instruction="聚焦於國際新聞文脈",
        deckName="媒體用語",
    )


def test_complete_flashcard_success():
    provider = DummyProvider({
        "card": {
            "front": "新聞媒體",
            "frontNote": "常見於大眾傳播領域",
            "back": "news media",
            "backNote": "Use when referring to mass media outlets.",
        }
    })
    req = make_request()
    resp = asyncio.run(
        complete_flashcard(
            req,
            provider=provider,
            chosen_model="gemini-2.5-flash",
            device_id="unit-test",
            route="/flashcards/complete",
        )
    )
    assert resp.front == "新聞媒體"
    assert resp.back == "news media"
    assert resp.frontNote is not None


def test_complete_flashcard_requires_front():
    provider = DummyProvider({"card": {"front": "新聞媒體", "back": "news media"}})
    req = make_request(front="   ")
    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            complete_flashcard(
                req,
                provider=provider,
                chosen_model="gemini-2.5-flash",
                device_id="unit-test",
                route="/flashcards/complete",
            )
        )
    assert exc.value.status_code == 422
    assert exc.value.detail == "front_empty"


def test_complete_flashcard_invalid_shape():
    provider = DummyProvider({"foo": "bar"})
    req = make_request()
    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            complete_flashcard(
                req,
                provider=provider,
                chosen_model="gemini-2.5-flash",
                device_id="unit-test",
                route="/flashcards/complete",
            )
        )
    assert exc.value.status_code == 422
