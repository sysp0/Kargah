"""What a step cost: reported by the harness, else estimated from a price list, else unknown (pure)."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from kargah.ports.harness import HarnessResult


@dataclass(frozen=True)
class ModelPrice:
    input: float
    output: float
    cached: float          # USD per million tokens


def step_cost(result: HarnessResult, model: str, prices: Mapping[str, ModelPrice]) -> tuple[float | None, str]:
    if result.cost_usd is not None:
        return result.cost_usd, "reported"
    price = prices.get(model)
    if price is not None and result.tokens_in is not None and result.tokens_out is not None:
        cached = result.tokens_cached or 0
        cost = ((result.tokens_in - cached) * price.input + cached * price.cached + result.tokens_out * price.output)
        return cost / 1e6, "estimated"
    return None, "unknown"
