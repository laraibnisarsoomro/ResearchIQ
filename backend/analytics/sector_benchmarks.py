"""Sector peer benchmarking — compute and cache mean/median ratios."""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Optional

import numpy as np
import pandas as pd
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.db.models import CompanyRatiosCache, SectorStatsCache
from backend.models.schemas import ComputedRatios, SectorStats

logger = logging.getLogger(__name__)

# Ratio fields that should be positive-only (negative values are excluded
# from mean/median but are included in D/E and net_debt_ebitda with care)
_POSITIVE_ONLY = {"pe", "pb", "ps", "pfcf", "ev_ebitda", "ev_sales"}
_WINSORIZE_QUANTILE = 0.05  # trim top/bottom 5%


def _winsorize(arr: np.ndarray, q: float = _WINSORIZE_QUANTILE) -> np.ndarray:
    if len(arr) < 4:
        return arr
    lo, hi = np.nanquantile(arr, q), np.nanquantile(arr, 1 - q)
    return np.clip(arr, lo, hi)


def _ratios_to_dict(r: ComputedRatios) -> dict:
    return r.model_dump()


def _dict_to_ratios(d: dict) -> ComputedRatios:
    return ComputedRatios(**{k: d.get(k) for k in ComputedRatios.model_fields})


def _compute_stats(values: list[Optional[float]], field: str) -> tuple[Optional[float], Optional[float]]:
    """Return (mean, median) with winsorization and outlier removal."""
    arr = np.array([v for v in values if v is not None and np.isfinite(v)], dtype=float)
    if field in _POSITIVE_ONLY:
        arr = arr[arr > 0]
    if len(arr) == 0:
        return None, None
    arr = _winsorize(arr)
    return float(np.nanmean(arr)), float(np.nanmedian(arr))


async def get_sector_stats(
    db: AsyncSession, sector: str, force_refresh: bool = False
) -> Optional[SectorStats]:
    """Return cached sector stats, computing from stored ratios if needed."""
    if not force_refresh:
        cached = await db.get(SectorStatsCache, sector)
        if cached:
            age = datetime.utcnow() - cached.computed_at
            if age < timedelta(seconds=settings.sector_stats_ttl):
                data = json.loads(cached.stats_json)
                return SectorStats(
                    sector=sector,
                    peer_count=cached.peer_count,
                    mean=_dict_to_ratios(data["mean"]),
                    median=_dict_to_ratios(data["median"]),
                )

    return await _compute_and_cache_sector_stats(db, sector)


async def _compute_and_cache_sector_stats(
    db: AsyncSession, sector: str
) -> Optional[SectorStats]:
    """Query all cached company ratios for the sector and compute stats."""
    from sqlalchemy import select

    result = await db.execute(
        select(CompanyRatiosCache).where(CompanyRatiosCache.sector == sector)
    )
    rows = result.scalars().all()
    if not rows:
        return None

    fields = list(ComputedRatios.model_fields.keys())
    bucket: dict[str, list[Optional[float]]] = {f: [] for f in fields}

    for row in rows:
        try:
            ratios_dict = json.loads(row.ratios_json)
        except Exception:
            continue
        for f in fields:
            bucket[f].append(ratios_dict.get(f))

    means: dict = {}
    medians: dict = {}
    for f in fields:
        m, md = _compute_stats(bucket[f], f)
        means[f] = m
        medians[f] = md

    peer_count = len(rows)
    stats = SectorStats(
        sector=sector,
        peer_count=peer_count,
        mean=ComputedRatios(**means),
        median=ComputedRatios(**medians),
    )

    # Persist
    entry = await db.get(SectorStatsCache, sector)
    if entry is None:
        entry = SectorStatsCache(sector=sector)
        db.add(entry)
    entry.stats_json = json.dumps({"mean": means, "median": medians})
    entry.peer_count = peer_count
    entry.computed_at = datetime.utcnow()
    await db.commit()

    return stats


async def upsert_company_ratios(
    db: AsyncSession,
    ticker: str,
    sector: str,
    ratios: ComputedRatios,
    market_cap: float = 0.0,
    upside_pct: Optional[float] = None,
    beta: Optional[float] = None,
):
    """Store or update a company's ratios in the sector benchmarks pool.

    upside_pct and beta are stored as extra keys in ratios_json so the
    portfolio builder can retrieve them without a separate fetch.
    """
    entry = await db.get(CompanyRatiosCache, ticker)
    if entry is None:
        entry = CompanyRatiosCache(ticker=ticker)
        db.add(entry)
    entry.sector = sector

    d = _ratios_to_dict(ratios)
    if upside_pct is not None:
        # Cap at ±75% — values beyond this almost certainly reflect comparable
        # distortion (e.g., a media stock benchmarked against FAANG multiples),
        # not genuine return potential for a large-cap equity.
        d["upside_pct"] = max(min(float(upside_pct), 75.0), -75.0)
    if beta is not None:
        d["beta"] = beta

    entry.ratios_json = json.dumps(d)
    entry.computed_at = datetime.utcnow()
    entry.market_cap = market_cap or 0.0
    await db.commit()


async def ensure_sector_has_peers(
    db: AsyncSession,
    sector: str,
    target_ticker: str,
    peer_tickers: list[str],
    min_peers: int = 5,
) -> int:
    """
    If the sector has fewer than min_peers cached, download a batch of peers.
    Returns the number of peers successfully processed.
    """
    from sqlalchemy import select, func

    result = await db.execute(
        select(func.count()).select_from(CompanyRatiosCache).where(
            CompanyRatiosCache.sector == sector
        )
    )
    existing = result.scalar_one()
    if existing >= min_peers:
        return existing

    # Fetch a representative batch (up to max_sector_peers)
    batch = [t for t in peer_tickers if t != target_ticker][: settings.max_sector_peers]
    if not batch:
        return existing

    logger.info("Bootstrapping %d sector peers for %s", len(batch), sector)
    count = 0
    for ticker in batch:
        try:
            await _fetch_and_store_peer(db, ticker, sector)
            count += 1
        except Exception as exc:
            logger.debug("Peer fetch failed for %s: %s", ticker, exc)
        # Yield control so we don't block the event loop
        await asyncio.sleep(0)

    return existing + count


async def _fetch_and_store_peer(db: AsyncSession, ticker: str, sector: str):
    """Download minimal data for a peer and store its ratios."""
    from backend.data.yfinance_client import get_info, get_financials
    from backend.analytics.ttm_calculator import compute_ttm
    from backend.analytics.ratio_calculator import compute_ratios

    info = await get_info(db, ticker)
    if not info:
        return
    income, balance, cashflow = await get_financials(db, ticker)
    metrics = compute_ttm(info, income, balance, cashflow)
    ratios = compute_ratios(metrics, info)
    mktcap = metrics.market_cap or 0.0
    await upsert_company_ratios(db, ticker, sector, ratios, mktcap)
