from __future__ import annotations

from typing import Optional, Protocol, Sequence, Mapping

from app.core.settings import get_settings
from app.llm import call_gemini_json, resolve_model as llm_resolve_model


class LLMProvider(Protocol):
    def resolve_model(self, override: Optional[str]) -> str: ...

    def generate_json(
        self,
        system_prompt: str,
        user_content: str,
        *,
        model: Optional[str] = None,
        inline_parts: Optional[Sequence[Mapping[str, object]]] = None,
        timeout: int = 60,
    ) -> dict: ...


class GeminiProvider:
    def resolve_model(self, override: Optional[str]) -> str:
        # Delegate to existing resolver which respects env allow-list
        return llm_resolve_model(override)

    def generate_json(
        self,
        system_prompt: str,
        user_content: str,
        *,
        model: Optional[str] = None,
        inline_parts: Optional[Sequence[Mapping[str, object]]] = None,
        timeout: int = 60,
    ) -> dict:
        return call_gemini_json(
            system_prompt,
            user_content,
            model=model,
            inline_parts=inline_parts,
            timeout=timeout,
        )


def get_provider() -> LLMProvider:
    # In future, can switch by settings or feature flags
    return GeminiProvider()
