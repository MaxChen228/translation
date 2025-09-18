from __future__ import annotations

from functools import lru_cache
from typing import Optional, Set, Dict

from pydantic import BaseSettings, Field


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
    LLM_MAX_OUTPUT_TOKENS: int = 320

    # Content/data
    CONTENT_DIR: str = "data"

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


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # reads from env by default

