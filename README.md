# ResearchIQ — Setup & Usage Guide

**FIN-680 Term Project — Advanced Quantitative Methods and Machine Learning**
**Student:** Laraib Nisar &nbsp;·&nbsp; **Professor:** Ali Sanati

ResearchIQ is a local web application that generates institutional-quality equity research memos for any S&P 500 stock and constructs hypothetical portfolios. The system runs entirely on a laptop — no cloud account or paid data subscription required.

> **For the academic write-up, see [`PROPOSAL.md`](PROPOSAL.md). For technical architecture details, see [`SYSTEM_OVERVIEW.md`](SYSTEM_OVERVIEW.md).**

---

## What You Need

- **A Mac or Linux laptop** (Windows works too — see note at the end)
- **Python 3.9 or newer** — check with `python3 --version` in Terminal
   - If not installed, download from [python.org](https://www.python.org/downloads/)
- **An internet connection** (the app fetches market data from Yahoo Finance)
- **(Optional) An Anthropic API key** for AI-generated investment narratives. Without it, the app falls back to template-based prose and works fine.

---

## Setup — Three Steps

### 1. Open Terminal in the project folder

```bash
cd path/to/equity_research_app
```

### 2. Run the setup script (one time only)

```bash
./setup.sh
```

This script will:
- Create a Python virtual environment in `.venv/`
- Install all required Python packages (FastAPI, yfinance, pandas, etc.)
- Copy `.env.example` → `.env` if not already present

It takes about **2–3 minutes** the first time. You'll see "Setup complete!" when it's done.

> **If `./setup.sh` says "permission denied":** run `chmod +x setup.sh` first, then `./setup.sh`.

### 3. Start the app

```bash
python run.py
```

You'll see:
```
ResearchIQ starting…  →  http://localhost:8000
```

Open your browser and go to **<http://localhost:8000>** — that's it.

To stop the app, press **`Ctrl + C`** in the terminal.

---

## How to Use the App

### Generate an Equity Research Memo

1. On the landing page, type any S&P 500 ticker (e.g., `AAPL`, `JPM`, `MSFT`, `NVDA`)
2. Click **Generate Memo** (or press Enter)
3. Watch the 7-stage progress bar — the full memo appears in about 60 seconds

The memo includes: company description, current price vs. fair value range, Buy/Hold/Sell recommendation with confidence level, 1-year price chart vs. S&P 500, financial metrics benchmarked against sector peers, investment thesis bullets, key risks, and catalysts.

### Build a Portfolio

1. After generating any memo, scroll down and click **Build Portfolio Recommendation**
2. Answer the 5-section questionnaire (investor profile, amount, risk tolerance, sectors, constraints)
3. Click **Generate My Portfolio** on the last section

You'll get a hypothetical portfolio with long (and possibly short) positions, expected return, volatility, Sharpe ratio, sector allocation, and a written rationale.

> The questionnaire **remembers your answers** — if you want to tweak just one input (e.g., change sectors), reopen it and only change that field.

---

## Optional: Enable AI-Generated Narratives

By default the app uses template-based text for investment thesis and risks. To enable Claude-powered prose:

1. Get an API key from [console.anthropic.com](https://console.anthropic.com/)
2. Open the `.env` file in any text editor
3. Replace `sk-ant-...` on the first line with your actual key
4. Restart the app (`Ctrl + C`, then `python run.py` again)

A typical memo costs about **$0.01–0.03** in API usage.

---

## Troubleshooting

**"Command not found: python3"**
→ Python isn't installed. Get it from [python.org](https://www.python.org/downloads/).

**"./setup.sh: permission denied"**
→ Run `chmod +x setup.sh` first, then `./setup.sh`.

**App says "No candidates available" when building a portfolio**
→ The cache is empty. Generate a few equity memos first (try AAPL, MSFT, JPM, NVDA, GOOGL) — each one populates sector data. Or run `python seed_portfolio_data.py` to bulk-seed analyst data for ~150 popular S&P 500 tickers (takes ~5 minutes).

**Port 8000 already in use**
→ Another app is using port 8000. Either stop that app or edit the last line of `run.py` to use a different port (e.g., `port=8001`), then visit `http://localhost:8001`.

**Browser shows old layout after I update something**
→ Hard refresh: `Cmd + Shift + R` (Mac) or `Ctrl + Shift + R` (Windows/Linux).

---

## Project Structure

```
equity_research_app/
├── PROPOSAL.md              ← The academic research proposal (main deliverable)
├── SYSTEM_OVERVIEW.md       ← Technical architecture reference
├── README.md                ← This file (setup + usage)
├── run.py                   ← Launcher (use this to start the app)
├── setup.sh                 ← One-time setup script
├── seed_portfolio_data.py   ← Optional bulk-seeder for portfolio data
├── requirements.txt         ← Python dependencies
├── .env.example             ← Environment config template
├── backend/                 ← FastAPI server + 7-stage agentic pipeline
│   ├── agents/                  ← Pipeline stages (data, valuation, writer, QA)
│   ├── analytics/               ← Financial calculation engine
│   ├── data/                    ← yfinance + universe management
│   ├── db/                      ← SQLite cache layer
│   ├── models/                  ← Pydantic schemas
│   ├── portfolio/               ← Portfolio construction logic
│   └── main.py                  ← FastAPI app entry point
├── frontend/                ← Single-page web UI (vanilla HTML/CSS/JS)
│   ├── index.html
│   ├── css/style.css
│   └── js/app.js, portfolio.js
└── data/                    ← Auto-created SQLite cache (yfinance data)
```

---

## Windows Users

The setup script (`setup.sh`) is for Mac/Linux. On Windows, run these commands manually in PowerShell from the project folder:

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt
copy .env.example .env
python run.py
```

Then open <http://localhost:8000> in your browser.

---

## Methods Summary

The system implements course methods including:
- **Comparable-multiple valuation** (P/E, P/B, P/S, P/FCF, EV/EBITDA) with sector-specific weighting
- **Rule-based recommendation engine** (transparent, auditable Buy/Hold/Sell logic)
- **CAPM-based portfolio expected return** with bounded valuation alpha
- **Beta-weighted portfolio risk model** with idiosyncratic component
- **Agentic LLM workflow** for research narrative synthesis (separation of quantitative computation and qualitative writing)

Full methodology, formulas, and references are in [`PROPOSAL.md`](PROPOSAL.md).
