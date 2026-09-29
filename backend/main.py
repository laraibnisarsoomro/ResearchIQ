"""FastAPI application — equity research memo generator."""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import AsyncGenerator

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sse_starlette.sse import EventSourceResponse

from backend.agents.data_retrieval import retrieve_company_data
from backend.agents.financial_processor import process_financials
from backend.agents.qa_guardrail import run_qa
from backend.agents.report_composer import compose_report
from backend.agents.research_writer import write_research
from backend.agents.ticker_resolver import resolve_ticker
from backend.agents.valuation_agent import run_valuation
from backend.config import settings
from backend.data.yfinance_client import get_price_history, get_latest_close
from backend.db.database import get_db, init_db
from backend.data.universe import refresh_universe, universe_needs_refresh
from backend.models.schemas import EquityReport, ReportRequest
from backend.analytics.sector_benchmarks import upsert_company_ratios
from backend.portfolio.schemas import PortfolioRequest, PortfolioResponse
from backend.portfolio.strategy import resolve_strategy, strategy_books, STRATEGY_DESCRIPTIONS
from backend.portfolio.builder import build_portfolio

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Equity Research Memo Generator", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup():
    await init_db()
    logger.info("Database initialised at %s", settings.db_path)


# ── Static files & frontend ────────────────────────────────────────────────────
_FRONTEND = Path(__file__).parent.parent / "frontend"


@app.get("/", response_class=HTMLResponse)
async def serve_index():
    html_path = _FRONTEND / "index.html"
    return html_path.read_text(encoding="utf-8")


app.mount("/static", StaticFiles(directory=str(_FRONTEND)), name="static")


# ── Health ─────────────────────────────────────────────────────────────────────
@app.get("/api/health")
async def health():
    return {"status": "ok", "llm_enabled": settings.has_llm, "model": settings.llm_model}


# ── Universe management ────────────────────────────────────────────────────────
@app.get("/api/universe/status")
async def universe_status():
    from sqlalchemy import select, func
    from backend.db.models import UniverseEntry
    async for db in get_db():
        needs = await universe_needs_refresh(db)
        result = await db.execute(select(func.count()).select_from(UniverseEntry))
        count = result.scalar_one()
        return {"ticker_count": count, "needs_refresh": needs}


@app.post("/api/universe/refresh")
async def universe_refresh():
    async for db in get_db():
        count = await refresh_universe(db)
        return {"refreshed": True, "ticker_count": count}


# ── Ticker validation ──────────────────────────────────────────────────────────
@app.get("/api/ticker/{ticker}/validate")
async def validate_ticker(ticker: str):
    async for db in get_db():
        try:
            profile = await resolve_ticker(db, ticker.upper())
            return {"valid": True, "name": profile.name, "sector": profile.sector}
        except ValueError as exc:
            return JSONResponse(status_code=404, content={"valid": False, "error": str(exc)})


# ── Main report generation (SSE streaming) ────────────────────────────────────
@app.get("/api/report/stream")
async def report_stream(ticker: str, request: Request):
    """Generate an equity report with Server-Sent Events progress updates."""

    async def generate() -> AsyncGenerator[dict, None]:
        ticker_upper = ticker.upper().strip()

        async def _emit(stage: int, total: int, message: str):
            yield {
                "event": "progress",
                "data": json.dumps({
                    "stage": stage,
                    "total": total,
                    "message": message,
                    "done": False,
                }),
            }

        async def _error(msg: str):
            yield {
                "event": "error",
                "data": json.dumps({"error": msg, "done": True}),
            }

        async for db in get_db():
            try:
                # Stage 1: Resolve ticker
                async for event in _emit(1, 7, f"Resolving ticker {ticker_upper}…"):
                    yield event
                profile = await resolve_ticker(db, ticker_upper)

                # Stage 2: Retrieve data
                async for event in _emit(2, 7, f"Fetching market data for {profile.name}…"):
                    yield event
                data = await retrieve_company_data(db, ticker_upper)
                if data.info.get("currentPrice") is None and data.info.get("regularMarketPrice") is None:
                    # Try to get price from fast_info
                    pass  # TTM calculator handles this gracefully

                # Stage 3: Process financials
                async for event in _emit(3, 7, "Computing financial metrics and TTM figures…"):
                    yield event
                processed = await process_financials(db, data, profile.sector)

                # Always fetch the freshest closing price (uncached) so the report
                # reflects the most recent trading day, not the cached info dict.
                live_close = await get_latest_close(ticker_upper)
                if live_close and live_close > 0:
                    current_price = live_close
                    processed.metrics = processed.metrics.model_copy(update={"current_price": live_close})
                else:
                    current_price = processed.metrics.current_price or 0.0
                    if current_price <= 0:
                        current_price = float(data.info.get("regularMarketPrice") or data.info.get("ask") or 0)

                # Stage 4: Sector benchmarking message
                peer_count = processed.sector_stats.peer_count if processed.sector_stats else 0
                async for event in _emit(4, 7, f"Benchmarking against {peer_count} {profile.sector} sector peers…"):
                    yield event

                # Stage 5: Valuation
                async for event in _emit(5, 7, "Estimating fair value via sector comparables…"):
                    yield event
                valuation = run_valuation(processed, profile.sector, current_price)

                # Stage 6: Research writing
                async for event in _emit(6, 7, "Writing investment thesis, risks, and catalysts…"):
                    yield event
                research = await write_research(profile, data, processed, valuation)

                # Stage 7: Compose & QA
                async for event in _emit(7, 7, "Finalising and validating report…"):
                    yield event
                report = compose_report(profile, data, processed, valuation, research)

                # Set description from data
                desc = data.long_description
                if desc and len(desc) > 500:
                    sentences = desc.split(". ")
                    desc = ". ".join(sentences[:3]) + "."
                elif not desc:
                    desc = f"{profile.name} operates in the {profile.sector} sector."
                website = data.info.get("website") or ""
                report = report.model_copy(update={"description": desc, "website": website})

                # Fetch price history (non-critical, wrapped in try/except)
                try:
                    price_history = await get_price_history(db, ticker_upper, period="1y")
                    if price_history:
                        report = report.model_copy(update={"price_history": price_history})
                except Exception as exc:
                    logger.debug("Price history fetch failed for %s: %s", ticker_upper, exc)

                qa_result = run_qa(report)
                final_report = qa_result.report

                # Persist upside_pct + beta into ratios cache for portfolio builder
                try:
                    await upsert_company_ratios(
                        db, ticker_upper, profile.sector, processed.ratios,
                        market_cap=processed.metrics.market_cap or 0.0,
                        upside_pct=final_report.upside_pct,
                        beta=processed.metrics.beta,
                    )
                except Exception:
                    pass

                yield {
                    "event": "report",
                    "data": json.dumps({
                        "done": True,
                        "report": final_report.model_dump(),
                        "warnings": qa_result.warnings,
                    }),
                }

            except ValueError as exc:
                async for event in _error(str(exc)):
                    yield event
            except Exception as exc:
                logger.exception("Unhandled error generating report for %s", ticker_upper)
                async for event in _error(f"An unexpected error occurred: {exc}"):
                    yield event

    return EventSourceResponse(generate())


# ── Legacy POST endpoint (non-streaming) ──────────────────────────────────────
@app.post("/api/report")
async def generate_report(req: ReportRequest):
    """Synchronous report generation (no streaming)."""
    ticker = req.ticker.upper().strip()
    async for db in get_db():
        try:
            profile = await resolve_ticker(db, ticker)
            data = await retrieve_company_data(db, ticker)
            processed = await process_financials(db, data, profile.sector)

            # Always fetch the freshest closing price (uncached) so the report
            # reflects the most recent trading day, not the cached info dict.
            live_close = await get_latest_close(ticker)
            if live_close and live_close > 0:
                current_price = live_close
                processed.metrics = processed.metrics.model_copy(update={"current_price": live_close})
            else:
                current_price = processed.metrics.current_price or float(
                    data.info.get("regularMarketPrice") or 0
                )

            valuation = run_valuation(processed, profile.sector, current_price)
            research = await write_research(profile, data, processed, valuation)
            report = compose_report(profile, data, processed, valuation, research)
            desc = data.long_description
            if desc and len(desc) > 500:
                desc = ". ".join(desc.split(". ")[:3]) + "."
            website = data.info.get("website") or ""
            report = report.model_copy(update={"description": desc or report.description, "website": website})

            # Fetch price history (non-critical, wrapped in try/except)
            try:
                price_history = await get_price_history(db, ticker, period="1y")
                if price_history:
                    report = report.model_copy(update={"price_history": price_history})
            except Exception as exc:
                logger.debug("Price history fetch failed for %s: %s", ticker, exc)

            qa = run_qa(report)
            # Persist upside_pct + beta for portfolio builder
            try:
                await upsert_company_ratios(
                    db, ticker, profile.sector, processed.ratios,
                    market_cap=processed.metrics.market_cap or 0.0,
                    upside_pct=qa.report.upside_pct,
                    beta=processed.metrics.beta,
                )
            except Exception:
                pass
            return {"report": qa.report.model_dump(), "warnings": qa.warnings}
        except ValueError as exc:
            return JSONResponse(status_code=404, content={"error": str(exc)})
        except Exception as exc:
            logger.exception("Error generating report for %s", ticker)
            return JSONResponse(status_code=500, content={"error": str(exc)})


# ── Portfolio builder ──────────────────────────────────────────────────────────
@app.post("/api/portfolio")
async def generate_portfolio(req: PortfolioRequest):
    async for db in get_db():
        try:
            # 1. Resolve strategy
            strategy = resolve_strategy(
                investor_type=req.investor_type,
                investor_subtype=req.investor_subtype,
                age=req.age,
                objective=req.objective,
                drawdown_tolerance=req.drawdown_tolerance,
            )
            strategy_desc = STRATEGY_DESCRIPTIONS[strategy]

            # 2. Build positions + compute stats (all deterministic)
            long_pos, short_pos, stats, warning = await build_portfolio(
                db=db,
                anchor_ticker=req.anchor_ticker,
                sectors=req.sectors,
                investment_amount=req.investment_amount,
                max_positions=req.max_positions,
                sizing_style=req.sizing_style,
                strategy=strategy,
            )
            stats.strategy_description = strategy_desc

            # 3. Pairs trade highlight
            pairs_long_ticker = long_pos[0].ticker if long_pos else None
            pairs_long_company = long_pos[0].company if long_pos else None
            pairs_short_ticker = short_pos[0].ticker if short_pos else None
            pairs_short_company = short_pos[0].company if short_pos else None
            pairs_sector = req.sectors[0] if req.sectors else None

            # 4. LLM rationale (passes only pre-computed numbers — never invents)
            rationale = await _write_portfolio_rationale(req, strategy, stats, long_pos, short_pos)

            return PortfolioResponse(
                strategy=strategy,
                strategy_description=strategy_desc,
                stats=stats,
                long_positions=long_pos,
                short_positions=short_pos,
                pairs_long_ticker=pairs_long_ticker,
                pairs_long_company=pairs_long_company,
                pairs_short_ticker=pairs_short_ticker,
                pairs_short_company=pairs_short_company,
                pairs_sector=pairs_sector,
                rationale=rationale,
                warning=warning,
            )
        except Exception as exc:
            logger.exception("Portfolio generation failed")
            return JSONResponse(status_code=500, content={"error": str(exc)})


async def _write_portfolio_rationale(
    req: PortfolioRequest,
    strategy: str,
    stats: PortfolioStats,
    long_pos: list,
    short_pos: list,
) -> str:
    """Call the LLM once with all pre-computed values. LLM writes prose only."""
    if not settings.has_llm:
        return (
            f"A {strategy} portfolio targeting {stats.expected_return_pct:.1f}% expected return "
            f"with {stats.portfolio_vol_pct:.1f}% estimated annualised volatility and a "
            f"{stats.sharpe_ratio:.2f} illustrative Sharpe ratio, built across "
            f"{', '.join(req.sectors[:3])} sectors."
        )

    import anthropic
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    top_longs = long_pos[:2]
    top_short = short_pos[:1]

    prompt = f"""You are writing an investment rationale for a hypothetical portfolio memo.
Write exactly 3-4 sentences. No bullet points. No headers. No markdown.
Every sentence must reference specific numbers provided below.
Do not use generic phrases like "in today's market environment" or "aligned with your goals."
Do not invent any numbers not listed here.
Do not mention macroeconomic conditions.
{"Do not mention short selling." if strategy == "Long-Only" else ""}
Write in a professional but accessible tone for the given investor type.
Keep it under 100 words.

INPUTS:
- Investor: {req.investor_type} ({req.investor_subtype}), age {req.age}
- Horizon: {req.horizon}
- Objective: {req.objective}
- Drawdown tolerance: {req.drawdown_tolerance}
- Experience: {req.experience}
- Strategy: {strategy} — {stats.strategy_description}
- Sectors selected: {', '.join(req.sectors)}
- Investment amount: ${req.investment_amount:,.0f}
- Expected portfolio return: {stats.expected_return_pct:.1f}%
- Expected portfolio volatility: {stats.portfolio_vol_pct:.1f}% (annualised, beta-based)
- Approximate Sharpe ratio: {stats.sharpe_ratio:.2f}
- Portfolio beta: {stats.portfolio_beta:.2f}
- Net exposure: {stats.net_exposure_pct:.0f}%
- Gross exposure: {stats.gross_exposure_pct:.0f}%
- Anchor ticker: {req.anchor_ticker} ({req.anchor_recommendation})
{f"- Top long 1: {top_longs[0].ticker} ({top_longs[0].company}), upside {top_longs[0].upside_pct:.1f}%, weight {top_longs[0].weight_pct:.1f}%" if len(top_longs) > 0 else ""}
{f"- Top long 2: {top_longs[1].ticker} ({top_longs[1].company}), upside {top_longs[1].upside_pct:.1f}%, weight {top_longs[1].weight_pct:.1f}%" if len(top_longs) > 1 else ""}
{f"- Top short: {top_short[0].ticker} ({top_short[0].company}), downside {top_short[0].upside_pct:.1f}%, weight {top_short[0].weight_pct:.1f}%" if top_short else ""}

Write the rationale now:"""

    msg = client.messages.create(
        model=settings.llm_model,
        max_tokens=200,
        messages=[{"role": "user", "content": prompt}],
    )
    return msg.content[0].text.strip()


if __name__ == "__main__":
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
