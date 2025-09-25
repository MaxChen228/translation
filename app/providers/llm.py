from __future__ import annotations

from typing import Optional, Protocol, Sequence, Mapping

from app.llm import call_gemini_json, resolve_model as llm_resolve_model
from app.usage.models import LLMUsage


class LLMProvider(Protocol):
    def resolve_model(self, override: Optional[str]) -> str: ...

    async def generate_json(
        self,
        system_prompt: str,
        user_content: str,
        *,
        model: Optional[str] = None,
        inline_parts: Optional[Sequence[Mapping[str, object]]] = None,
        timeout: int = 60,
    ) -> tuple[dict, LLMUsage]: ...


class GeminiProvider:
    def resolve_model(self, override: Optional[str]) -> str:
        # Delegate to existing resolver which respects env allow-list
        return llm_resolve_model(override)

    async def generate_json(
        self,
        system_prompt: str,
        user_content: str,
        *,
        model: Optional[str] = None,
        inline_parts: Optional[Sequence[Mapping[str, object]]] = None,
        timeout: int = 60,
    ) -> tuple[dict, LLMUsage]:
        return await call_gemini_json(
            system_prompt,
            user_content,
            model=model,
            inline_parts=inline_parts,
            timeout=timeout,
        )


def get_provider() -> LLMProvider:
    # In future, can switch by settings or feature flags
    return GeminiProvider()
