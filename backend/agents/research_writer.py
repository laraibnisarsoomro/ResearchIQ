"""Agent 5 — Generate qualitative research content (LLM-powered with template fallback)."""
from __future__ import annotations

import logging
import re
from typing import Optional

from backend.agents.data_retrieval import CompanyData
from backend.agents.financial_processor import ProcessedFinancials
from backend.agents.valuation_agent import ValuationOutput
from backend.config import settings
from backend.data.news_client import format_news_for_llm
from backend.models.schemas import CompanyProfile, ResearchContent

logger = logging.getLogger(__name__)


def _fmt_pct(v: Optional[float]) -> str:
    if v is None:
        return "N/M"
    return f"{v*100:.1f}%"


def _fmt_x(v: Optional[float]) -> str:
    if v is None:
        return "N/M"
    return f"{v:.1f}x"


def _fmt_b(v: Optional[float]) -> str:
    if v is None:
        return "N/M"
    if abs(v) >= 1e12:
        return f"${v/1e12:.1f}T"
    if abs(v) >= 1e9:
        return f"${v/1e9:.1f}B"
    if abs(v) >= 1e6:
        return f"${v/1e6:.1f}M"
    return f"${v:.0f}"


async def write_research(
    profile: CompanyProfile,
    data: CompanyData,
    processed: ProcessedFinancials,
    valuation: ValuationOutput,
) -> ResearchContent:
    """Orchestrate research writing, preferring LLM if available."""
    if settings.has_llm:
        try:
            return await _llm_research(profile, data, processed, valuation)
        except Exception:
            logger.exception("LLM research writing failed; using template")
    return _template_research(profile, data, processed, valuation)


# ── LLM-based research ────────────────────────────────────────────────────────

async def _llm_research(
    profile: CompanyProfile,
    data: CompanyData,
    processed: ProcessedFinancials,
    valuation: ValuationOutput,
) -> ResearchContent:
    import anthropic

    m = processed.metrics
    r = processed.ratios
    fv = valuation.fair_value
    rec = valuation.recommendation
    sm = processed.sector_stats.median if processed.sector_stats else None

    # Build structured context block for the LLM
    context = f"""
COMPANY: {profile.name} ({profile.ticker}) | Sector: {profile.sector} | Industry: {profile.industry}
RECOMMENDATION: {rec.recommendation} | Confidence: {rec.confidence}
CURRENT PRICE: ${(m.current_price or 0):.2f}
FAIR VALUE (base): ${(fv.base or 0):.2f} | UPSIDE: {(fv.upside_pct if fv.upside_pct is not None else 0):+.1f}%

FINANCIAL SNAPSHOT (TTM):
  Revenue: {_fmt_b(m.ttm_revenue)} | Revenue Growth YoY: {_fmt_pct(r.revenue_growth)}
  Gross Margin: {_fmt_pct(r.gross_margin)} | Operating Margin: {_fmt_pct(r.operating_margin)}
  Net Margin: {_fmt_pct(r.net_margin)} | FCF Margin: {_fmt_pct(r.fcf_margin)}
  EPS: ${(m.ttm_eps or 0):.2f} | FCF: {_fmt_b(m.ttm_fcf)}

VALUATION vs SECTOR:
  P/E: {_fmt_x(r.pe)} vs sector median {_fmt_x(sm.pe if sm else None)}
  P/S: {_fmt_x(r.ps)} vs sector median {_fmt_x(sm.ps if sm else None)}
  EV/EBITDA: {_fmt_x(r.ev_ebitda)} vs sector median {_fmt_x(sm.ev_ebitda if sm else None)}
  ROE: {_fmt_pct(r.roe)} vs sector median {_fmt_pct(sm.roe if sm else None)}
  D/E: {_fmt_x(r.de)} vs sector median {_fmt_x(sm.de if sm else None)}

RECOMMENDATION RATIONALE: {rec.rationale}
VALUATION METHODS USED: {', '.join(fv.methods_used)}

COMPANY BUSINESS SUMMARY (from Yahoo Finance):
{data.long_description[:1500] if data.long_description else "Not available."}

RECENT NEWS:
{format_news_for_llm(data.news, max_items=10)}
"""

    prompt = f"""{context}

You are an equity research analyst writing a concise professional research memo.
Using ONLY the data provided above (do not invent or estimate any numbers), write:

1. DESCRIPTION (2 sentences): What does this company do? Focus on core business.

2. REVENUE MODEL (2 sentences): How does the company generate revenue? Mention key segments if visible.

3. SECTOR OVERVIEW (2 sentences): Current state of the {profile.sector} sector — key themes, tailwinds, headwinds.

4. INVESTMENT THESIS (exactly 3 to 4 bullet points, each under 20 words):
   Grounded in the financial data above. Start each with "•"

5. KEY RISKS (exactly 3 bullet points, each under 20 words):
   Draw from news headlines and financial data. Start each with "•"

6. KEY CATALYSTS (exactly 3 bullet points, each under 20 words):
   Draw from news headlines and financial data. Start each with "•"

Format your response exactly as:
DESCRIPTION: [text]
REVENUE_MODEL: [text]
SECTOR_OVERVIEW: [text]
INVESTMENT_THESIS:
• [point 1]
• [point 2]
• [point 3]
KEY_RISKS:
• [risk 1]
• [risk 2]
• [risk 3]
KEY_CATALYSTS:
• [catalyst 1]
• [catalyst 2]
• [catalyst 3]

Be concise, factual, and professional. Do not add caveats or disclaimers."""

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    response = client.messages.create(
        model=settings.llm_model,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    text = response.content[0].text
    return _parse_llm_output(text, data.news)


def _parse_llm_output(text: str, news: list[dict]) -> ResearchContent:
    """Parse structured LLM response into ResearchContent."""
    def _extract(label: str) -> str:
        pattern = rf"{label}:\s*(.*?)(?=\n[A-Z_]+:|$)"
        m = re.search(pattern, text, re.DOTALL)
        return m.group(1).strip() if m else ""

    def _extract_bullets(label: str) -> list[str]:
        pattern = rf"{label}:\s*((?:•[^\n]+\n?)+)"
        m = re.search(pattern, text, re.DOTALL)
        if not m:
            return []
        block = m.group(1)
        return [b.lstrip("• ").strip() for b in block.split("•") if b.strip()]

    description = _extract("DESCRIPTION")
    revenue_model = _extract("REVENUE_MODEL")
    sector_overview = _extract("SECTOR_OVERVIEW")
    thesis = _extract_bullets("INVESTMENT_THESIS")
    risks = _extract_bullets("KEY_RISKS")
    catalysts = _extract_bullets("KEY_CATALYSTS")

    # Fallbacks
    if not thesis:
        thesis = ["Refer to valuation analysis above."]
    if not risks:
        risks = ["Refer to sector and company data."]
    if not catalysts:
        catalysts = ["Refer to recent news and financial trends."]

    news_titles = [n.get("title", "") for n in news[:5] if n.get("title")]

    return ResearchContent(
        investment_thesis=thesis[:4],
        sector_overview=sector_overview or f"Sector trends unavailable.",
        key_risks=risks[:3],
        key_catalysts=catalysts[:3],
        news_used=news_titles,
    )


# ── Template fallback ─────────────────────────��───────────────────────────────

def _template_research(
    profile: CompanyProfile,
    data: CompanyData,
    processed: ProcessedFinancials,
    valuation: ValuationOutput,
) -> ResearchContent:
    r = processed.ratios
    fv = valuation.fair_value
    rec = valuation.recommendation
    m = processed.metrics
    sm = processed.sector_stats.median if processed.sector_stats else None
    ticker = profile.ticker
    sector = profile.sector

    # ── Investment thesis ──��──────────────────────────────────────────────────
    thesis = []
    if rec.recommendation == "Buy":
        thesis.append(
            f"{ticker} trades at a discount to {sector} sector comparable fair value "
            f"({fv.upside_pct:+.1f}% upside)." if fv.upside_pct else
            f"{ticker} screens attractively vs. {sector} peers on multiple valuation metrics."
        )
    elif rec.recommendation == "Sell":
        thesis.append(
            f"{ticker} appears overvalued relative to {sector} sector median comparable fair value "
            f"({fv.upside_pct:+.1f}% downside)." if fv.upside_pct else
            f"{ticker} screens as overvalued vs. {sector} sector peers."
        )
    else:
        thesis.append(
            f"{ticker} is broadly fairly valued vs. {sector} sector peers "
            f"(upside: {fv.upside_pct:+.1f}%)." if fv.upside_pct else
            f"{ticker} is broadly in-line with {sector} sector comparable valuations."
        )

    if r.roe and sm and sm.roe:
        if r.roe > sm.roe * 1.10:
            thesis.append(
                f"ROE of {_fmt_pct(r.roe)} meaningfully exceeds sector median ({_fmt_pct(sm.roe)}), "
                "suggesting superior capital efficiency."
            )
        elif r.roe < sm.roe * 0.90:
            thesis.append(
                f"ROE of {_fmt_pct(r.roe)} lags sector median ({_fmt_pct(sm.roe)}), "
                "indicating room for improvement."
            )

    if r.revenue_growth is not None:
        if r.revenue_growth > 0.10:
            thesis.append(f"Double-digit revenue growth ({_fmt_pct(r.revenue_growth)} YoY) ahead of sector peers.")
        elif r.revenue_growth < 0:
            thesis.append(f"Revenue declined {_fmt_pct(abs(r.revenue_growth))} YoY — monitor for stabilisation.")

    if r.fcf_margin and r.fcf_margin > 0.10:
        thesis.append(f"Strong FCF margin ({_fmt_pct(r.fcf_margin)}) provides financial flexibility.")

    if len(thesis) < 3:
        thesis.append(f"Valuation methods used: {', '.join(fv.methods_used) if fv.methods_used else 'sector comps'}.")

    # ── Sector overview ────────────────────────────────────────────────���──────
    sector_overviews = {
        "Information Technology": "The technology sector benefits from secular digitisation tailwinds, AI adoption, and cloud migration, though valuations remain elevated and subject to rate sensitivity.",
        "Communication Services": "Communication services companies face a dual dynamic of digital advertising recovery and streaming competition while investing heavily in AI-driven content and infrastructure.",
        "Financials": "The financial sector is navigating a higher-for-longer rate environment that supports net interest income but pressures loan demand and credit quality.",
        "Health Care": "Healthcare fundamentals remain resilient underpinned by ageing demographics, though drug pricing reform and biosimilar competition present headwinds.",
        "Consumer Discretionary": "Consumer discretionary faces a bifurcated spending environment with resilient high-income consumers offset by trade-down behaviour among price-sensitive households.",
        "Consumer Staples": "Consumer staples companies are benefiting from easing input cost inflation and modest volume recovery after years of price-led growth.",
        "Energy": "Energy sector free cash flow generation remains solid near current commodity prices, supporting buybacks and dividends, though the energy transition adds long-term uncertainty.",
        "Industrials": "Industrial companies are benefiting from infrastructure spending and reshoring trends, while supply chain normalisation supports margin recovery.",
        "Materials": "Materials demand is tied to global industrial activity with cyclical headwinds from slowing China construction and potential trade tariffs.",
        "Utilities": "Utilities face capex-intensive grid modernisation and data centre power demand growth, creating both opportunity and balance sheet pressure.",
        "Real Estate": "Real estate valuations remain compressed relative to history as higher rates weigh on cap rates and refinancing costs.",
    }
    sector_overview = sector_overviews.get(
        sector,
        f"The {sector} sector continues to evolve amid shifting macro conditions. "
        "Peer valuation benchmarking provides useful context for relative positioning."
    )

    # ── Key risks ──────────────────���──────────────────────────────────────────
    risks = []
    if r.de and sm and sm.de and r.de > sm.de * 1.5:
        risks.append(f"Elevated leverage (D/E: {_fmt_x(r.de)}) vs. sector median ({_fmt_x(sm.de)}) limits financial flexibility.")
    if r.revenue_growth is not None and r.revenue_growth < 0:
        risks.append("Negative revenue growth raises questions about demand trajectory.")
    if r.net_margin is not None and r.net_margin < 0:
        risks.append("Negative net margins indicate profitability challenges.")
    # Generic risks by sector
    sector_risks = {
        "Information Technology": ["Regulatory scrutiny of large-cap tech and AI governance risks.", "Valuation compression risk in a higher-rate environment."],
        "Financials": ["Credit quality deterioration in a softening economic environment.", "Net interest margin compression if rate cuts accelerate."],
        "Health Care": ["Drug pricing reform and regulatory pipeline risk.", "Patent cliff exposure and biosimilar competition."],
        "Energy": ["Commodity price volatility driven by OPEC+ policy and demand uncertainty.", "Accelerating energy transition poses long-run demand risk."],
        "Consumer Discretionary": ["Weakening consumer confidence and trade-down risk.", "Tariff and supply chain cost pass-through uncertainty."],
    }
    for generic in sector_risks.get(sector, ["Macro uncertainty and broader market volatility.", "Sector-specific regulatory and competitive risks."]):
        if generic not in risks:
            risks.append(generic)
    if len(risks) < 3:
        risks.append("Data gaps limit full visibility into company-specific risks.")

    # ── Key catalysts ���────────────────────────────────────────────────────────
    catalysts = []
    if fv.upside_pct and fv.upside_pct > 10:
        catalysts.append(f"Re-rating toward sector-median valuation implies {fv.upside_pct:.0f}% upside potential.")
    if r.revenue_growth and r.revenue_growth > 0.08:
        catalysts.append(f"Above-sector revenue growth momentum ({_fmt_pct(r.revenue_growth)} YoY).")
    sector_catalysts = {
        "Information Technology": ["AI monetisation and new product cycle driving estimate revisions.", "Cloud and SaaS renewal cycles supporting recurring revenue growth."],
        "Financials": ["Capital return programs (buybacks and dividends) supporting EPS growth.", "Loan book quality stabilisation underpinning earnings visibility."],
        "Health Care": ["Clinical trial readouts or regulatory approvals acting as near-term catalysts.", "International expansion adding incremental revenue streams."],
        "Energy": ["Commodity price upside driven by supply discipline or demand recovery.", "Free cash flow deployment via buybacks and dividend increases."],
        "Consumer Discretionary": ["New product launch or store expansion driving traffic.", "Pricing power normalisation restoring unit volumes."],
    }
    for generic in sector_catalysts.get(sector, ["Management strategic initiatives or capital allocation improving returns.", "Sector tailwinds and operating leverage driving margin expansion."]):
        if generic not in catalysts:
            catalysts.append(generic)
    if len(catalysts) < 3:
        catalysts.append("Improving macro backdrop supporting sector-wide re-rating.")

    news_titles = [n.get("title", "") for n in data.news[:5] if n.get("title")]

    # Description from yfinance
    description_raw = data.long_description
    if description_raw and len(description_raw) > 300:
        # Use first 2 sentences
        sentences = description_raw.split(". ")
        description = ". ".join(sentences[:2]) + "."
    elif description_raw:
        description = description_raw
    else:
        description = f"{profile.name} is a company in the {sector} sector."

    return ResearchContent(
        investment_thesis=thesis[:4],
        sector_overview=sector_overview,
        key_risks=risks[:3],
        key_catalysts=catalysts[:3],
        news_used=news_titles,
    )
