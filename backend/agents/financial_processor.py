"""Agent 3 — Compute TTM metrics, ratios, and sector benchmarks."""
from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from backend.agents.data_retrieval import CompanyData
from backend.analytics.ratio_calculator import compute_ratios
from backend.analytics.sector_benchmarks import (
    ensure_sector_has_peers,
    get_sector_stats,
    upsert_company_ratios,
)
from backend.analytics.ttm_calculator import compute_ttm
from backend.data.universe import get_sector_peers
from backend.models.schemas import (
    ComputedRatios,
    FinancialMetrics,
    SectorStats,
)

logger = logging.getLogger(__name__)


class ProcessedFinancials:
    def __init__(
        self,
        metrics: FinancialMetrics,
        ratios: ComputedRatios,
        sector_stats: Optional[SectorStats],
    ):
        self.metrics = metrics
        self.ratios = ratios
        self.sector_stats = sector_stats


async def process_financials(
    db: AsyncSession, data: CompanyData, sector: str
) -> ProcessedFinancials:
    # 1. Compute TTM metrics
    metrics = compute_ttm(data.info, data.income, data.balance, data.cashflow)

    # 2. Compute ratios
    ratios = compute_ratios(metrics, data.info)

    # 3. Store this company's ratios in the benchmark pool
    await upsert_company_ratios(
        db, data.ticker, sector, ratios, metrics.market_cap or 0.0
    )

    # 4. Ensure we have enough sector peers
    peer_tickers = await get_sector_peers(db, sector, exclude_ticker=data.ticker)
    if peer_tickers:
        await ensure_sector_has_peers(db, sector, data.ticker, peer_tickers, min_peers=5)

    # 5. Get sector stats
    sector_stats = await get_sector_stats(db, sector, force_refresh=True)

    return ProcessedFinancials(metrics=metrics, ratios=ratios, sector_stats=sector_stats)
