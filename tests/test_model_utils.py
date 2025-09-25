from typing import Optional

import pytest
from fastapi import HTTPException

from app.routers.model_utils import resolve_model_or_422


class StubProvider:
    def __init__(self, *, response: Optional[str] = None, error: Optional[ValueError] = None):
        self._response = response
        self._error = error
        self.called_with: Optional[str] = None

    def resolve_model(self, override: Optional[str]) -> str:
        self.called_with = override
        if self._error is not None:
            raise self._error
        return self._response or (override or "default-model")


def test_resolve_model_success_passthrough():
    provider = StubProvider()
    result = resolve_model_or_422(provider, "gemini-model")
    assert result == "gemini-model"
    assert provider.called_with == "gemini-model"


def test_resolve_model_raises_http_exception_with_json_detail():
    error = ValueError('{"invalid_model":"bad","allowed":["good"]}')
    provider = StubProvider(error=error)

    with pytest.raises(HTTPException) as exc_info:
        resolve_model_or_422(provider, "bad")

    exc = exc_info.value
    assert exc.status_code == 422
    assert exc.detail == {"invalid_model": "bad", "allowed": ["good"]}


def test_resolve_model_falls_back_to_default_detail():
    error = ValueError("unexpected message")
    provider = StubProvider(error=error)

    with pytest.raises(HTTPException) as exc_info:
        resolve_model_or_422(provider, "bad-model")

    exc = exc_info.value
    assert exc.status_code == 422
    assert exc.detail == {"invalid_model": "bad-model"}
