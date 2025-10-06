from __future__ import annotations

from functools import lru_cache
from typing import Dict, Optional, Set

from pydantic import Field
from pydantic_settings import BaseSettings

from app.core.model_registry import (
    allowed_model_names,
    default_model,
    resolve_model_name,
)

class Settings(BaseSettings):
    # API keys
    GEMINI_API_KEY: Optional[str] = None
    GOOGLE_API_KEY: Optional[str] = None

    # Model selection
    GEMINI_MODEL: str = Field(default_factory=default_model)
    ALLOWED_MODELS: Optional[str] = Field(default=None, description="Comma separated allow-list")

    # Generation configuration
    LLM_TEMPERATURE: float = 0.1
    LLM_TOP_P: float = 0.1
    LLM_TOP_K: int = 1
    # Optional cap for model output tokens; when unset we do not send maxOutputTokens
    # allowing the provider to decide the limit. Can be re-enabled via env var.
    LLM_MAX_OUTPUT_TOKENS: Optional[int] = None

    # Content/data
    CONTENT_DIR: str = "data"
    USAGE_DB_PATH: str = "data/usage.db"
    USAGE_DB_URL: Optional[str] = None
    QUESTION_DB_PATH: str = "data/questions.sqlite"
    QUESTION_DB_URL: Optional[str] = None
    CONTENT_ADMIN_TOKEN: Optional[str] = None

    # Prompts
    PROMPT_FILE: str = "prompts/prompt.txt"
    PROMPT_LENIENT_FILE: str = "prompts/prompt_lenient.txt"
    DECK_PROMPT_FILE: str = "prompts/prompt_deck.txt"
    CHAT_TURN_PROMPT_FILE: str = "prompts/prompt_chat_turn.txt"
    CHAT_RESEARCH_PROMPT_FILE: str = "prompts/prompt_chat_research.txt"
    MERGE_PROMPT_FILE: str = "prompts/prompt_merge.txt"
    FLASHCARD_COMPLETION_PROMPT_FILE: str = "prompts/prompt_flashcard_completion.txt"

    # Debug / logging
    DECK_DEBUG_LOG: str = "1"
    LOG_LEVEL: str = "INFO"
    LLM_LOG_MODE: str = "both"  # off | input | output | both
    LLM_LOG_PRETTY: bool = True
    QUESTION_PROMPT_FILE: str = "prompts/prompt_generate_questions.txt"
    GENERATOR_DEFAULT_COUNT: int = 8

    def allowed_models_set(self) -> Set[str]:
        raw = (self.ALLOWED_MODELS or "").strip()
        if not raw:
            return set(allowed_model_names())

        allowed: Set[str] = set()
        for token in raw.split(","):
            candidate = token.strip()
            if not candidate:
                continue
            resolved = resolve_model_name(candidate, include_deprecated=True)
            allowed.update(resolved.info.all_names())
        if not allowed:
            raise ValueError("ALLOWED_MODELS produced empty set")
        return allowed

    def generation_config(self) -> Dict[str, object]:
        config: Dict[str, object] = {
            "response_mime_type": "application/json",
            "temperature": float(self.LLM_TEMPERATURE),
            "topP": float(self.LLM_TOP_P),
            "topK": int(self.LLM_TOP_K),
        }
        max_tokens = self.LLM_MAX_OUTPUT_TOKENS
        if max_tokens is not None:
            max_tokens_int = int(max_tokens)
            if max_tokens_int > 0:
                config["maxOutputTokens"] = max_tokens_int
        return config

    def deck_debug_enabled(self) -> bool:
        v = (self.DECK_DEBUG_LOG or "").strip().lower()
        return v in ("1", "true", "yes", "on")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # reads from env by default
