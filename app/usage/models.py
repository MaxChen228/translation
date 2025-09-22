from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class LLMUsage(BaseModel):
    timestamp: float = Field(..., description="Unix timestamp when the call finished")
    provider: str = "gemini"
    api_kind: str = "generateContent"
    model: str
    api_endpoint: str
    route: str = ""
    device_id: str = "unknown"
    inline_parts: int = 0
    prompt_chars: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    latency_ms: float = 0.0
    status_code: Optional[int] = None


class LLMUsageSummary(BaseModel):
    count: int
    total_input_tokens: int
    total_output_tokens: int
    total_tokens: int
    total_prompt_chars: int
    avg_latency_ms: float


class LLMUsageQueryResponse(BaseModel):
    summary: LLMUsageSummary
    items: list[LLMUsage]
