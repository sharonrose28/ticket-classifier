from decimal import Decimal

from app.ai.pricing import estimate_cost_usd, rates_for_model
from app.core.settings import Settings


def test_primary_cost_accounts_for_cached_input_tokens():
    cost = estimate_cost_usd(
        model="gpt-4.1",
        input_tokens=1_000_000,
        cached_input_tokens=250_000,
        output_tokens=100_000,
        settings=Settings(),
    )
    assert cost == Decimal("2.42500000")


def test_fallback_snapshot_uses_fallback_rates():
    settings = Settings()
    rates = rates_for_model("gpt-4.1-mini-2025-04-14", settings)
    assert rates.input_per_million == Decimal("0.40")
    assert rates.output_per_million == Decimal("1.60")


def test_cached_tokens_are_bounded_by_total_input():
    cost = estimate_cost_usd(
        model="gpt-4.1-mini",
        input_tokens=10,
        cached_input_tokens=100,
        output_tokens=-1,
        settings=Settings(),
    )
    assert cost == Decimal("0.00000100")
