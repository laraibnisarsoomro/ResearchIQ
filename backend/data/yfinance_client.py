"""yfinance wrapper with SQLite-backed caching and robust field handling."""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta
from functools import partial
from typing import Any, Optional

import pandas as pd
import yfinance as yf
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.db.models import CompanyCache

logger = logging.getLogger(__name__)

# ── Field name aliases (yfinance changes names between versions) ──────────────
INCOME_ALIASES: dict[str, list[str]] = {
    "revenue": ["Total Revenue", "Revenue", "TotalRevenue"],
    "gross_profit": ["Gross Profit", "GrossProfit"],
    "operating_income": ["Operating Income", "OperatingIncome", "EBIT"],
    "net_income": [
        "Net Income",
        "NetIncome",
        "Net Income Common Stockholders",
        "Net Income Including Noncontrolling Interests",
    ],
    "ebitda": ["EBITDA", "Ebitda", "Normalized EBITDA"],
    "eps_basic": ["Basic EPS", "BasicEPS", "Diluted EPS", "DilutedEPS"],
    "interest_expense": ["Interest Expense", "InterestExpense"],
    "tax_provision": ["Tax Provision", "TaxProvision", "Income Tax Expense"],
}

BALANCE_ALIASES: dict[str, list[str]] = {
    "total_assets": ["Total Assets", "TotalAssets"],
    "total_debt": [
        "Total Debt",
        "TotalDebt",
        "Long Term Debt And Capital Lease Obligation",
        "Long Term Debt",
    ],
    "short_term_debt": [
        "Current Debt",
        "CurrentDebt",
        "Short Long Term Debt",
        "Current Debt And Capital Lease Obligation",
    ],
    "cash": [
        "Cash And Cash Equivalents",
        "CashAndCashEquivalents",
        "Cash Cash Equivalents And Short Term Investments",
        "Cash Cash Equivalents And Federal Funds Sold",
    ],
    "equity": [
        "Total Stockholder Equity",
        "StockholdersEquity",
        "Stockholders Equity",
        "Common Stock Equity",
        "Total Equity Gross Minority Interest",
    ],
    "current_assets": ["Total Current Assets", "CurrentAssets", "Current Assets"],
    "current_liabilities": [
        "Total Current Liabilities",
        "CurrentLiabilities",
        "Current Liabilities",
    ],
    "shares_outstanding": [
        "Share Issued",
        "Ordinary Shares Number",
        "Common Stock Shares Outstanding",
    ],
}

CASHFLOW_ALIASES: dict[str, list[str]] = {
    "operating_cf": [
        "Total Cash From Operating Activities",
        "OperatingCashFlow",
        "Operating Cash Flow",
        "Cash Flow From Continuing Operating Activities",
    ],
    "capex": [
        "Capital Expenditures",
        "CapitalExpenditures",
        "Purchase Of Property Plant And Equipment",
        "Capital Expenditure",
    ],
    "free_cash_flow": ["Free Cash Flow", "FreeCashFlow"],
}


# ── Serialisation helpers ─────────────────────────────────────────────────────

def _df_to_json(df: Optional[pd.DataFrame]) -> str:
    if df is None or df.empty:
        return "{}"
    try:
        return df.to_json(date_format="iso")
    except Exception:
        return "{}"


def _json_to_df(raw: str) -> Optional[pd.DataFrame]:
    if not raw or raw == "{}":
        return None
    try:
        import io
        df = pd.read_json(io.StringIO(raw))
        # Columns are date strings — convert to Timestamps
        df.columns = pd.to_datetime(df.columns, utc=True)
        return df
    except Exception as exc:
        logger.debug("DataFrame deserialisation failed: %s", exc)
        return None


def _dict_to_json(d: Any) -> str:
    try:
        return json.dumps(d, default=str)
    except Exception:
        return "{}"


# ── Cache helpers ─────────────────────────────────────────────────────────────

async def _get_cache(
    db: AsyncSession, ticker: str, data_type: str, max_age_s: int
) -> Optional[str]:
    cutoff = datetime.utcnow() - timedelta(seconds=max_age_s)
    result = await db.execute(
        select(CompanyCache).where(
            and_(
                CompanyCache.ticker == ticker,
                CompanyCache.data_type == data_type,
                CompanyCache.fetched_at >= cutoff,
            )
        ).order_by(CompanyCache.fetched_at.desc()).limit(1)
    )
    row = result.scalar_one_or_none()
    return row.data_json if row else None


async def _set_cache(
    db: AsyncSession, ticker: str, data_type: str, data_json: str
):
    from sqlalchemy import delete
    await db.execute(
        delete(CompanyCache).where(
            and_(CompanyCache.ticker == ticker, CompanyCache.data_type == data_type)
        )
    )
    db.add(CompanyCache(
        ticker=ticker,
        data_type=data_type,
        data_json=data_json,
        fetched_at=datetime.utcnow(),
    ))
    await db.commit()


# ── Public fetch functions ────────────────────────────────────────────────────

def _fetch_info_sync(ticker: str) -> dict:
    try:
        t = yf.Ticker(ticker)
        info = t.info or {}
        return info
    except Exception as exc:
        logger.warning("yfinance info failed for %s: %s", ticker, exc)
        return {}


def _fetch_financials_sync(ticker: str) -> tuple[str, str, str]:
    """Returns (income_json, balance_json, cashflow_json)."""
    try:
        t = yf.Ticker(ticker)
        income = _df_to_json(t.quarterly_income_stmt)
        balance = _df_to_json(t.quarterly_balance_sheet)
        cashflow = _df_to_json(t.quarterly_cashflow)
        return income, balance, cashflow
    except Exception as exc:
        logger.warning("yfinance financials failed for %s: %s", ticker, exc)
        return "{}", "{}", "{}"


def _fetch_news_sync(ticker: str) -> list[dict]:
    try:
        t = yf.Ticker(ticker)
        news = t.news or []
        cleaned = []
        for item in news[:15]:
            cleaned.append({
                "title": item.get("title", ""),
                "publisher": item.get("publisher", ""),
                "link": item.get("link", ""),
                "providerPublishTime": item.get("providerPublishTime", 0),
            })
        return cleaned
    except Exception as exc:
        logger.warning("yfinance news failed for %s: %s", ticker, exc)
        return []


def _fetch_latest_close_sync(ticker: str) -> Optional[float]:
    """Fetch the most recent closing price (last trading day). No cache."""
    try:
        hist = yf.Ticker(ticker).history(period="5d", auto_adjust=False)
        if hist is None or hist.empty or "Close" not in hist.columns:
            return None
        last = hist["Close"].dropna()
        if last.empty:
            return None
        return float(last.iloc[-1])
    except Exception as exc:
        logger.warning("yfinance latest close failed for %s: %s", ticker, exc)
        return None


async def get_latest_close(ticker: str) -> Optional[float]:
    """Always-fresh latest closing price (bypasses cache)."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _fetch_latest_close_sync, ticker)


def _fetch_price_history_sync(ticker: str, period: str = "1y") -> dict:
    """Fetch 1Y daily price history for ticker and S&P 500; return cumulative returns."""
    try:
        # Fetch ticker and S&P 500 prices
        stock_hist = yf.download(ticker, period=period, progress=False)
        sp500_hist = yf.download("^GSPC", period=period, progress=False)

        if stock_hist.empty or sp500_hist.empty:
            return {}

        # Extract closing prices
        # If multi-indexed columns (from downloading multiple tickers), get the relevant column
        if isinstance(stock_hist.columns, pd.MultiIndex):
            stock_close = stock_hist[("Close", ticker)]
            sp500_close = sp500_hist[("Close", "^GSPC")]
        else:
            stock_close = stock_hist["Close"]
            sp500_close = sp500_hist["Close"]

        # Align dates (some trading days may differ)
        common_dates = stock_close.index.intersection(sp500_close.index)
        if len(common_dates) < 2:
            return {}

        stock_aligned = stock_close[common_dates]
        sp500_aligned = sp500_close[common_dates]

        # Compute cumulative returns normalized to 0% at start
        stock_returns = ((stock_aligned / stock_aligned.iloc[0]) - 1) * 100
        sp500_returns = ((sp500_aligned / sp500_aligned.iloc[0]) - 1) * 100

        # Format output
        dates = [d.strftime("%Y-%m-%d") for d in stock_aligned.index]
        return {
            "dates": dates,
            "stock": [round(r, 2) for r in stock_returns.tolist()],
            "sp500": [round(r, 2) for r in sp500_returns.tolist()],
        }
    except Exception as exc:
        logger.warning("yfinance price history failed for %s: %s", ticker, exc)
        return {}


async def get_info(db: AsyncSession, ticker: str) -> dict:
    cached = await _get_cache(db, ticker, "info", settings.info_cache_ttl)
    if cached:
        return json.loads(cached)
    loop = asyncio.get_event_loop()
    info = await loop.run_in_executor(None, _fetch_info_sync, ticker)
    await _set_cache(db, ticker, "info", _dict_to_json(info))
    return info


async def get_financials(
    db: AsyncSession, ticker: str
) -> tuple[Optional[pd.DataFrame], Optional[pd.DataFrame], Optional[pd.DataFrame]]:
    """Return (income_stmt, balance_sheet, cashflow) quarterly DataFrames."""
    c_income, c_balance, c_cashflow = await asyncio.gather(
        _get_cache(db, ticker, "income", settings.financials_cache_ttl),
        _get_cache(db, ticker, "balance", settings.financials_cache_ttl),
        _get_cache(db, ticker, "cashflow", settings.financials_cache_ttl),
    )

    if c_income and c_balance and c_cashflow:
        return _json_to_df(c_income), _json_to_df(c_balance), _json_to_df(c_cashflow)

    loop = asyncio.get_event_loop()
    raw_income, raw_balance, raw_cashflow = await loop.run_in_executor(
        None, _fetch_financials_sync, ticker
    )
    await _set_cache(db, ticker, "income", raw_income)
    await _set_cache(db, ticker, "balance", raw_balance)
    await _set_cache(db, ticker, "cashflow", raw_cashflow)
    return _json_to_df(raw_income), _json_to_df(raw_balance), _json_to_df(raw_cashflow)


async def get_news(db: AsyncSession, ticker: str) -> list[dict]:
    cached = await _get_cache(db, ticker, "news", settings.news_cache_ttl)
    if cached:
        return json.loads(cached)
    loop = asyncio.get_event_loop()
    news = await loop.run_in_executor(None, _fetch_news_sync, ticker)
    await _set_cache(db, ticker, "news", json.dumps(news))
    return news


async def get_price_history(db: AsyncSession, ticker: str, period: str = "1y") -> Optional[dict]:
    """Fetch and cache price history (stock vs S&P 500 cumulative returns)."""
    cached = await _get_cache(db, ticker, "price_history", settings.price_history_cache_ttl)
    if cached:
        data = json.loads(cached)
        return data if data else None
    loop = asyncio.get_event_loop()
    fetch_fn = partial(_fetch_price_history_sync, ticker, period)
    history = await loop.run_in_executor(None, fetch_fn)
    if history:
        await _set_cache(db, ticker, "price_history", json.dumps(history))
    return history if history else None


# ── Field extraction helpers ──────────────────────────────────────────────────

def extract_field(df: Optional[pd.DataFrame], aliases: list[str]) -> Optional[pd.Series]:
    """Try alias names in order; return the first matched row as a Series."""
    if df is None or df.empty:
        return None
    for alias in aliases:
        if alias in df.index:
            return df.loc[alias]
    return None


def safe_scalar(series: Optional[pd.Series], col_idx: int = 0) -> Optional[float]:
    """Get a single scalar value from a Series by position, safely."""
    if series is None or series.empty:
        return None
    try:
        val = series.iloc[col_idx]
        if pd.isna(val):
            return None
        return float(val)
    except Exception:
        return None


def ttm_sum(series: Optional[pd.Series], n: int = 4) -> Optional[float]:
    """Sum the last n non-null values (quarterly → TTM)."""
    if series is None or series.empty:
        return None
    vals = series.dropna().iloc[:n]
    if vals.empty:
        return None
    return float(vals.sum())


def ttm_mean(series: Optional[pd.Series], n: int = 4) -> Optional[float]:
    """Average the last n non-null values."""
    if series is None or series.empty:
        return None
    vals = series.dropna().iloc[:n]
    if vals.empty:
        return None
    return float(vals.mean())
