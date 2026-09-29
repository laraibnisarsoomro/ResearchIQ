# ResearchIQ — System Overview

**Advanced Quantitative Methods & Machine Learning | Spring 2026**  
**Laraib Nisar · Prof. Ali Sanati**

---

## What It Does

ResearchIQ is a fully automated equity research memo generator for S&P 500 stocks. Enter a ticker symbol and within ~60 seconds the system produces a publication-quality investment memo — complete with fair value estimate, Buy/Hold/Sell recommendation, investment thesis, risk factors, catalysts, a live price chart, and sector benchmarking — without a human analyst touching it.

A built-in portfolio builder then takes multiple analyzed stocks and constructs an optimized long/short portfolio with weights, expected return, volatility, and Sharpe ratio.

---

## Architecture

```
Browser (HTML/CSS/JS)
        │  SSE stream (7 progress events + final JSON)
        ▼
FastAPI backend  ──▶  SQLite cache (yfinance data, sector stats, ratios)
        │
        ▼
7-Stage Agentic Pipeline
```

The backend is built with **FastAPI** and streams progress to the browser via **Server-Sent Events (SSE)** so the user sees real-time stage updates. All market data is sourced from **yfinance** (Yahoo Finance API) with an async SQLite cache to avoid redundant fetches.

---

## The 7-Stage Pipeline

| Stage | Agent | What It Does |
|-------|-------|--------------|
| 1 | **Ticker Resolver** | Validates the ticker against the S&P 500 universe, returns company name, sector, industry |
| 2 | **Data Retrieval** | Fetches income statement, balance sheet, cash flow, price history, analyst targets via yfinance |
| 3 | **Financial Processor** | Computes trailing-twelve-month (TTM) figures, 19 financial ratios (PE, PB, PS, EV/EBITDA, ROE, margins, growth rates), benchmarks against sector peers |
| 4 | **Sector Benchmarking** | Aggregates mean/median ratios across all cached sector peers, annotates each metric as above/below peer median |
| 5 | **Valuation Agent** | Estimates fair value using sector-appropriate comparable multiples (weighted blend of PE, PB, PS, EV/EBITDA, P/FCF, EV/Sales); computes upside/downside % |
| 6 | **Research Writer** | Uses Claude (Anthropic API) to write a structured investment thesis, sector overview, key risks, and catalysts grounded in real financial data |
| 7 | **Report Composer + QA** | Assembles the final EquityReport object; QA guardrail checks numeric consistency and flags distorted comparables |

---

## Valuation Methodology

Fair value is a **weighted average of implied prices** from multiple comparable-multiple methods:

**Implied price per method:**
- **P/E** → `sector_median_PE × company_TTM_EPS`
- **P/B** → `sector_median_PB × company_book_value_per_share`
- **P/S** → `sector_median_PS × (TTM_revenue / shares)`
- **EV/EBITDA** → `(sector_median_EVEBITDA × TTM_EBITDA − net_debt) / shares`
- **P/FCF** → `sector_median_PFCF × (TTM_FCF / shares)`

Sector-specific weights reflect how each sector is typically analyzed by practitioners:

| Sector | Primary Method |
|--------|---------------|
| Financials | P/B (50%), P/E (40%) |
| Information Technology | P/S (35%), P/E (35%), EV/Sales (30%) |
| Energy | EV/EBITDA (40%), P/E (35%), P/FCF (25%) |
| Health Care | P/E (40%), EV/EBITDA (35%), P/S (25%) |
| Consumer | P/E (40%), EV/EBITDA (30%), P/S (30%) |

The **base FV** uses sector median multiples. The **high FV** uses sector mean (capturing growth premium). The **low FV** discounts base by 10%.

---

## Recommendation Engine

The recommendation is **rule-based and transparent** (no ML black box):

```
upside > 15% AND no red flags  →  BUY
upside > 15% AND red flags     →  HOLD  (wait for improvement)
upside  5–15% AND quality ≥ 0.50  →  BUY
upside  5–15%                 →  HOLD
upside −15% to +5%            →  HOLD
upside < −15%                 →  SELL
```

**Red flags** checked algorithmically:
- Debt/Equity > 2× sector median
- Negative net margin vs. profitable sector
- Revenue declining > 10% YoY

**Quality score** (0–1): fraction of profitability/leverage/growth metrics beating sector median. Affects confidence level (High/Medium/Low) and rationale wording — but does not override the directional call when upside is clear.

**QA Guardrail** caps confidence to Low when FV > 4× price (likely distorted comparables) and nullifies FV when FV > 8× price.

---

## Portfolio Builder

After generating one or more reports, the user can build a portfolio via the questionnaire:

1. **Investor profiling**: type (retail/institutional), age, experience, risk tolerance, drawdown limit, investment horizon
2. **Strategy resolution**: maps profile → one of {Aggressive Growth, Growth, Balanced, Income, Defensive, Long-Only, Market Neutral}
3. **Stock selection**: pulls all cached tickers matching the selected sectors, ranks longs by upside_pct, shorts by downside (negative upside)
4. **Position sizing**: three modes — Equal Weight, Conviction-Weighted (proportional to upside), or Risk-Parity (inverse beta)
5. **Stats computation**: portfolio-level beta, expected return (CAPM-based), annualized volatility, Sharpe ratio, net/gross exposure
6. **LLM rationale**: Claude writes 3–4 sentences of prose citing the pre-computed numbers (never invents figures)

---

## Data Sources

| Data | Source |
|------|--------|
| Price, fundamentals, ratios | Yahoo Finance via `yfinance` |
| Sector peer list | S&P 500 universe (~503 tickers) refreshed from Wikipedia |
| News/analyst consensus | yfinance analyst targets (`targetMeanPrice`) |
| Investment narrative | Anthropic Claude API (claude-opus-4-7) |
| Company logos | Google faviconV2 API |

**Caching:** All yfinance fetches are cached in SQLite (`equity_research.db`) with a 24-hour TTL to avoid rate limits and speed up repeated lookups.

---

## Frontend

- **Single-page app** — pure HTML/CSS/JS (no React/Vue), served by FastAPI
- **Real-time progress** via SSE: 7 stage bars animate as each pipeline stage completes
- **Price return chart**: 1-year cumulative return vs. S&P 500, rendered with Chart.js
- **Sector-ambient backdrop**: full-page SVG background pattern that changes with the stock's sector (circuit traces for Tech, skyscrapers for Financials, pipelines for Energy, etc.)
- **Gutter content swap**: as user scrolls from equity report to portfolio memo, left/right gutters animate in portfolio-specific visuals (strategy badge, sector donut, Sharpe gauge)
- **Landing page**: live market index strip (S&P 500, NASDAQ, DOW, VIX, 10Y, Crude), animated stat counters, floating ticker chips, mouse-parallax card tilt

---

## Key Design Decisions

**Why comparable multiples instead of DCF?**  
DCF requires forecasting 5–10 years of cash flows, which introduces analyst-level subjectivity. Comparable multiples are fully data-driven: the only inputs are current financials and sector peer ratios. This keeps the system honest and reproducible.

**Why rule-based recommendations instead of ML?**  
With only 503 stocks and no labeled "correct" Buy/Hold/Sell training data, an ML classifier would overfit. The rule-based engine is interpretable, auditable, and never makes a call it can't explain in plain English.

**Why Claude for the narrative layer?**  
Financial ratio tables are accurate but not actionable. Claude converts structured numbers into a coherent investment thesis with sector context, risk factors, and catalysts — the kind of qualitative framing that makes quantitative analysis useful to a decision-maker.

---

## Running Locally

```bash
# Install dependencies
pip install -r requirements.txt

# Set Anthropic API key (optional — app runs without LLM in stub mode)
export ANTHROPIC_API_KEY=sk-ant-...

# Start server
uvicorn backend.main:app --reload

# Open browser
open http://localhost:8000
```

---

*Built with FastAPI · SQLAlchemy · yfinance · Anthropic Claude · Chart.js*
