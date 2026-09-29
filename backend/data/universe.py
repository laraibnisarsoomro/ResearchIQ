"""S&P 500 universe management — fetch, store, and query constituent data."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.db.models import UniverseEntry

logger = logging.getLogger(__name__)

# Wikipedia table URL for S&P 500 list
_SP500_WIKI = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"

# Sector name normalization (yfinance sometimes uses non-standard names)
_SECTOR_NORMALIZATION = {
    "Consumer Cyclical": "Consumer Discretionary",
    "Consumer Non-Cyclical": "Consumer Staples",
    "Industrial Cyclical": "Industrials",
}

# Fallback: hard-coded sector assignments for the most common tickers
# Used if Wikipedia fetch fails
_FALLBACK_SECTORS: dict[str, tuple[str, str]] = {
    "AAPL": ("Information Technology", "Technology Hardware, Storage & Peripherals"),
    "MSFT": ("Information Technology", "Systems Software"),
    "GOOGL": ("Communication Services", "Interactive Media & Services"),
    "GOOG": ("Communication Services", "Interactive Media & Services"),
    "AMZN": ("Consumer Discretionary", "Broadline Retail"),
    "NVDA": ("Information Technology", "Semiconductors"),
    "META": ("Communication Services", "Interactive Media & Services"),
    "TSLA": ("Consumer Discretionary", "Automobile Manufacturers"),
    "BRK-B": ("Financials", "Multi-Sector Holdings"),
    "JPM": ("Financials", "Diversified Banks"),
    "JNJ": ("Health Care", "Pharmaceuticals"),
    "V": ("Financials", "Transaction & Payment Processing Services"),
    "UNH": ("Health Care", "Managed Health Care"),
    "XOM": ("Energy", "Integrated Oil & Gas"),
    "WMT": ("Consumer Staples", "Consumer Staples Merchandise Retail"),
    "MA": ("Financials", "Transaction & Payment Processing Services"),
    "PG": ("Consumer Staples", "Personal Care Products"),
    "HD": ("Consumer Discretionary", "Home Improvement Retail"),
    "CVX": ("Energy", "Integrated Oil & Gas"),
    "MRK": ("Health Care", "Pharmaceuticals"),
    "LLY": ("Health Care", "Pharmaceuticals"),
    "ABBV": ("Health Care", "Biotechnology"),
    "PFE": ("Health Care", "Pharmaceuticals"),
    "KO": ("Consumer Staples", "Soft Drinks & Non-alcoholic Beverages"),
    "PEP": ("Consumer Staples", "Soft Drinks & Non-alcoholic Beverages"),
    "AVGO": ("Information Technology", "Semiconductors"),
    "COST": ("Consumer Staples", "Consumer Staples Merchandise Retail"),
    "TMO": ("Health Care", "Life Sciences Tools & Services"),
    "MCD": ("Consumer Discretionary", "Restaurants"),
    "ACN": ("Information Technology", "IT Consulting & Other Services"),
    "ABT": ("Health Care", "Health Care Equipment"),
    "CSCO": ("Information Technology", "Communications Equipment"),
    "DHR": ("Health Care", "Health Care Equipment"),
    "ADBE": ("Information Technology", "Application Software"),
    "NFLX": ("Communication Services", "Movies & Entertainment"),
    "CRM": ("Information Technology", "Application Software"),
    "TXN": ("Information Technology", "Semiconductors"),
    "NEE": ("Utilities", "Electric Utilities"),
    "WFC": ("Financials", "Diversified Banks"),
    "BAC": ("Financials", "Diversified Banks"),
    "GS": ("Financials", "Investment Banking & Brokerage"),
    "MS": ("Financials", "Investment Banking & Brokerage"),
    "CAT": ("Industrials", "Construction Machinery & Heavy Transportation Equipment"),
    "GE": ("Industrials", "Industrial Conglomerates"),
    "HON": ("Industrials", "Industrial Conglomerates"),
    "UPS": ("Industrials", "Air Freight & Logistics"),
    "BA": ("Industrials", "Aerospace & Defense"),
    "RTX": ("Industrials", "Aerospace & Defense"),
    "LMT": ("Industrials", "Aerospace & Defense"),
    "DE": ("Industrials", "Agricultural & Farm Machinery"),
    "SLB": ("Energy", "Oil & Gas Equipment & Services"),
    "COP": ("Energy", "Oil & Gas Exploration & Production"),
    "OXY": ("Energy", "Oil & Gas Exploration & Production"),
    "ECL": ("Materials", "Specialty Chemicals"),
    "APD": ("Materials", "Industrial Gases"),
    "DD": ("Materials", "Specialty Chemicals"),
    "NEM": ("Materials", "Gold"),
    "FCX": ("Materials", "Copper"),
    "AMT": ("Real Estate", "Telecom Tower REITs"),
    "PLD": ("Real Estate", "Industrial REITs"),
    "SPG": ("Real Estate", "Retail REITs"),
    "DUK": ("Utilities", "Electric Utilities"),
    "SO": ("Utilities", "Electric Utilities"),
    "AEP": ("Utilities", "Electric Utilities"),
    "D": ("Utilities", "Multi-Utilities"),
}


async def get_universe(db: AsyncSession) -> dict[str, dict]:
    """Return {ticker: {name, sector, sub_industry}} from DB."""
    result = await db.execute(select(UniverseEntry))
    rows = result.scalars().all()
    return {
        r.ticker: {"name": r.name, "sector": r.sector, "sub_industry": r.sub_industry}
        for r in rows
    }


async def universe_needs_refresh(db: AsyncSession, max_age_days: int = 7) -> bool:
    result = await db.execute(
        select(UniverseEntry.fetched_at).order_by(UniverseEntry.fetched_at.desc()).limit(1)
    )
    raw = result.scalar_one_or_none()
    if raw is None:
        return True
    if isinstance(raw, str):
        try:
            raw = datetime.fromisoformat(raw)
        except ValueError:
            return True
    return datetime.utcnow() - raw > timedelta(days=max_age_days)


async def _bulk_upsert_universe(
    db: AsyncSession, rows: list[tuple[str, str, str, str]]
) -> int:
    """
    Upsert a list of (ticker, name, sector, sub_industry) rows in one commit.
    Uses a single bulk SELECT to avoid N+1 queries.
    """
    tickers = [r[0] for r in rows]
    existing_result = await db.execute(
        select(UniverseEntry).where(UniverseEntry.ticker.in_(tickers))
    )
    entry_map: dict[str, UniverseEntry] = {e.ticker: e for e in existing_result.scalars()}
    now = datetime.utcnow()
    for ticker, name, sector, sub_industry in rows:
        entry = entry_map.get(ticker)
        if entry is None:
            entry = UniverseEntry(ticker=ticker)
            db.add(entry)
        entry.name = name
        entry.sector = sector
        entry.sub_industry = sub_industry
        entry.fetched_at = now
    await db.commit()
    return len(rows)


async def refresh_universe(db: AsyncSession) -> int:
    """Download S&P 500 list from Wikipedia and store in DB. Returns count."""
    try:
        import io
        import requests
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        }
        resp = requests.get(_SP500_WIKI, headers=headers, timeout=15)
        resp.raise_for_status()
        tables = pd.read_html(io.StringIO(resp.text), header=0)
        df = tables[0]
        col_map = {
            "Symbol": "ticker",
            "Security": "name",
            "GICS Sector": "sector",
            "GICS Sub-Industry": "sub_industry",
        }
        df = df.rename(columns={c: col_map[c] for c in col_map if c in df.columns})
        if "ticker" not in df.columns and "Ticker symbol" in df.columns:
            df = df.rename(columns={"Ticker symbol": "ticker"})
        df["ticker"] = df["ticker"].str.replace(".", "-", regex=False)
        rows = []
        for _, row in df.iterrows():
            ticker = str(row.get("ticker", "")).strip()
            if ticker:
                rows.append((
                    ticker,
                    str(row.get("name", ticker)),
                    str(row.get("sector", "Unknown")),
                    str(row.get("sub_industry", "")),
                ))
        count = await _bulk_upsert_universe(db, rows)
        logger.info("Universe refreshed: %d tickers", count)
        return count
    except Exception as exc:
        logger.warning("Wikipedia fetch failed (%s); loading fallback sectors", exc)
        rows = [
            (ticker, ticker, sector, sub_industry)
            for ticker, (sector, sub_industry) in _FALLBACK_SECTORS.items()
        ]
        return await _bulk_upsert_universe(db, rows)


async def get_sector_peers(db: AsyncSession, sector: str, exclude_ticker: str = "") -> list[str]:
    """Return list of tickers in the same sector."""
    result = await db.execute(
        select(UniverseEntry.ticker).where(UniverseEntry.sector == sector)
    )
    tickers = [row[0] for row in result.fetchall() if row[0] != exclude_ticker]
    return tickers


async def resolve_ticker_sector(
    db: AsyncSession, ticker: str
) -> tuple[str, str, str]:
    """Return (name, sector, sub_industry) for ticker, or ("", "Unknown", "")."""
    entry = await db.get(UniverseEntry, ticker)
    if entry:
        return entry.name, entry.sector, entry.sub_industry
    # Check fallback
    if ticker in _FALLBACK_SECTORS:
        sector, sub_industry = _FALLBACK_SECTORS[ticker]
        return ticker, sector, sub_industry
    return "", "Unknown", ""


def normalize_sector(sector: str) -> str:
    """Convert non-standard sector names to S&P 500 GICS sector names."""
    return _SECTOR_NORMALIZATION.get(sector, sector)
