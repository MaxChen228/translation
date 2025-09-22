from __future__ import annotations

from typing import Optional, Tuple

# Pricing in USD per million tokens
# Values sourced from Google Gemini public pricing (2025-02)
_PRICING_TABLE: dict[str, Tuple[float, float]] = {
    "gemini-2.5-flash": (0.30, 2.50),
    "gemini-2.5-flash-lite": (0.10, 0.40),
    "gemini-2.5-pro": (1.25, 10.00),
}


def get_pricing(model: str) -> Optional[Tuple[float, float]]:
    key = (model or "").strip().lower()
    for name, pricing in _PRICING_TABLE.items():
        if name.lower() == key:
            return pricing
    return None


def compute_cost(model: str, input_tokens: int, output_tokens: int) -> Tuple[float, float, float]:
    pricing = get_pricing(model)
    if pricing is None:
        return 0.0, 0.0, 0.0
    input_price, output_price = pricing
    cost_input = (input_tokens * input_price) / 1_000_000
    cost_output = (output_tokens * output_price) / 1_000_000
    return cost_input, cost_output, cost_input + cost_output


def pricing_table() -> dict[str, Tuple[float, float]]:
    return dict(_PRICING_TABLE)

