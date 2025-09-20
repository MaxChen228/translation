from __future__ import annotations

from functools import lru_cache
from typing import Optional, Set, Dict

from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    # API keys
    GEMINI_API_KEY: Optional[str] = None
    GOOGLE_API_KEY: Optional[str] = None

    # Model selection
    GEMINI_MODEL: str = "gemini-2.5-flash"
    ALLOWED_MODELS: Optional[str] = Field(default=None, description="Comma separated allow-list")

    # Generation configuration
    LLM_TEMPERATURE: float = 0.1
    LLM_TOP_P: float = 0.1
    LLM_TOP_K: int = 1
    # Set a very high default cap to avoid truncation under JSON mode
    # Can still be overridden by environment variable LLM_MAX_OUTPUT_TOKENS
    LLM_MAX_OUTPUT_TOKENS: int = 8192

    # Content/data
    CONTENT_DIR: str = "data"

    # Prompts
    PROMPT_FILE: str = "prompts/prompt.txt"
    DECK_PROMPT_FILE: str = "prompts/prompt_deck.txt"
    CHAT_TURN_PROMPT_FILE: str = "prompts/prompt_chat_turn.txt"
    CHAT_RESEARCH_PROMPT_FILE: str = "prompts/prompt_chat_research.txt"

    # Debug / logging
    DECK_DEBUG_LOG: str = "1"
    LOG_LEVEL: str = "INFO"

    def allowed_models_set(self) -> Set[str]:
        raw = (self.ALLOWED_MODELS or "").strip()
        if not raw:
            return {"gemini-2.5-pro", "gemini-2.5-flash"}
        return {m.strip() for m in raw.split(",") if m.strip()}

    def generation_config(self) -> Dict[str, object]:
        return {
            "response_mime_type": "application/json",
            "temperature": float(self.LLM_TEMPERATURE),
            "topP": float(self.LLM_TOP_P),
            "topK": int(self.LLM_TOP_K),
            "maxOutputTokens": int(self.LLM_MAX_OUTPUT_TOKENS),
        }

    def deck_debug_enabled(self) -> bool:
        v = (self.DECK_DEBUG_LOG or "").strip().lower()
        return v in ("1", "true", "yes", "on")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # reads from env by default
