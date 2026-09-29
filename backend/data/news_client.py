"""News retrieval and formatting for research context."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


def format_news_for_llm(news_items: list[dict], max_items: int = 10) -> str:
    """Convert yfinance news list to a readable text block for LLM context."""
    if not news_items:
        return "No recent news available."
    lines = []
    for item in news_items[:max_items]:
        title = item.get("title", "").strip()
        publisher = item.get("publisher", "")
        ts = item.get("providerPublishTime", 0)
        date_str = ""
        if ts:
            try:
                date_str = datetime.utcfromtimestamp(ts).strftime("%b %d, %Y")
            except Exception:
                date_str = ""
        if title:
            lines.append(f"- [{date_str}] {title} ({publisher})")
    return "\n".join(lines) if lines else "No recent news available."


def extract_news_titles(news_items: list[dict], max_items: int = 10) -> list[str]:
    """Return a plain list of news headline strings."""
    titles = []
    for item in news_items[:max_items]:
        title = item.get("title", "").strip()
        if title:
            titles.append(title)
    return titles
