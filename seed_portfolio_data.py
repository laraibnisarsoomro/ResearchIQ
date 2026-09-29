"""Seed portfolio upside_pct and beta into CompanyRatiosCache.

Run once after startup to give the portfolio builder meaningful candidates:
    python seed_portfolio_data.py

Strategy:
  - For every ticker already in company_ratios_cache, fetch yfinance info
    (targetMeanPrice, currentPrice, beta) to compute analyst-consensus upside_pct
  - Update ratios_json in-place (preserves existing ratio data)
  - Also seeds the UniverseEntry name if missing
  - Skips tickers where targetMeanPrice is unavailable
"""
from __future__ import annotations

import asyncio
import json
import logging
import sys
from datetime import datetime

import yfinance as yf
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
)
logger = logging.getLogger(__name__)

DB_URL = "sqlite+aiosqlite:///data/equity_research.db"

_SECTOR_MAP = {
    "Technology": "Information Technology",
    "Financial Services": "Financials",
    "Healthcare": "Health Care",
    "Consumer Cyclical": "Consumer Discretionary",
    "Consumer Defensive": "Consumer Staples",
    "Communication Services": "Communication Services",
    "Industrials": "Industrials",
    "Basic Materials": "Materials",
    "Energy": "Energy",
    "Real Estate": "Real Estate",
    "Utilities": "Utilities",
}

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


def _fetch_ticker_data(ticker: str) -> dict | None:
    try:
        info = yf.Ticker(ticker).info
        target = info.get("targetMeanPrice") or info.get("targetMedianPrice")
        current = (
            info.get("currentPrice")
            or info.get("regularMarketPrice")
            or info.get("previousClose")
        )
        if not target or not current or current <= 0:
            return None

        upside_pct = round((target - current) / current * 100, 2)
        beta = info.get("beta")
        yf_sector = info.get("sector", "")
        gics_sector = _SECTOR_MAP.get(yf_sector, yf_sector)
        name = info.get("longName") or info.get("shortName") or ticker

        return {
            "upside_pct": upside_pct,
            "beta": beta,
            "gics_sector": gics_sector,
            "name": name,
        }
    except Exception as exc:
        logger.debug("yfinance failed for %s: %s", ticker, exc)
        return None


async def seed(batch_size: int = 10, delay: float = 0.5):
    engine = create_async_engine(DB_URL, echo=False)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    from backend.db.models import CompanyRatiosCache, UniverseEntry  # noqa: PLC0415

    async with Session() as db:
        result = await db.execute(select(CompanyRatiosCache))
        rows = result.scalars().all()

    tickers = [r.ticker for r in rows]
    logger.info("Seeding %d tickers from company_ratios_cache…", len(tickers))

    updated = 0
    skipped = 0

    for i in range(0, len(tickers), batch_size):
        batch = tickers[i : i + batch_size]
        loop = asyncio.get_event_loop()
        results = await asyncio.gather(
            *[loop.run_in_executor(None, _fetch_ticker_data, t) for t in batch],
            return_exceptions=False,
        )

        async with Session() as db:
            for ticker, data in zip(batch, results):
                if data is None:
                    skipped += 1
                    continue

                row = await db.get(CompanyRatiosCache, ticker)
                if row is None:
                    skipped += 1
                    continue

                try:
                    ratios = json.loads(row.ratios_json)
                except Exception:
                    ratios = {}

                ratios["upside_pct"] = data["upside_pct"]
                if data["beta"] and 0.0 < data["beta"] < 5.0:
                    ratios["beta"] = data["beta"]
                else:
                    gics = data["gics_sector"] or row.sector
                    ratios["beta"] = _SECTOR_BETAS.get(gics, 1.0)

                row.ratios_json = json.dumps(ratios)
                row.computed_at = datetime.utcnow()

                # Also update sector if we have a better GICS match
                if data["gics_sector"]:
                    row.sector = data["gics_sector"]

                updated += 1

            await db.commit()

        pct_done = min(100, round((i + len(batch)) / len(tickers) * 100))
        logger.info(
            "[%3d%%] batch %d-%d: %d updated, %d skipped so far",
            pct_done,
            i + 1,
            i + len(batch),
            updated,
            skipped,
        )
        if i + batch_size < len(tickers):
            await asyncio.sleep(delay)

    logger.info("Done. %d updated, %d skipped (no analyst target).", updated, skipped)
    await engine.dispose()


if __name__ == "__main__":
    import sys
    sys.path.insert(0, ".")
    asyncio.run(seed())
