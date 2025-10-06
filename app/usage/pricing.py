from __future__ import annotations

from typing import Dict, Optional, Tuple

from app.core.model_registry import (
    allowed_model_names,
    get_model_info,
    pricing_for_model,
    resolve_model_name,
)


def get_pricing(model: str) -> Optional[Tuple[float, float]]:
    try:
        resolved = resolve_model_name(model)
    except ValueError:
        return None
    pricing = pricing_for_model(resolved.canonical_name)
    if pricing == (0.0, 0.0):
        return None
    return pricing


def compute_cost(model: str, input_tokens: int, output_tokens: int) -> Tuple[float, float, float]:
    pricing = get_pricing(model)
    if pricing is None:
        return 0.0, 0.0, 0.0
    input_price, output_price = pricing
    cost_input = (input_tokens * input_price) / 1_000_000
    cost_output = (output_tokens * output_price) / 1_000_000
    return cost_input, cost_output, cost_input + cost_output


def pricing_table() -> Dict[str, Tuple[float, float]]:
    table: Dict[str, Tuple[float, float]] = {}
    seen: set[str] = set()
    for name in allowed_model_names(include_deprecated=True):
        info = get_model_info(name)
        if info is None:
            continue
        if info.canonical_name in seen:
            continue
        seen.add(info.canonical_name)
        table[info.canonical_name] = pricing_for_model(info.canonical_name)
    return table
