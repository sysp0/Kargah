from kargah.domain.pricing import ModelPrice, step_cost
from kargah.ports.harness import HarnessResult

PRICES = {"m": ModelPrice(input=2.0, output=10.0, cached=0.5)}


def test_a_reported_cost_wins():
    result = HarnessResult(ok=True, cost_usd=0.25, tokens_in=1000, tokens_out=1000)
    assert step_cost(result, "m", PRICES) == (0.25, "reported")


def test_estimated_from_tokens_and_price_with_cached_input_priced_lower():
    result = HarnessResult(ok=True, tokens_in=1_000_000, tokens_out=100_000, tokens_cached=400_000)
    cost, source = step_cost(result, "m", PRICES)
    assert source == "estimated" and round(cost, 6) == round(600_000 * 2 / 1e6 + 400_000 * 0.5 / 1e6 + 1.0, 6)


def test_no_cached_tokens_counts_as_zero_cached():
    result = HarnessResult(ok=True, tokens_in=1_000_000, tokens_out=0)
    assert step_cost(result, "m", PRICES) == (2.0, "estimated")


def test_unknown_when_the_model_has_no_price_or_tokens_are_missing():
    assert step_cost(HarnessResult(ok=True, tokens_in=5, tokens_out=5), "other", PRICES) == (None, "unknown")
    assert step_cost(HarnessResult(ok=True, tokens_in=5), "m", PRICES) == (None, "unknown")
    assert step_cost(HarnessResult(ok=True), "m", {}) == (None, "unknown")
