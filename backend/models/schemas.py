from __future__ import annotations
from typing import Optional
from pydantic import BaseModel


class ReportRequest(BaseModel):
    ticker: str


class MetricRow(BaseModel):
    metric: str
    company: Optional[str] = "N/M"
    sector_mean: Optional[str] = "N/M"
    sector_median: Optional[str] = "N/M"
    vs_peers: Optional[str] = "—"
    note: Optional[str] = None


class FairValueResult(BaseModel):
    low: Optional[float]
    base: Optional[float]
    high: Optional[float]
    upside_pct: Optional[float]
    methods_used: list[str]
    weights: dict[str, float]


class RecommendationResult(BaseModel):
    recommendation: str          # Buy / Hold / Sell
    confidence: str              # High / Medium / Low
    rationale: str
    quality_score: float         # 0.0 – 1.0
    data_completeness: float     # 0.0 – 1.0


class CompanyProfile(BaseModel):
    ticker: str
    name: str
    sector: str
    industry: str
    exchange: str
    description: str
    revenue_model: str


class FinancialMetrics(BaseModel):
    # Price / market
    current_price: Optional[float]
    prev_close: Optional[float]
    week_52_low: Optional[float]
    week_52_high: Optional[float]
    market_cap: Optional[float]
    shares_outstanding: Optional[float]
    beta: Optional[float]
    # TTM income
    ttm_revenue: Optional[float]
    ttm_gross_profit: Optional[float]
    ttm_operating_income: Optional[float]
    ttm_net_income: Optional[float]
    ttm_ebitda: Optional[float]
    ttm_eps: Optional[float]
    # TTM cash flow
    ttm_operating_cf: Optional[float]
    ttm_capex: Optional[float]
    ttm_fcf: Optional[float]
    # Balance sheet (most recent quarter)
    total_assets: Optional[float]
    total_debt: Optional[float]
    cash: Optional[float]
    net_debt: Optional[float]
    equity: Optional[float]
    book_value_per_share: Optional[float]
    current_ratio: Optional[float]
    # Prior year TTM (for growth)
    prior_ttm_revenue: Optional[float]
    prior_ttm_net_income: Optional[float]
    prior_ttm_fcf: Optional[float]


class ComputedRatios(BaseModel):
    pe: Optional[float]
    forward_pe: Optional[float]
    pb: Optional[float]
    ps: Optional[float]
    pfcf: Optional[float]
    ev_ebitda: Optional[float]
    ev_sales: Optional[float]
    de: Optional[float]
    net_debt_ebitda: Optional[float]
    current_ratio: Optional[float]
    roe: Optional[float]
    roa: Optional[float]
    gross_margin: Optional[float]
    operating_margin: Optional[float]
    net_margin: Optional[float]
    fcf_margin: Optional[float]
    revenue_growth: Optional[float]
    eps_growth: Optional[float]
    fcf_growth: Optional[float]


class SectorStats(BaseModel):
    sector: str
    peer_count: int
    mean: ComputedRatios
    median: ComputedRatios


class ResearchContent(BaseModel):
    investment_thesis: list[str]
    sector_overview: str
    key_risks: list[str]
    key_catalysts: list[str]
    news_used: list[str]


class EquityReport(BaseModel):
    # Header
    ticker: str
    company_name: str
    sector: str
    industry: str
    exchange: str
    generated_at: str
    data_as_of: str
    # Valuation
    current_price: float
    fair_value_low: Optional[float]
    fair_value_base: Optional[float]
    fair_value_high: Optional[float]
    upside_pct: Optional[float]
    valuation_methods: list[str]
    # Recommendation
    recommendation: str
    confidence: str
    rationale: str
    # Narrative
    description: str
    revenue_model: str
    investment_thesis: list[str]
    sector_overview: str
    key_risks: list[str]
    key_catalysts: list[str]
    # Data tables
    metrics_table: list[MetricRow]
    # Price history
    price_history: Optional[dict] = None
    # Branding
    website: Optional[str] = None
    # Meta
    peer_count: int
    data_completeness_pct: int
    caveats: list[str]


class ProgressEvent(BaseModel):
    stage: int
    total_stages: int
    message: str
    done: bool = False
    error: Optional[str] = None
    report: Optional[EquityReport] = None
