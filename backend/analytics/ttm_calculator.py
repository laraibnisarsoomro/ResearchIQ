"""Compute trailing-twelve-month metrics from quarterly financial statements."""
from __future__ import annotations

import logging
from typing import Optional

import pandas as pd

from backend.data.yfinance_client import (
    INCOME_ALIASES,
    BALANCE_ALIASES,
    CASHFLOW_ALIASES,
    extract_field,
    safe_scalar,
    ttm_sum,
    ttm_mean,
)
from backend.models.schemas import FinancialMetrics

logger = logging.getLogger(__name__)


def _coalesce(*vals):
    for v in vals:
        if v is not None:
            return v
    return None


def compute_ttm(
    info: dict,
    income: Optional[pd.DataFrame],
    balance: Optional[pd.DataFrame],
    cashflow: Optional[pd.DataFrame],
) -> FinancialMetrics:
    """Build FinancialMetrics from yfinance data."""

    # ── Market data from info dict ────────────────────────────────────────────
    def _g(key: str) -> Optional[float]:
        v = info.get(key)
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return None
        try:
            return float(v)
        except Exception:
            return None

    current_price = _coalesce(_g("currentPrice"), _g("regularMarketPrice"), _g("ask"))
    prev_close = _coalesce(_g("previousClose"), _g("regularMarketPreviousClose"))
    week_52_low = _g("fiftyTwoWeekLow")
    week_52_high = _g("fiftyTwoWeekHigh")
    market_cap = _g("marketCap")
    shares_outstanding = _coalesce(_g("sharesOutstanding"), _g("impliedSharesOutstanding"))
    beta = _g("beta")

    # ── Income statement TTM ──────────────────────────────────────────────────
    rev_series = extract_field(income, INCOME_ALIASES["revenue"])
    gp_series = extract_field(income, INCOME_ALIASES["gross_profit"])
    oi_series = extract_field(income, INCOME_ALIASES["operating_income"])
    ni_series = extract_field(income, INCOME_ALIASES["net_income"])
    ebitda_series = extract_field(income, INCOME_ALIASES["ebitda"])
    eps_series = extract_field(income, INCOME_ALIASES["eps_basic"])

    ttm_revenue = _coalesce(ttm_sum(rev_series), _g("totalRevenue"))
    ttm_gross_profit = _coalesce(ttm_sum(gp_series), _g("grossProfits"))
    ttm_operating_income = _coalesce(ttm_sum(oi_series), _g("operatingIncome"), _g("ebit"))
    ttm_net_income = _coalesce(ttm_sum(ni_series), _g("netIncome"), _g("netIncomeToCommon"))
    ttm_ebitda = _coalesce(ttm_sum(ebitda_series), _g("ebitda"))

    # Build TTM EPS
    if eps_series is not None and not eps_series.dropna().empty:
        ttm_eps = ttm_sum(eps_series)
    elif ttm_net_income and shares_outstanding and shares_outstanding > 0:
        ttm_eps = ttm_net_income / shares_outstanding
    else:
        ttm_eps = _g("trailingEps") or _g("trailingEPS")

    # ── EBITDA estimation if not directly available ───────────────────────────
    if ttm_ebitda is None and ttm_operating_income is not None:
        # Rough estimate: EBITDA ≈ EBIT + D&A; we skip D&A if unknown
        ttm_ebitda = ttm_operating_income  # conservative underestimate

    # ── Cash flow TTM ─────────────────────────────────────────────────────────
    ocf_series = extract_field(cashflow, CASHFLOW_ALIASES["operating_cf"])
    capex_series = extract_field(cashflow, CASHFLOW_ALIASES["capex"])
    fcf_series = extract_field(cashflow, CASHFLOW_ALIASES["free_cash_flow"])

    ttm_operating_cf = ttm_sum(ocf_series) or _g("operatingCashflow")
    ttm_capex = ttm_sum(capex_series)
    if ttm_capex is not None:
        # capex in yfinance is usually negative; make it positive for display
        ttm_capex = abs(ttm_capex)

    # Compute TTM FCF
    if fcf_series is not None and not fcf_series.dropna().empty:
        ttm_fcf = ttm_sum(fcf_series)
    elif ttm_operating_cf is not None and ttm_capex is not None:
        ttm_fcf = ttm_operating_cf - ttm_capex
    else:
        ttm_fcf = _g("freeCashflow")

    # ── Balance sheet (most recent quarter) ──────────────────────────────────
    def _bs(key: str) -> Optional[float]:
        series = extract_field(balance, BALANCE_ALIASES[key])
        return safe_scalar(series, 0)

    total_assets = _bs("total_assets")
    total_debt = _bs("total_debt")
    if total_debt is None:
        short_term = _bs("short_term_debt") or 0.0
        total_debt = (_g("longTermDebt") or 0.0) + short_term
        total_debt = total_debt if total_debt else None
    cash = _bs("cash") or _g("totalCash")
    equity = _bs("equity") or _g("bookValue")
    current_assets = _bs("current_assets")
    current_liabilities = _bs("current_liabilities")

    # Shares outstanding from balance sheet if missing from info
    if shares_outstanding is None:
        shares_bs = _bs("shares_outstanding")
        if shares_bs:
            shares_outstanding = shares_bs

    # Derived BS metrics
    net_debt: Optional[float] = None
    if total_debt is not None and cash is not None:
        net_debt = total_debt - cash

    book_value_per_share: Optional[float] = None
    if equity and shares_outstanding and shares_outstanding > 0:
        book_value_per_share = equity / shares_outstanding
    elif equity and market_cap and current_price and current_price > 0:
        # Estimate shares from market cap
        est_shares = market_cap / current_price
        book_value_per_share = equity / est_shares

    current_ratio: Optional[float] = None
    if current_assets and current_liabilities and current_liabilities > 0:
        current_ratio = current_assets / current_liabilities

    # ── Prior-year TTM (for YoY growth) ──────────────────────────────────────
    # Use quarters 5-8 for prior-year TTM
    prior_ttm_revenue = _ttm_prior(rev_series)
    prior_ttm_net_income = _ttm_prior(ni_series)
    prior_ttm_fcf: Optional[float] = None
    if fcf_series is not None and not fcf_series.dropna().empty:
        prior_ttm_fcf = _ttm_prior(fcf_series)
    elif ocf_series is not None and capex_series is not None:
        prior_ocf = _ttm_prior(ocf_series)
        prior_capex = _ttm_prior(capex_series)
        if prior_ocf is not None and prior_capex is not None:
            prior_ttm_fcf = prior_ocf - abs(prior_capex)

    return FinancialMetrics(
        current_price=current_price,
        prev_close=prev_close,
        week_52_low=week_52_low,
        week_52_high=week_52_high,
        market_cap=market_cap,
        shares_outstanding=shares_outstanding,
        beta=beta,
        ttm_revenue=ttm_revenue,
        ttm_gross_profit=ttm_gross_profit,
        ttm_operating_income=ttm_operating_income,
        ttm_net_income=ttm_net_income,
        ttm_ebitda=ttm_ebitda,
        ttm_eps=ttm_eps,
        ttm_operating_cf=ttm_operating_cf,
        ttm_capex=ttm_capex,
        ttm_fcf=ttm_fcf,
        total_assets=total_assets,
        total_debt=total_debt,
        cash=cash,
        net_debt=net_debt,
        equity=equity,
        book_value_per_share=book_value_per_share,
        current_ratio=current_ratio,
        prior_ttm_revenue=prior_ttm_revenue,
        prior_ttm_net_income=prior_ttm_net_income,
        prior_ttm_fcf=prior_ttm_fcf,
    )


def _ttm_prior(series: Optional[pd.Series], skip: int = 4, n: int = 4, min_quarters: int = 4) -> Optional[float]:
    """
    Sum quarters skip through skip+n (prior-year TTM).
    Returns None if there are fewer than skip+min_quarters valid data points,
    preventing a spurious growth rate from incomplete prior-year coverage.
    """
    if series is None or series.empty:
        return None
    vals = series.dropna()
    if len(vals) < skip + min_quarters:
        return None
    segment = vals.iloc[skip: skip + n]
    if len(segment) < min_quarters:
        return None
    return float(segment.sum())
