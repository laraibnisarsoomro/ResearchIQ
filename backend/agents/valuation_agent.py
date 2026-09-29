"""Agent 4 — Fair value estimation and preliminary recommendation."""
from __future__ import annotations

import logging
from typing import Optional

from backend.agents.financial_processor import ProcessedFinancials
from backend.analytics.fair_value import compute_fair_value
from backend.analytics.recommendation import (
    compute_data_completeness,
    compute_quality_score,
    make_recommendation,
)
from backend.models.schemas import FairValueResult, RecommendationResult

logger = logging.getLogger(__name__)


class ValuationOutput:
    def __init__(
        self,
        fair_value: FairValueResult,
        recommendation: RecommendationResult,
    ):
        self.fair_value = fair_value
        self.recommendation = recommendation


def run_valuation(
    processed: ProcessedFinancials,
    sector: str,
    current_price: float,
) -> ValuationOutput:
    fv = compute_fair_value(
        sector=sector,
        metrics=processed.metrics,
        company_ratios=processed.ratios,
        sector_stats=processed.sector_stats,
        current_price=current_price,
    )
    quality_score = compute_quality_score(processed.ratios, processed.sector_stats)
    data_completeness = compute_data_completeness(processed.ratios)
    rec = make_recommendation(
        fv=fv,
        quality_score=quality_score,
        data_completeness=data_completeness,
        company_ratios=processed.ratios,
        sector_stats=processed.sector_stats,
    )
    return ValuationOutput(fair_value=fv, recommendation=rec)
