"""Comparable-valuation fair value estimation."""
from __future__ import annotations

import logging
from typing import Optional

from backend.models.schemas import (
    ComputedRatios,
    FinancialMetrics,
    FairValueResult,
    SectorStats,
)

logger = logging.getLogger(__name__)

# Sector-specific weighting schemes for fair value methods
# Keys: lowercase method name.  Values: relative weight (will be normalised).
_SECTOR_WEIGHTS: dict[str, dict[str, float]] = {
    "Information Technology": {"ps": 0.35, "pe": 0.35, "ev_sales": 0.30},
    "Communication Services": {"pe": 0.35, "ps": 0.30, "ev_ebitda": 0.35},
    "Financials": {"pb": 0.50, "pe": 0.40, "ps": 0.10},
    "Health Care": {"pe": 0.40, "ev_ebitda": 0.35, "ps": 0.25},
    "Consumer Discretionary": {"pe": 0.40, "ev_ebitda": 0.30, "ps": 0.30},
    "Consumer Staples": {"pe": 0.40, "ev_ebitda": 0.35, "ps": 0.25},
    "Energy": {"ev_ebitda": 0.40, "pe": 0.35, "pfcf": 0.25},
    "Industrials": {"pe": 0.40, "ev_ebitda": 0.35, "pfcf": 0.25},
    "Materials": {"pe": 0.40, "ev_ebitda": 0.40, "ps": 0.20},
    "Utilities": {"pe": 0.40, "ev_ebitda": 0.40, "pb": 0.20},
    "Real Estate": {"pb": 0.40, "pe": 0.35, "ps": 0.25},
    "default": {"pe": 0.35, "pb": 0.25, "ps": 0.25, "pfcf": 0.15},
}


def _normalize_weights(raw: dict[str, float]) -> dict[str, float]:
    total = sum(raw.values())
    if total <= 0:
        return raw
    return {k: v / total for k, v in raw.items()}


def _implied_price_pe(
    sector_median_pe: Optional[float],
    company_ratios: ComputedRatios,
    metrics: FinancialMetrics,
    current_price: float,
) -> Optional[float]:
    if not sector_median_pe or sector_median_pe <= 0:
        return None
    # Use TTM EPS
    eps = metrics.ttm_eps
    if eps is None or eps <= 0:
        return None
    return sector_median_pe * eps


def _implied_price_pb(
    sector_median_pb: Optional[float],
    metrics: FinancialMetrics,
) -> Optional[float]:
    if not sector_median_pb or sector_median_pb <= 0:
        return None
    bvps = metrics.book_value_per_share
    if bvps is None or bvps <= 0:
        return None
    return sector_median_pb * bvps


def _implied_price_ps(
    sector_median_ps: Optional[float],
    metrics: FinancialMetrics,
) -> Optional[float]:
    if not sector_median_ps or sector_median_ps <= 0:
        return None
    if metrics.ttm_revenue is None or metrics.ttm_revenue <= 0:
        return None
    shares = metrics.shares_outstanding
    if shares is None or shares <= 0:
        return None
    rev_per_share = metrics.ttm_revenue / shares
    return sector_median_ps * rev_per_share


def _implied_price_pfcf(
    sector_median_pfcf: Optional[float],
    metrics: FinancialMetrics,
) -> Optional[float]:
    if not sector_median_pfcf or sector_median_pfcf <= 0:
        return None
    if metrics.ttm_fcf is None or metrics.ttm_fcf <= 0:
        return None
    shares = metrics.shares_outstanding
    if shares is None or shares <= 0:
        return None
    fcf_per_share = metrics.ttm_fcf / shares
    return sector_median_pfcf * fcf_per_share


def _implied_price_ev_ebitda(
    sector_median_ev_ebitda: Optional[float],
    metrics: FinancialMetrics,
) -> Optional[float]:
    """Back-calculate implied price from EV/EBITDA: implied_EV = multiple * EBITDA → equity = EV - net_debt."""
    if not sector_median_ev_ebitda or sector_median_ev_ebitda <= 0:
        return None
    if metrics.ttm_ebitda is None or metrics.ttm_ebitda <= 0:
        return None
    shares = metrics.shares_outstanding
    if shares is None or shares <= 0:
        return None
    implied_ev = sector_median_ev_ebitda * metrics.ttm_ebitda
    net_debt = metrics.net_debt or 0.0
    implied_equity = implied_ev - net_debt
    if implied_equity <= 0:
        return None
    return implied_equity / shares


def _implied_price_ev_sales(
    sector_median_ev_sales: Optional[float],
    metrics: FinancialMetrics,
) -> Optional[float]:
    if not sector_median_ev_sales or sector_median_ev_sales <= 0:
        return None
    if metrics.ttm_revenue is None or metrics.ttm_revenue <= 0:
        return None
    shares = metrics.shares_outstanding
    if shares is None or shares <= 0:
        return None
    implied_ev = sector_median_ev_sales * metrics.ttm_revenue
    net_debt = metrics.net_debt or 0.0
    implied_equity = implied_ev - net_debt
    if implied_equity <= 0:
        return None
    return implied_equity / shares


_METHODS = {
    "pe": _implied_price_pe,
    "pb": _implied_price_pb,
    "ps": _implied_price_ps,
    "pfcf": _implied_price_pfcf,
    "ev_ebitda": _implied_price_ev_ebitda,
    "ev_sales": _implied_price_ev_sales,
}


def compute_fair_value(
    sector: str,
    metrics: FinancialMetrics,
    company_ratios: ComputedRatios,
    sector_stats: Optional[SectorStats],
    current_price: float,
) -> FairValueResult:
    if sector_stats is None or current_price <= 0:
        return FairValueResult(
            low=None, base=None, high=None,
            upside_pct=None, methods_used=[], weights={}
        )

    raw_weights = _SECTOR_WEIGHTS.get(sector, _SECTOR_WEIGHTS["default"]).copy()
    sector_median = sector_stats.median
    sector_mean = sector_stats.mean

    # Compute implied prices per method
    implied: dict[str, float] = {}
    implied_from_mean: dict[str, float] = {}

    for method, weight in raw_weights.items():
        if method not in _METHODS:
            continue
        fn = _METHODS[method]
        median_multiple = getattr(sector_median, method, None)
        mean_multiple = getattr(sector_mean, method, None)

        if method == "pe":
            base_price = fn(median_multiple, company_ratios, metrics, current_price)
            mean_price = fn(mean_multiple, company_ratios, metrics, current_price)
        elif method == "pb":
            base_price = fn(median_multiple, metrics)
            mean_price = fn(mean_multiple, metrics)
        elif method in ("ps", "pfcf"):
            base_price = fn(median_multiple, metrics)
            mean_price = fn(mean_multiple, metrics)
        elif method in ("ev_ebitda", "ev_sales"):
            base_price = fn(median_multiple, metrics)
            mean_price = fn(mean_multiple, metrics)
        else:
            base_price = None
            mean_price = None

        if base_price and 0 < base_price < current_price * 10:
            implied[method] = base_price
        if mean_price and 0 < mean_price < current_price * 10:
            implied_from_mean[method] = mean_price

    if not implied:
        return FairValueResult(
            low=None, base=None, high=None,
            upside_pct=None, methods_used=[], weights={}
        )

    # Normalise weights to only include valid methods
    valid_weights = {m: raw_weights[m] for m in implied}
    valid_weights = _normalize_weights(valid_weights)

    # Weighted base fair value (using sector median multiples)
    base_fv = sum(implied[m] * valid_weights[m] for m in implied)

    # High: use sector mean (often higher for growth sectors)
    if implied_from_mean:
        valid_w_mean = {m: raw_weights[m] for m in implied_from_mean}
        valid_w_mean = _normalize_weights(valid_w_mean)
        high_fv = sum(implied_from_mean[m] * valid_w_mean[m] for m in implied_from_mean)
    else:
        high_fv = base_fv * 1.10  # 10% above base as rough upper

    # Low: discount base by 10% (sector median can overshoot for weaker companies)
    low_fv = base_fv * 0.90

    upside_pct = (base_fv - current_price) / current_price * 100

    return FairValueResult(
        low=round(low_fv, 2),
        base=round(base_fv, 2),
        high=round(high_fv, 2),
        upside_pct=round(upside_pct, 1),
        methods_used=list(implied.keys()),
        weights={m: round(w, 3) for m, w in valid_weights.items()},
    )
