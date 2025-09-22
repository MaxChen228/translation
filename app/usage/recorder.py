from __future__ import annotations

from typing import List, Optional

from .models import LLMUsage, LLMUsageSummary
from .pricing import compute_cost
from .storage import get_storage


def _with_costs(usage: LLMUsage) -> LLMUsage:
    cost_input, cost_output, cost_total = compute_cost(
        usage.model,
        usage.input_tokens,
        usage.output_tokens,
    )
    return usage.model_copy(
        update={
            "cost_input": cost_input,
            "cost_output": cost_output,
            "cost_total": cost_total,
        }
    )


def record_usage(usage: LLMUsage, *, route: str, device_id: str) -> LLMUsage:
    usage_with_ctx = usage.model_copy(update={"route": route, "device_id": device_id})
    usage_with_costs = _with_costs(usage_with_ctx)
    get_storage().record(usage_with_costs)
    return usage_with_costs


def query_usage(
    *,
    device_id: Optional[str] = None,
    route: Optional[str] = None,
    model: Optional[str] = None,
    provider: Optional[str] = None,
    since: Optional[float] = None,
    until: Optional[float] = None,
    limit: Optional[int] = None,
    offset: int = 0,
) -> List[LLMUsage]:
    return get_storage().query(
        device_id=device_id,
        route=route,
        model=model,
        provider=provider,
        since=since,
        until=until,
        limit=limit,
        offset=offset,
    )


def summarize_usage(
    *,
    device_id: Optional[str] = None,
    route: Optional[str] = None,
    model: Optional[str] = None,
    provider: Optional[str] = None,
    since: Optional[float] = None,
    until: Optional[float] = None,
) -> LLMUsageSummary:
    return get_storage().summarize(
        device_id=device_id,
        route=route,
        model=model,
        provider=provider,
        since=since,
        until=until,
    )


def reset_usage() -> None:
    get_storage().reset()

