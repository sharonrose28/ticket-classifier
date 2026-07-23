"""Deterministic token-cost estimation using deployment-configured rates."""

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from app.core.settings import Settings

_MILLION = Decimal("1000000")
_COST_QUANTUM = Decimal("0.00000001")


@dataclass(frozen=True, slots=True)
class TokenRates:
    input_per_million: Decimal
    cached_input_per_million: Decimal
    output_per_million: Decimal


def rates_for_model(model: str, settings: Settings) -> TokenRates:
    """Resolve configured prices by model role, accepting snapshot suffixes."""

    if model == settings.openai_fallback_model or model.startswith(
        f"{settings.openai_fallback_model}-"
    ):
        return TokenRates(
            settings.openai_fallback_input_cost_per_million,
            settings.openai_fallback_cached_input_cost_per_million,
            settings.openai_fallback_output_cost_per_million,
        )
    return TokenRates(
        settings.openai_primary_input_cost_per_million,
        settings.openai_primary_cached_input_cost_per_million,
        settings.openai_primary_output_cost_per_million,
    )


def estimate_cost_usd(
    *,
    model: str,
    input_tokens: int,
    cached_input_tokens: int,
    output_tokens: int,
    settings: Settings,
) -> Decimal:
    """Estimate text-token cost; this is not a substitute for provider billing."""

    cached = min(max(0, cached_input_tokens), max(0, input_tokens))
    uncached = max(0, input_tokens) - cached
    rates = rates_for_model(model, settings)
    cost = (
        Decimal(uncached) * rates.input_per_million
        + Decimal(cached) * rates.cached_input_per_million
        + Decimal(max(0, output_tokens)) * rates.output_per_million
    ) / _MILLION
    return cost.quantize(_COST_QUANTUM, rounding=ROUND_HALF_UP)
