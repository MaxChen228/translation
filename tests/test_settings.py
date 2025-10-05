
import pytest

from app.core.settings import get_settings


@pytest.fixture(autouse=True)
def reset_settings(monkeypatch):
    for key in [
        "ALLOWED_MODELS",
        "LLM_TEMPERATURE",
        "LLM_TOP_P",
        "LLM_TOP_K",
        "LLM_MAX_OUTPUT_TOKENS",
        "DECK_DEBUG_LOG",
    ]:
        monkeypatch.delenv(key, raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_allowed_models_defaults():
    settings = get_settings()
    defaults = settings.allowed_models_set()
    assert "gemini-2.5-pro" in defaults
    assert "gemini-flash-lite-latest" in defaults


def test_allowed_models_custom(monkeypatch):
    monkeypatch.setenv("ALLOWED_MODELS", "alpha, beta , alpha")
    settings = get_settings()
    models = settings.allowed_models_set()
    assert models == {"alpha", "beta"}


def test_generation_config_casts(monkeypatch):
    monkeypatch.setenv("LLM_TEMPERATURE", "0.7")
    monkeypatch.setenv("LLM_TOP_P", "0.8")
    monkeypatch.setenv("LLM_TOP_K", "5")
    monkeypatch.setenv("LLM_MAX_OUTPUT_TOKENS", "1024")
    settings = get_settings()
    config = settings.generation_config()
    assert config["temperature"] == pytest.approx(0.7)
    assert config["topP"] == pytest.approx(0.8)
    assert config["topK"] == 5
    assert config["maxOutputTokens"] == 1024


def test_generation_config_without_max_tokens():
    settings = get_settings()
    config = settings.generation_config()
    assert "maxOutputTokens" not in config


def test_deck_debug_enabled(monkeypatch):
    monkeypatch.setenv("DECK_DEBUG_LOG", "off")
    settings = get_settings()
    assert settings.deck_debug_enabled() is False
    monkeypatch.setenv("DECK_DEBUG_LOG", "YES")
    get_settings.cache_clear()
    settings = get_settings()
    assert settings.deck_debug_enabled() is True
