"""Transparent rule-based Buy/Hold/Sell recommendation engine."""
from __future__ import annotations

import logging
from typing import Optional

from backend.models.schemas import (
    ComputedRatios,
    FairValueResult,
    RecommendationResult,
    SectorStats,
)

logger = logging.getLogger(__name__)


def _cmp(company: Optional[float], sector_median: Optional[float]) -> Optional[int]:
    """Return +1 if company > sector, -1 if below, 0 if in-line, None if unknown."""
    if company is None or sector_median is None:
        return None
    ratio = company / sector_median if sector_median != 0 else None
    if ratio is None:
        return None
    if ratio > 1.10:
        return 1
    if ratio < 0.90:
        return -1
    return 0


def compute_quality_score(
    company_ratios: ComputedRatios,
    sector_stats: Optional[SectorStats],
) -> float:
    """Score 0.0–1.0 based on how many quality dimensions beat sector median."""
    if sector_stats is None:
        return 0.5  # neutral if no benchmark

    sm = sector_stats.median
    score = 0.0
    total = 0.0

    def _add(company_val, sector_val, higher_is_better: bool = True):
        nonlocal score, total
        c = _cmp(company_val, sector_val)
        if c is None:
            return
        total += 1.0
        if higher_is_better and c >= 0:
            score += 1.0
        elif not higher_is_better and c <= 0:
            score += 1.0

    # Profitability (higher is better)
    _add(company_ratios.roe, sm.roe, True)
    _add(company_ratios.net_margin, sm.net_margin, True)
    _add(company_ratios.operating_margin, sm.operating_margin, True)
    _add(company_ratios.fcf_margin, sm.fcf_margin, True)
    _add(company_ratios.roa, sm.roa, True)
    # Leverage (lower is better)
    _add(company_ratios.de, sm.de, False)
    # Growth (higher is better)
    _add(company_ratios.revenue_growth, sm.revenue_growth, True)
    _add(company_ratios.eps_growth, sm.eps_growth, True)

    if total == 0:
        return 0.5
    return round(score / total, 3)


def compute_data_completeness(company_ratios: ComputedRatios) -> float:
    """Fraction of ratio fields that are non-None."""
    fields = company_ratios.model_dump()
    total = len(fields)
    filled = sum(1 for v in fields.values() if v is not None)
    return round(filled / total, 3) if total else 0.0


def make_recommendation(
    fv: FairValueResult,
    quality_score: float,
    data_completeness: float,
    company_ratios: ComputedRatios,
    sector_stats: Optional[SectorStats],
) -> RecommendationResult:
    upside = fv.upside_pct

    # ── Confidence ────────────────────────────────────────────────────────────
    n_methods = len(fv.methods_used)
    if n_methods >= 3 and data_completeness >= 0.50:
        confidence = "High"
    elif n_methods >= 2 and data_completeness >= 0.30:
        confidence = "Medium"
    else:
        confidence = "Low"

    if upside is None:
        return RecommendationResult(
            recommendation="Hold",
            confidence="Low",
            rationale="Insufficient data to estimate fair value. Defaulting to Hold.",
            quality_score=quality_score,
            data_completeness=data_completeness,
        )

    # ── Red flags ─────────────────────────────────────────────────────────────
    red_flags: list[str] = []
    sm = sector_stats.median if sector_stats else None
    if sm:
        if company_ratios.de is not None and sm.de is not None and company_ratios.de > sm.de * 2.0:
            red_flags.append("elevated leverage")
        if company_ratios.net_margin is not None and sm.net_margin is not None:
            if company_ratios.net_margin < 0 and sm.net_margin > 0:
                red_flags.append("negative net margin vs. profitable sector")
        if company_ratios.revenue_growth is not None and company_ratios.revenue_growth < -0.10:
            red_flags.append("declining revenue")

    has_red_flags = len(red_flags) > 0

    # ── Decision logic ────────────────────────────────────────────────────────
    # Upside is the primary signal; quality_score affects confidence/rationale, not the call.
    if upside > 15 and not has_red_flags:
        rec = "Buy"
        if upside > 50:
            rationale = (
                f"Substantial upside of {upside:.1f}% to sector-comparable fair value suggests "
                f"significant undervaluation relative to peer multiples. "
                f"Quality score {quality_score:.2f} vs. sector peers."
            )
            if quality_score < 0.40:
                rationale += (
                    " Quality metrics trail sector median — consider sizing conservatively "
                    "until fundamentals confirm the valuation gap."
                )
        elif upside > 30:
            rationale = (
                f"Significant upside of {upside:.1f}% to sector-comparable fair value with "
                f"quality score {quality_score:.2f}. Valuation multiples suggest meaningful "
                "undervaluation relative to fundamentals."
            )
        else:
            rationale = (
                f"Attractive upside of {upside:.1f}% to sector-comparable fair value. "
                f"Stock trades at a discount vs. sector peers on comparable metrics "
                f"(quality score: {quality_score:.2f})."
            )
        # Downgrade confidence when quality is below average
        if quality_score < 0.40 and confidence == "High":
            confidence = "Medium"
    elif upside > 15 and has_red_flags:
        rec = "Hold"
        rationale = (
            f"Potential upside of {upside:.1f}% is offset by: {', '.join(red_flags)}. "
            "Recommend waiting for improvement in these metrics before initiating a position."
        )
    elif upside < -15:
        rec = "Sell"
        rationale = (
            f"Stock appears {abs(upside):.1f}% overvalued vs. sector-median comparable fair value. "
            "Valuation multiples are elevated relative to fundamentals and peer group."
        )
        if has_red_flags:
            rationale += f" Concerns amplified by: {', '.join(red_flags)}."
    elif -15 <= upside <= 5:
        rec = "Hold"
        rationale = (
            f"Valuation appears broadly in-line with sector peers (upside: {upside:+.1f}%). "
            "Stock fairly valued based on comparable multiple analysis."
        )
        if quality_score >= 0.60:
            rationale += " Quality metrics are above-average, supporting current valuation."
    elif 5 < upside <= 15:
        rec = "Hold"
        rationale = (
            f"Modest upside of {upside:.1f}% relative to sector-median fair value. "
            "Limited margin of safety from current price."
        )
        if quality_score >= 0.50:
            rec = "Buy"
            rationale += f" Above-average quality profile (score: {quality_score:.2f}) supports a Buy at these levels."
    else:
        rec = "Hold"
        rationale = (
            f"Upside of {upside:+.1f}% relative to sector peers does not clearly warrant "
            "a directional call at this time."
        )

    # Downgrade confidence if there are red flags or very low data completeness
    if has_red_flags and confidence == "High":
        confidence = "Medium"
    if data_completeness < 0.25:
        confidence = "Low"

    return RecommendationResult(
        recommendation=rec,
        confidence=confidence,
        rationale=rationale,
        quality_score=quality_score,
        data_completeness=data_completeness,
    )
