"""Portfolio builder — request/response schemas."""
from __future__ import annotations
from typing import Optional
from pydantic import BaseModel


class PortfolioRequest(BaseModel):
    # Anchor
    anchor_ticker: str
    anchor_sector: str
    anchor_recommendation: str
    anchor_upside_pct: Optional[float] = None

    # Section A
    age: int
    investor_type: str          # Individual | Institutional
    investor_subtype: str       # employment status or institution type

    # Section B
    investment_amount: float
    horizon: str                # Short-term | Medium-term | Long-term

    # Section C
    objective: str
    drawdown_tolerance: str
    experience: str

    # Section D
    sectors: list[str]

    # Section E
    max_positions: int          # 5 | 10 | 15 | 20
    sizing_style: str           # Equal Weight | Conviction-Weighted | Sector-Concentrated


class PositionRow(BaseModel):
    ticker: str
    company: str
    sector: str
    upside_pct: float           # valuation gap — used for selection, not displayed
    expected_return_pct: float  # CAPM + alpha — what gets shown in the table
    weight_pct: float
    dollar_amount: float
    beta: Optional[float] = None


class PortfolioStats(BaseModel):
    strategy: str
    strategy_description: str
    net_exposure_pct: float
    gross_exposure_pct: float
    long_book_usd: float
    short_book_usd: float
    n_long: int
    n_short: int
    sectors_covered: list[str]
    portfolio_beta: float
    market_vol_pct: float
    portfolio_vol_pct: float
    expected_return_pct: float
    expected_return_usd: float
    sharpe_ratio: float
    risk_free_rate_pct: float
    risk_free_source: str


class PortfolioResponse(BaseModel):
    strategy: str
    strategy_description: str
    stats: PortfolioStats
    long_positions: list[PositionRow]
    short_positions: list[PositionRow]
    pairs_long_ticker: Optional[str] = None
    pairs_long_company: Optional[str] = None
    pairs_short_ticker: Optional[str] = None
    pairs_short_company: Optional[str] = None
    pairs_sector: Optional[str] = None
    rationale: str
    warning: Optional[str] = None
