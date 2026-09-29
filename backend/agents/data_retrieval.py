"""Agent 2 — Fetch and cache company data."""
from __future__ import annotations

import logging
from typing import Optional

import pandas as pd
from sqlalchemy.ext.asyncio import AsyncSession

from backend.data.yfinance_client import get_financials, get_info, get_news

logger = logging.getLogger(__name__)


class CompanyData:
    def __init__(
        self,
        ticker: str,
        info: dict,
        income: Optional[pd.DataFrame],
        balance: Optional[pd.DataFrame],
        cashflow: Optional[pd.DataFrame],
        news: list[dict],
    ):
        self.ticker = ticker
        self.info = info
        self.income = income
        self.balance = balance
        self.cashflow = cashflow
        self.news = news

    @property
    def has_financials(self) -> bool:
        return self.income is not None or self.balance is not None

    @property
    def long_description(self) -> str:
        return self.info.get("longBusinessSummary", "") or ""


async def retrieve_company_data(db: AsyncSession, ticker: str) -> CompanyData:
    """Fetch all data needed for a single company report."""
    info, (income, balance, cashflow), news = await _gather(db, ticker)
    return CompanyData(
        ticker=ticker,
        info=info,
        income=income,
        balance=balance,
        cashflow=cashflow,
        news=news,
    )


async def _gather(db: AsyncSession, ticker: str):
    import asyncio
    info_task = asyncio.create_task(get_info(db, ticker))
    fin_task = asyncio.create_task(get_financials(db, ticker))
    news_task = asyncio.create_task(get_news(db, ticker))
    info = await info_task
    fin = await fin_task
    news = await news_task
    return info, fin, news
