"""Agent 1 — Validate ticker and resolve company profile."""
from __future__ import annotations

import asyncio
import logging
from functools import partial

import yfinance as yf
from sqlalchemy.ext.asyncio import AsyncSession

from backend.data.universe import refresh_universe, resolve_ticker_sector, universe_needs_refresh
from backend.models.schemas import CompanyProfile

logger = logging.getLogger(__name__)

_INVALID_EXCHANGE_KEYWORDS = ["OTC", "Pink", "Grey"]


def _validate_sync(ticker: str) -> dict:
    """Quick synchronous validation via yfinance fast_info."""
    try:
        t = yf.Ticker(ticker)
        info = t.fast_info
        price = getattr(info, "last_price", None)
        exchange = getattr(info, "exchange", "") or ""
        quote_type = t.info.get("quoteType", "") if hasattr(t, "info") else ""
        return {
            "valid": price is not None and price > 0,
            "price": price,
            "exchange": exchange,
            "quote_type": quote_type,
            "name": t.info.get("longName") or t.info.get("shortName") or ticker if hasattr(t, "info") else ticker,
        }
    except Exception as exc:
        logger.debug("Validation failed for %s: %s", ticker, exc)
        return {"valid": False, "price": None, "exchange": "", "quote_type": "", "name": ticker}


async def resolve_ticker(db: AsyncSession, ticker: str) -> CompanyProfile:
    """
    Validate ticker and return a CompanyProfile.
    Raises ValueError for invalid / unrecognised tickers.
    """
    ticker = ticker.upper().strip().replace(" ", "").replace(".", "-")
    if not ticker or len(ticker) > 10:
        raise ValueError(f"Invalid ticker symbol: '{ticker}'")

    # Ensure universe is loaded
    needs_refresh = await universe_needs_refresh(db, max_age_days=7)
    if needs_refresh:
        await refresh_universe(db)

    # Quick yfinance validation (runs in thread pool to not block event loop)
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, _validate_sync, ticker)

    if not result["valid"]:
        raise ValueError(
            f"Could not retrieve market data for '{ticker}'. "
            "Please verify the ticker symbol is correct and traded on a major US exchange."
        )

    # Resolve sector from universe DB or fallback
    uni_name, sector, sub_industry = await resolve_ticker_sector(db, ticker)
    name = uni_name or result.get("name") or ticker
    exchange = result.get("exchange", "")

    # If sector is still Unknown, try to get it from yfinance info
    if sector == "Unknown":
        from backend.data.yfinance_client import get_info
        from backend.data.universe import normalize_sector
        info = await get_info(db, ticker)
        sector = info.get("sector") or "Unknown"
        sector = normalize_sector(sector)  # Normalize to standard GICS sector names
        sub_industry = info.get("industry") or ""
        name = info.get("longName") or info.get("shortName") or name

    description = ""
    revenue_model = ""

    return CompanyProfile(
        ticker=ticker,
        name=name,
        sector=sector,
        industry=sub_industry,
        exchange=exchange,
        description=description,
        revenue_model=revenue_model,
    )
