"""Agent 6 — Assemble the final EquityReport from all agent outputs."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from backend.agents.data_retrieval import CompanyData
from backend.agents.financial_processor import ProcessedFinancials
from backend.agents.research_writer import ResearchContent
from backend.agents.valuation_agent import ValuationOutput
from backend.models.schemas import (
    CompanyProfile,
    EquityReport,
    MetricRow,
)

logger = logging.getLogger(__name__)


def _fmt_x(v: Optional[float], nm_if_negative: bool = True) -> str:
    if v is None:
        return "N/M"
    if nm_if_negative and v < 0:
        return "N/M"
    return f"{v:.1f}x"


def _fmt_pct(v: Optional[float]) -> str:
    if v is None:
        return "N/M"
    return f"{v*100:.1f}%"


def _vs_peers(
    company: Optional[float],
    median: Optional[float],
    lower_is_better: bool = False,
    quality: bool = False,
) -> str:
    if company is None or median is None or median == 0:
        return "—"
    ratio = company / median
    if quality:
        return "SUPERIOR" if ratio > 1.15 else ("BELOW" if ratio < 0.85 else "INLINE")
    if lower_is_better:
        return "FAVORABLE" if ratio < 0.85 else ("ELEVATED" if ratio > 1.20 else "INLINE")
    return "PREMIUM" if ratio > 1.15 else ("DISCOUNT" if ratio < 0.85 else "INLINE")


def build_metrics_table(
    processed: ProcessedFinancials,
    data: CompanyData,
) -> list[MetricRow]:
    r = processed.ratios
    sm = processed.sector_stats.median if processed.sector_stats else None
    smn = processed.sector_stats.mean if processed.sector_stats else None

    rows: list[MetricRow] = []

    def _row(
        metric: str,
        company_val: Optional[float],
        sector_mean_val: Optional[float],
        sector_median_val: Optional[float],
        fmt_fn,
        lower_is_better: bool = False,
        is_quality: bool = False,
        note: Optional[str] = None,
    ) -> MetricRow:
        co_str = fmt_fn(company_val)
        sm_str = fmt_fn(sector_median_val)
        smn_str = fmt_fn(sector_mean_val)
        vs = _vs_peers(company_val, sector_median_val, lower_is_better, quality=is_quality)
        return MetricRow(
            metric=metric,
            company=co_str,
            sector_mean=smn_str,
            sector_median=sm_str,
            vs_peers=vs,
            note=note,
        )

    # Valuation multiples
    rows.append(_row("P/E (TTM)", r.pe, smn.pe if smn else None, sm.pe if sm else None, _fmt_x, lower_is_better=True))
    if r.forward_pe is not None:
        rows.append(_row("P/E (Fwd)", r.forward_pe, None, None, _fmt_x, lower_is_better=True))
    rows.append(_row("P/B", r.pb, smn.pb if smn else None, sm.pb if sm else None, _fmt_x, lower_is_better=True))
    rows.append(_row("P/S", r.ps, smn.ps if smn else None, sm.ps if sm else None, _fmt_x, lower_is_better=True))
    if r.pfcf is not None:
        rows.append(_row("P/FCF", r.pfcf, smn.pfcf if smn else None, sm.pfcf if sm else None, _fmt_x, lower_is_better=True))
    if r.ev_ebitda is not None:
        rows.append(_row("EV/EBITDA", r.ev_ebitda, smn.ev_ebitda if smn else None, sm.ev_ebitda if sm else None, _fmt_x, lower_is_better=True))
    if r.ev_sales is not None:
        rows.append(_row("EV/Sales", r.ev_sales, smn.ev_sales if smn else None, sm.ev_sales if sm else None, _fmt_x, lower_is_better=True))

    # Separator — leverage
    rows.append(_row("D/E Ratio", r.de, smn.de if smn else None, sm.de if sm else None, _fmt_x, lower_is_better=True))
    if r.net_debt_ebitda is not None:
        rows.append(_row("Net Debt/EBITDA", r.net_debt_ebitda, smn.net_debt_ebitda if smn else None, sm.net_debt_ebitda if sm else None, _fmt_x, lower_is_better=True))
    if r.current_ratio is not None:
        rows.append(_row("Current Ratio", r.current_ratio, None, None, lambda v: f"{v:.2f}x" if v else "N/M"))

    # Profitability
    rows.append(_row("ROE", r.roe, smn.roe if smn else None, sm.roe if sm else None, _fmt_pct, is_quality=True))
    rows.append(_row("ROA", r.roa, smn.roa if smn else None, sm.roa if sm else None, _fmt_pct, is_quality=True))
    if r.gross_margin is not None:
        rows.append(_row("Gross Margin", r.gross_margin, smn.gross_margin if smn else None, sm.gross_margin if sm else None, _fmt_pct, is_quality=True))
    rows.append(_row("Operating Margin", r.operating_margin, smn.operating_margin if smn else None, sm.operating_margin if sm else None, _fmt_pct, is_quality=True))
    rows.append(_row("Net Margin", r.net_margin, smn.net_margin if smn else None, sm.net_margin if sm else None, _fmt_pct, is_quality=True))
    if r.fcf_margin is not None:
        rows.append(_row("FCF Margin", r.fcf_margin, smn.fcf_margin if smn else None, sm.fcf_margin if sm else None, _fmt_pct, is_quality=True))

    # Growth
    rows.append(_row("Revenue Growth (YoY)", r.revenue_growth, smn.revenue_growth if smn else None, sm.revenue_growth if sm else None, _fmt_pct, is_quality=True))
    if r.eps_growth is not None:
        rows.append(_row("EPS Growth (YoY)", r.eps_growth, smn.eps_growth if smn else None, sm.eps_growth if sm else None, _fmt_pct, is_quality=True))
    if r.fcf_growth is not None:
        rows.append(_row("FCF Growth (YoY)", r.fcf_growth, smn.fcf_growth if smn else None, sm.fcf_growth if sm else None, _fmt_pct, is_quality=True))

    return rows


def compose_report(
    profile: CompanyProfile,
    data: CompanyData,
    processed: ProcessedFinancials,
    valuation: ValuationOutput,
    research: ResearchContent,
) -> EquityReport:
    metrics = processed.metrics
    fv = valuation.fair_value
    rec = valuation.recommendation

    current_price = metrics.current_price or 0.0
    generated_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    data_as_of = datetime.utcnow().strftime("%Y-%m-%d")

    metrics_table = build_metrics_table(processed, data)

    # Caveats
    caveats: list[str] = [
        "This memo is for educational and research purposes only. It is not investment advice.",
        f"Peer set: S&P 500 {profile.sector} constituents ({processed.sector_stats.peer_count if processed.sector_stats else 0} companies with available data).",
        f"Valuation uses sector median comparables via: {', '.join(fv.methods_used) if fv.methods_used else 'N/M'}.",
        "N/M = Not Meaningful (negative denominator or insufficient data).",
        "TTM = Trailing Twelve Months. Balance sheet items as of most recent quarter.",
    ]
    if not data.has_financials:
        caveats.append("Quarterly financial statements unavailable; some metrics estimated from summary data.")

    # Split once and reuse for both description and revenue model
    raw_desc = data.long_description or ""
    sentences = [s.strip() for s in raw_desc.split(". ") if s.strip()] if raw_desc else []

    if len(sentences) >= 3:
        desc = ". ".join(sentences[:3]) + "."
    elif sentences:
        desc = raw_desc
    else:
        desc = f"{profile.name} operates in the {profile.sector} sector."

    if len(sentences) > 4:
        revenue_model = ". ".join(sentences[3:6]) + "."
    elif sentences:
        revenue_model = sentences[-1] + "."
    else:
        margin = metrics.ttm_gross_profit / metrics.ttm_revenue if (metrics.ttm_revenue and metrics.ttm_gross_profit) else None
        margin_str = f" with ~{margin*100:.0f}% gross margins" if margin else ""
        revenue_model = (
            f"{profile.name} generates revenue primarily through "
            f"{profile.industry or profile.sector} operations{margin_str}."
        )

    return EquityReport(
        ticker=profile.ticker,
        company_name=profile.name,
        sector=profile.sector,
        industry=profile.industry,
        exchange=profile.exchange,
        generated_at=generated_at,
        data_as_of=data_as_of,
        current_price=current_price,
        fair_value_low=fv.low,
        fair_value_base=fv.base,
        fair_value_high=fv.high,
        upside_pct=fv.upside_pct,
        valuation_methods=fv.methods_used,
        recommendation=rec.recommendation,
        confidence=rec.confidence,
        rationale=rec.rationale,
        description=desc,
        revenue_model=revenue_model,
        investment_thesis=research.investment_thesis,
        sector_overview=research.sector_overview,
        key_risks=research.key_risks,
        key_catalysts=research.key_catalysts,
        metrics_table=metrics_table,
        peer_count=processed.sector_stats.peer_count if processed.sector_stats else 0,
        data_completeness_pct=int(rec.data_completeness * 100),
        caveats=caveats,
    )
