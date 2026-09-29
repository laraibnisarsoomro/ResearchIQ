"""Portfolio construction — filters universe, ranks candidates, sizes positions,
computes all statistics deterministically. No LLM touches any number here."""
from __future__ import annotations

import asyncio
import json
import logging
import math
from typing import Optional

import yfinance as yf
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import CompanyRatiosCache, UniverseEntry
from backend.portfolio.schemas import PositionRow, PortfolioStats
from backend.portfolio.strategy import (
    STRATEGY_LONG_ONLY,
    strategy_books,
)

logger = logging.getLogger(__name__)

# Per-position caps keyed by max_positions setting
_POSITION_CAPS = {5: 0.20, 10: 0.15, 15: 0.10, 20: 0.07}


# ── Candidate data class ──────────────────────────────────────────────────────

class Candidate:
    __slots__ = ("ticker", "company", "sector", "upside_pct", "beta")

    def __init__(self, ticker: str, company: str, sector: str, upside_pct: float, beta: float):
        self.ticker = ticker
        self.company = company
        self.sector = sector
        self.upside_pct = upside_pct
        self.beta = beta


# ── Sector beta fallbacks (used when per-stock beta is missing) ───────────────

_SECTOR_BETAS = {
    "Information Technology": 1.25,
    "Communication Services": 1.10,
    "Consumer Discretionary": 1.15,
    "Financials": 1.05,
    "Health Care": 0.75,
    "Industrials": 1.00,
    "Consumer Staples": 0.55,
    "Energy": 0.85,
    "Materials": 0.95,
    "Real Estate": 0.70,
    "Utilities": 0.45,
}


# ── Market volatility (SPY 252-day) ──────────────────────────────────────────

def _fetch_market_vol_sync() -> float:
    try:
        spy = yf.download("SPY", period="1y", progress=False)
        if isinstance(spy.columns, __import__("pandas").MultiIndex):
            closes = spy[("Close", "SPY")].dropna()
        else:
            closes = spy["Close"].dropna()
        returns = closes.pct_change().dropna()
        return float(returns.std() * math.sqrt(252))
    except Exception:
        return 0.15  # fallback: 15% annualised


async def fetch_market_vol() -> float:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _fetch_market_vol_sync)


# ── Risk-free rate (FRED DTB3) ────────────────────────────────────────────────

def _fetch_rfr_sync() -> tuple[float, str]:
    try:
        import urllib.request
        url = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DTB3"
        with urllib.request.urlopen(url, timeout=5) as resp:
            lines = resp.read().decode().strip().split("\n")
        for line in reversed(lines):
            parts = line.split(",")
            if len(parts) == 2 and parts[1] not in (".", ""):
                rate = float(parts[1]) / 100
                return rate, "FRED DTB3"
    except Exception:
        pass
    return 0.043, "Fallback (4.3%)"


async def fetch_risk_free_rate() -> tuple[float, str]:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _fetch_rfr_sync)


# ── Universe scraping from cached ratios ──────────────────────────────────────

async def load_candidates(
    db: AsyncSession,
    sectors: list[str],
    anchor_ticker: str,
) -> list[Candidate]:
    """Load cached upside scores from CompanyRatiosCache + UniverseEntry."""
    result = await db.execute(
        select(CompanyRatiosCache).where(CompanyRatiosCache.sector.in_(sectors))
    )
    ratio_rows = result.scalars().all()

    # Build universe lookup
    uni_result = await db.execute(select(UniverseEntry))
    universe = {r.ticker: r for r in uni_result.scalars().all()}

    candidates: list[Candidate] = []
    for row in ratio_rows:
        if row.ticker == anchor_ticker:
            continue
        try:
            ratios_dict = json.loads(row.ratios_json)
        except Exception:
            continue

        # upside_pct is stored under key "upside_pct" if present
        upside = ratios_dict.get("upside_pct")
        if upside is None:
            continue

        beta = ratios_dict.get("beta")
        if beta is None or not (0.0 < beta < 5.0):
            beta = _SECTOR_BETAS.get(row.sector, 1.0)

        uni_entry = universe.get(row.ticker)
        company = uni_entry.name if uni_entry else row.ticker

        # Clamp stored upside to ±60% — anything beyond this is almost
        # certainly a comparable distortion, not a real return estimate.
        # (e.g., AMC benchmarked against Netflix multiples, stale seeded targets)
        clamped_upside = max(min(float(upside), 60.0), -60.0)

        candidates.append(Candidate(
            ticker=row.ticker,
            company=company,
            sector=row.sector,
            upside_pct=clamped_upside,
            beta=float(beta),
        ))

    return candidates


# ── Position sizing ───────────────────────────────────────────────────────────

def _size_positions(
    candidates: list[Candidate],
    book_usd: float,
    max_positions: int,
    sizing_style: str,
    sectors: list[str],
    cap: float,
    long_side: bool,
) -> list[PositionRow]:
    if not candidates:
        return []

    n = min(len(candidates), max_positions)
    pool = candidates[:n]

    if sizing_style == "Equal Weight":
        raw_weights = [1.0 / n] * n

    elif sizing_style == "Conviction-Weighted":
        # Cap each position's magnitude at 40% so no single stock overwhelms
        # the portfolio even if its upside is at the top of the allowed range.
        magnitudes = [min(abs(c.upside_pct), 40.0) for c in pool]
        total = sum(magnitudes) or 1.0
        raw_weights = [m / total for m in magnitudes]

    else:  # Sector-Concentrated
        # Find top 2 sectors by candidate count
        from collections import Counter
        sector_counts = Counter(c.sector for c in pool)
        top_sectors = {s for s, _ in sector_counts.most_common(2)}
        boost = 1.5
        raw = []
        for c in pool:
            raw.append(boost if c.sector in top_sectors else 1.0)
        total = sum(raw) or 1.0
        raw_weights = [r / total for r in raw]

    # Apply position cap and renormalise
    capped = [min(w, cap) for w in raw_weights]
    total = sum(capped) or 1.0
    weights = [w / total for w in capped]

    rows = []
    for i, c in enumerate(pool):
        w = weights[i]
        dollar = book_usd * w
        rows.append(PositionRow(
            ticker=c.ticker,
            company=c.company,
            sector=c.sector,
            upside_pct=c.upside_pct,
            expected_return_pct=0.0,  # filled in build_portfolio after rfr is known
            weight_pct=round(w * 100, 2),
            dollar_amount=round(dollar, 2),
            beta=c.beta,
        ))
    return rows


# ── Main builder ──────────────────────────────────────────────────────────────

async def build_portfolio(
    db: AsyncSession,
    anchor_ticker: str,
    sectors: list[str],
    investment_amount: float,
    max_positions: int,
    sizing_style: str,
    strategy: str,
) -> tuple[list[PositionRow], list[PositionRow], PortfolioStats, str | None]:
    """
    Returns (long_positions, short_positions, stats, warning).
    All numbers computed here — LLM never touches them.
    """
    candidates = await load_candidates(db, sectors, anchor_ticker)

    # Long candidates: meaningful upside only (≥5% avoids noise near zero)
    # Short candidates: meaningful downside only (≤-5%)
    # The ±60% ceiling was already applied in load_candidates via clamping.
    longs = sorted([c for c in candidates if c.upside_pct >= 5.0], key=lambda x: -x.upside_pct)
    shorts = sorted([c for c in candidates if c.upside_pct <= -5.0], key=lambda x: x.upside_pct)

    warning: str | None = None
    if len(longs) < 3:
        warning = (
            "Insufficient Buy-rated names in selected sectors. "
            "Consider expanding your sector selection."
        )

    long_pct, short_pct, net_exp_pct, gross_exp_pct = strategy_books(strategy, investment_amount)
    long_book_usd = investment_amount * long_pct
    short_book_usd = investment_amount * short_pct

    pos_cap = _POSITION_CAPS.get(max_positions, 0.10)

    # Split max_positions proportionally between books
    if strategy == STRATEGY_LONG_ONLY:
        n_long_slots = max_positions
        n_short_slots = 0
    else:
        n_long_slots = max(2, round(max_positions * 0.65))
        n_short_slots = max_positions - n_long_slots

    long_positions = _size_positions(
        longs, long_book_usd, n_long_slots, sizing_style, sectors, pos_cap, long_side=True
    )
    short_positions = [] if strategy == STRATEGY_LONG_ONLY else _size_positions(
        shorts, short_book_usd, n_short_slots, sizing_style, sectors, pos_cap, long_side=False
    )

    # ── Statistics (all deterministic) ────────────────────────────────────────
    market_vol, (rfr, rfr_source) = await asyncio.gather(
        fetch_market_vol(),
        fetch_risk_free_rate(),
    )

    # ── Per-position expected return (CAPM + bounded alpha) ───────────────────
    # This is what appears in the portfolio table — same model as the portfolio
    # total, so individual rows are directly consistent with the headline number.
    _ERP = 0.05
    _DISC = 0.25
    _ACAP = 0.06
    for pos in long_positions:
        b = pos.beta or _SECTOR_BETAS.get(pos.sector, 1.0)
        capm_i = rfr + b * _ERP
        alpha_i = min(max(pos.upside_pct, 0.0) / 100.0 * _DISC, _ACAP)
        pos.expected_return_pct = round((capm_i + alpha_i) * 100, 1)
    for pos in short_positions:
        b = pos.beta or _SECTOR_BETAS.get(pos.sector, 1.0)
        capm_i = rfr + b * _ERP
        alpha_i = min(max(-pos.upside_pct, 0.0) / 100.0 * _DISC, _ACAP)
        pos.expected_return_pct = round((capm_i + alpha_i) * 100, 1)

    # Portfolio beta (net: longs positive, shorts negative)
    portfolio_beta = 0.0
    for pos in long_positions:
        b = pos.beta or _SECTOR_BETAS.get(pos.sector, 1.0)
        portfolio_beta += (pos.weight_pct / 100) * long_pct * b
    for pos in short_positions:
        b = pos.beta or _SECTOR_BETAS.get(pos.sector, 1.0)
        portfolio_beta -= (pos.weight_pct / 100) * short_pct * b

    # ── Volatility ─────────────────────────────────────────────────────────────
    # Systematic component from net beta, plus idiosyncratic from concentration.
    # Idiosyncratic vol of a single stock ≈ 35%; diversification reduces it by √n.
    n_positions = len(long_positions) + len(short_positions)
    idio_vol = 0.35 / math.sqrt(max(n_positions, 1))
    systematic_vol = abs(portfolio_beta) * market_vol
    portfolio_vol = math.sqrt(systematic_vol ** 2 + idio_vol ** 2)
    portfolio_vol = max(portfolio_vol, 0.08)  # no realistic equity portfolio has <8% annual vol

    # ── Expected return via CAPM + bounded valuation alpha ─────────────────────
    # Upside_pct is a valuation gap (distance to fair value), NOT a 12-month return.
    # Academic research (Brav & Lehavy 2003; Jegadeesh et al. 2004) shows analyst
    # price target gaps realize ~20-25% of their stated magnitude over 12 months.
    # Our comparables-based estimates are more conservative; we use 25%.
    ERP = 0.05          # Long-run equity risk premium (Damodaran consensus)
    ALPHA_DISCOUNT = 0.25   # Fraction of valuation gap expected to close in 12 months
    ALPHA_CAP = 0.06    # Max alpha above CAPM: 6% (top-decile active manager territory)

    # CAPM base: compensation for systematic risk only
    capm_return = rfr + abs(portfolio_beta) * ERP

    # Valuation alpha: discounted and capped
    raw_alpha_long = sum(
        (p.weight_pct / 100) * long_pct * max(p.upside_pct, 0.0) / 100
        for p in long_positions
    )
    raw_alpha_short = sum(
        (p.weight_pct / 100) * short_pct * max(-p.upside_pct, 0.0) / 100
        for p in short_positions
    )
    alpha = min((raw_alpha_long + raw_alpha_short) * ALPHA_DISCOUNT, ALPHA_CAP)

    expected_return = capm_return + alpha

    sharpe = (expected_return - rfr) / portfolio_vol if portfolio_vol > 0 else 0.0

    sectors_covered = sorted({p.sector for p in long_positions} | {p.sector for p in short_positions})

    stats = PortfolioStats(
        strategy=strategy,
        strategy_description="",
        net_exposure_pct=round(net_exp_pct * 100, 1),
        gross_exposure_pct=round(gross_exp_pct * 100, 1),
        long_book_usd=round(long_book_usd, 2),
        short_book_usd=round(short_book_usd, 2),
        n_long=len(long_positions),
        n_short=len(short_positions),
        sectors_covered=sectors_covered,
        portfolio_beta=round(portfolio_beta, 3),
        market_vol_pct=round(market_vol * 100, 2),
        portfolio_vol_pct=round(portfolio_vol * 100, 2),
        expected_return_pct=round(expected_return * 100, 2),
        expected_return_usd=round(investment_amount * expected_return, 2),
        sharpe_ratio=round(sharpe, 2),
        risk_free_rate_pct=round(rfr * 100, 2),
        risk_free_source=rfr_source,
    )

    return long_positions, short_positions, stats, warning
