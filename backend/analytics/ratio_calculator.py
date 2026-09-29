"""Compute valuation and quality ratios from financial metrics."""
from __future__ import annotations

import logging
from typing import Optional

from backend.models.schemas import ComputedRatios, FinancialMetrics

logger = logging.getLogger(__name__)

_TINY = 1e-9  # guard against near-zero denominators


def _safe_div(num: Optional[float], den: Optional[float]) -> Optional[float]:
    if num is None or den is None:
        return None
    if abs(den) < _TINY:
        return None
    result = num / den
    # Suppress nonsensical multiples (e.g., very large from near-zero denominator)
    if abs(result) > 10_000:
        return None
    return result


def compute_ratios(metrics: FinancialMetrics, info: dict) -> ComputedRatios:
    price = metrics.current_price
    mktcap = metrics.market_cap
    shares = metrics.shares_outstanding

    # Derive shares if missing
    if shares is None and mktcap and price and price > 0:
        shares = mktcap / price

    # ── Valuation multiples ───────────────────────────────────────────────────
    # P/E (trailing)
    pe: Optional[float] = None
    if price and metrics.ttm_eps:
        pe = _safe_div(price, metrics.ttm_eps)
    if pe is None:
        raw_pe = info.get("trailingPE") or info.get("trailingPe")
        if raw_pe and abs(float(raw_pe)) < 10_000:
            pe = float(raw_pe)

    # Forward P/E
    forward_pe: Optional[float] = None
    raw_fpe = info.get("forwardPE")
    if raw_fpe:
        try:
            v = float(raw_fpe)
            if 0 < v < 10_000:
                forward_pe = v
        except Exception:
            pass

    # P/B
    pb: Optional[float] = None
    if price and metrics.book_value_per_share and metrics.book_value_per_share > 0:
        pb = _safe_div(price, metrics.book_value_per_share)
    if pb is None:
        raw_pb = info.get("priceToBook")
        if raw_pb:
            try:
                v = float(raw_pb)
                if 0 < v < 10_000:
                    pb = v
            except Exception:
                pass

    # P/S (trailing)
    ps: Optional[float] = None
    if price and metrics.ttm_revenue and shares and shares > 0:
        rev_per_share = metrics.ttm_revenue / shares
        ps = _safe_div(price, rev_per_share)
    if ps is None:
        raw_ps = info.get("priceToSalesTrailing12Months")
        if raw_ps:
            try:
                v = float(raw_ps)
                if 0 < v < 10_000:
                    ps = v
            except Exception:
                pass

    # P/FCF
    pfcf: Optional[float] = None
    if price and metrics.ttm_fcf and shares and shares > 0 and metrics.ttm_fcf > 0:
        fcf_per_share = metrics.ttm_fcf / shares
        pfcf = _safe_div(price, fcf_per_share)

    # EV = market cap + net debt
    ev: Optional[float] = None
    if mktcap is not None and metrics.net_debt is not None:
        ev = mktcap + metrics.net_debt
    elif mktcap is not None:
        # Rough EV without debt info
        ev = mktcap

    # EV/EBITDA
    ev_ebitda: Optional[float] = None
    if ev and metrics.ttm_ebitda and metrics.ttm_ebitda > 0:
        ev_ebitda = _safe_div(ev, metrics.ttm_ebitda)

    # EV/Sales
    ev_sales: Optional[float] = None
    if ev and metrics.ttm_revenue and metrics.ttm_revenue > 0:
        ev_sales = _safe_div(ev, metrics.ttm_revenue)

    # ── Leverage / balance sheet ──────────────────────────────────────────────
    # D/E
    de: Optional[float] = None
    if metrics.total_debt is not None and metrics.equity and metrics.equity > 0:
        de = _safe_div(metrics.total_debt, metrics.equity)

    # Net debt / EBITDA
    net_debt_ebitda: Optional[float] = None
    if metrics.net_debt is not None and metrics.ttm_ebitda and metrics.ttm_ebitda > 0:
        net_debt_ebitda = _safe_div(metrics.net_debt, metrics.ttm_ebitda)

    # ── Profitability / quality ───────────────────────────────────────────────
    # ROE
    roe: Optional[float] = None
    if metrics.ttm_net_income is not None and metrics.equity and metrics.equity > 0:
        roe = _safe_div(metrics.ttm_net_income, metrics.equity)

    # ROA
    roa: Optional[float] = None
    if metrics.ttm_net_income is not None and metrics.total_assets and metrics.total_assets > 0:
        roa = _safe_div(metrics.ttm_net_income, metrics.total_assets)

    # Gross margin
    gross_margin: Optional[float] = None
    if metrics.ttm_gross_profit is not None and metrics.ttm_revenue and metrics.ttm_revenue > 0:
        gross_margin = _safe_div(metrics.ttm_gross_profit, metrics.ttm_revenue)
    if gross_margin is None:
        raw_gm = info.get("grossMargins")
        if raw_gm is not None:
            try:
                gross_margin = float(raw_gm)
            except Exception:
                pass

    # Operating margin
    operating_margin: Optional[float] = None
    if metrics.ttm_operating_income is not None and metrics.ttm_revenue and metrics.ttm_revenue > 0:
        operating_margin = _safe_div(metrics.ttm_operating_income, metrics.ttm_revenue)
    if operating_margin is None:
        raw_om = info.get("operatingMargins")
        if raw_om is not None:
            try:
                operating_margin = float(raw_om)
            except Exception:
                pass

    # Net margin
    net_margin: Optional[float] = None
    if metrics.ttm_net_income is not None and metrics.ttm_revenue and metrics.ttm_revenue > 0:
        net_margin = _safe_div(metrics.ttm_net_income, metrics.ttm_revenue)
    if net_margin is None:
        raw_nm = info.get("profitMargins")
        if raw_nm is not None:
            try:
                net_margin = float(raw_nm)
            except Exception:
                pass

    # FCF margin
    fcf_margin: Optional[float] = None
    if metrics.ttm_fcf is not None and metrics.ttm_revenue and metrics.ttm_revenue > 0:
        fcf_margin = _safe_div(metrics.ttm_fcf, metrics.ttm_revenue)

    # ── Growth ────────────────────────────────────────────────────────────────
    # Revenue growth YoY
    revenue_growth: Optional[float] = None
    if (
        metrics.ttm_revenue is not None
        and metrics.prior_ttm_revenue
        and metrics.prior_ttm_revenue > 0
    ):
        revenue_growth = (metrics.ttm_revenue - metrics.prior_ttm_revenue) / abs(
            metrics.prior_ttm_revenue
        )
    if revenue_growth is None:
        raw_rg = info.get("revenueGrowth")
        if raw_rg is not None:
            try:
                revenue_growth = float(raw_rg)
            except Exception:
                pass

    # EPS growth
    eps_growth: Optional[float] = None
    raw_eg = info.get("earningsGrowth")
    if raw_eg is not None:
        try:
            eps_growth = float(raw_eg)
        except Exception:
            pass

    # FCF growth
    fcf_growth: Optional[float] = None
    if (
        metrics.ttm_fcf is not None
        and metrics.prior_ttm_fcf
        and metrics.prior_ttm_fcf > 0
    ):
        fcf_growth = (metrics.ttm_fcf - metrics.prior_ttm_fcf) / abs(
            metrics.prior_ttm_fcf
        )

    return ComputedRatios(
        pe=pe,
        forward_pe=forward_pe,
        pb=pb,
        ps=ps,
        pfcf=pfcf,
        ev_ebitda=ev_ebitda,
        ev_sales=ev_sales,
        de=de,
        net_debt_ebitda=net_debt_ebitda,
        current_ratio=metrics.current_ratio,
        roe=roe,
        roa=roa,
        gross_margin=gross_margin,
        operating_margin=operating_margin,
        net_margin=net_margin,
        fcf_margin=fcf_margin,
        revenue_growth=revenue_growth,
        eps_growth=eps_growth,
        fcf_growth=fcf_growth,
    )
