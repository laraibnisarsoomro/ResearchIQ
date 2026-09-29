#!/usr/bin/env bash
# ── ResearchIQ Setup Script ───────────────────────────────────────────────────
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo ""
echo "  ╔═══════════════════════════════════════╗"
echo "  ║  ResearchIQ — Equity Research Memos   ║"
echo "  ║  Setup Script                         ║"
echo "  ╚═══════════════════════════════════════╝"
echo ""

# 1. Check Python
PYTHON=$(which python3 || which python || echo "")
if [ -z "$PYTHON" ]; then
  echo "ERROR: Python 3.9+ is required. Install it from python.org"
  exit 1
fi
PY_VER=$("$PYTHON" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo "Using Python $PY_VER at $PYTHON"

# 2. Create virtual environment
if [ ! -d ".venv" ]; then
  echo "Creating virtual environment…"
  "$PYTHON" -m venv .venv
fi

source .venv/bin/activate
echo "Virtual environment activated."

# 3. Upgrade pip
pip install --upgrade pip --quiet

# 4. Install dependencies
echo "Installing Python dependencies…"
pip install -r requirements.txt --quiet

# 5. Create .env if not present
if [ ! -f ".env" ]; then
  cp .env.example .env
  echo ""
  echo "  NOTE: .env file created from .env.example"
  echo "  To enable LLM-generated research content, add your Anthropic API key:"
  echo "    ANTHROPIC_API_KEY=sk-ant-..."
  echo "  (The app works without it — falls back to template-based text.)"
fi

# 6. Create data directory
mkdir -p data

echo ""
echo "  ✓ Setup complete!"
echo ""
echo "  To start the app:"
echo "    source .venv/bin/activate   # if not already active"
echo "    python run.py"
echo ""
echo "  Then open: http://localhost:8000"
echo ""

