"""Strategy mapping logic — maps questionnaire answers to a named strategy."""
from __future__ import annotations


STRATEGY_LONG_ONLY = "Long-Only"
STRATEGY_LONG_BIASED = "Long-Biased (130/30)"
STRATEGY_LONG_SHORT = "Long-Short"
STRATEGY_MARKET_NEUTRAL = "Market Neutral"

STRATEGY_DESCRIPTIONS = {
    STRATEGY_LONG_ONLY: "100% long book, 0% short book, net exposure 100%.",
    STRATEGY_LONG_BIASED: "130% long book, 30% short book, net exposure 100%.",
    STRATEGY_LONG_SHORT: "60–70% net exposure, balanced long and short books.",
    STRATEGY_MARKET_NEUTRAL: "~0% net exposure, equal dollar long and short books.",
}

_STRATEGY_RANK = {
    STRATEGY_LONG_ONLY: 0,
    STRATEGY_LONG_BIASED: 1,
    STRATEGY_LONG_SHORT: 2,
    STRATEGY_MARKET_NEUTRAL: 3,
}


def _most_restrictive(a: str, b: str) -> str:
    return a if _STRATEGY_RANK[a] <= _STRATEGY_RANK[b] else b


def resolve_strategy(
    investor_type: str,
    investor_subtype: str,
    age: int,
    objective: str,
    drawdown_tolerance: str,
) -> str:
    """Return the most restrictive eligible strategy given all constraints."""

    # Rule 3 — objective / drawdown (always applies)
    obj = objective.lower()
    dd = drawdown_tolerance.lower()

    if "capital preservation" in obj or "5%" in dd:
        rule3 = STRATEGY_LONG_ONLY
    elif "income" in obj or "10%" in dd:
        rule3 = STRATEGY_LONG_BIASED
    elif "balanced" in obj or "20%" in dd:
        rule3 = STRATEGY_LONG_SHORT
    else:
        rule3 = STRATEGY_MARKET_NEUTRAL  # aggressive / max return + 30%+

    if investor_type.lower() == "individual":
        # Rule 1 — age + retirement override
        subtype_lower = investor_subtype.lower()
        if "retired" in subtype_lower or age >= 65:
            rule1 = STRATEGY_LONG_ONLY
        elif age >= 50:
            rule1 = STRATEGY_LONG_BIASED
        elif age >= 35:
            rule1 = STRATEGY_LONG_SHORT
        else:
            rule1 = STRATEGY_MARKET_NEUTRAL  # all eligible

        return _most_restrictive(rule1, rule3)

    else:
        # Rule 2 — institution type
        sub = investor_subtype.lower()
        if "insurance" in sub:
            rule2 = STRATEGY_LONG_ONLY
        elif "pension" in sub or "sovereign" in sub:
            rule2 = STRATEGY_LONG_BIASED
        elif "endowment" in sub or "foundation" in sub or "asset manager" in sub or "mutual" in sub:
            rule2 = STRATEGY_LONG_SHORT
        else:
            # Hedge fund, Family Office — all eligible
            rule2 = STRATEGY_MARKET_NEUTRAL

        return _most_restrictive(rule2, rule3)


def strategy_books(strategy: str, investment_amount: float) -> tuple[float, float, float, float]:
    """Return (long_pct, short_pct, net_exposure_pct, gross_exposure_pct)."""
    if strategy == STRATEGY_LONG_ONLY:
        return 1.0, 0.0, 1.0, 1.0
    elif strategy == STRATEGY_LONG_BIASED:
        return 1.30, 0.30, 1.0, 1.60
    elif strategy == STRATEGY_LONG_SHORT:
        return 0.85, 0.50, 0.65, 1.35
    else:  # Market Neutral
        return 0.50, 0.50, 0.0, 1.0
