"""Agent 7 — QA guardrails: validate numeric consistency and flag weak evidence."""
from __future__ import annotations

import logging
from typing import Optional

from backend.models.schemas import EquityReport

logger = logging.getLogger(__name__)


class QAResult:
    def __init__(self, passed: bool, warnings: list[str], report: EquityReport):
        self.passed = passed
        self.warnings = warnings
        self.report = report


def run_qa(report: EquityReport) -> QAResult:
    warnings: list[str] = []

    # 1. Price sanity
    if report.current_price <= 0:
        warnings.append("Current price is zero or negative — market data may be stale.")

    # 2. Fair value sanity
    if report.fair_value_base is not None:
        ratio = report.fair_value_base / report.current_price if report.current_price > 0 else 0
        if ratio > 8.0:
            warnings.append(
                "Fair value base is >8x current price — comparables may be severely distorted. "
                "Review sector peer quality."
            )
            # Extreme distortion: wipe FV and hold
            report = report.model_copy(
                update={
                    "upside_pct": None,
                    "fair_value_base": None,
                    "fair_value_low": None,
                    "fair_value_high": None,
                    "recommendation": "Hold",
                    "confidence": "Low",
                    "rationale": "Fair value estimate unreliable — sector comparable multiples appear severely distorted.",
                }
            )
        elif ratio > 4.0:
            warnings.append(
                f"Fair value base is {ratio:.1f}x current price — comparables may be distorted. "
                "Upside estimate should be treated with caution; consider alongside analyst consensus."
            )
            # Keep the Buy call but downgrade confidence
            if report.confidence == "High":
                report = report.model_copy(update={"confidence": "Medium"})
        elif ratio < 0.1:
            warnings.append(
                "Fair value base is <10% of current price — comparables may be distorted. "
                "Review sector peer quality."
            )

    # 3. Confidence vs data completeness
    if report.data_completeness_pct < 25 and report.confidence != "Low":
        warnings.append(
            f"Data completeness is only {report.data_completeness_pct}% — "
            "confidence downgraded to Low."
        )
        report = report.model_copy(update={"confidence": "Low"})

    # 4. Thesis quality
    if len(report.investment_thesis) == 0:
        warnings.append("Investment thesis is empty.")
        report = report.model_copy(
            update={"investment_thesis": ["Insufficient data to generate investment thesis."]}
        )

    # 5. Upside / recommendation consistency check
    if report.upside_pct is not None:
        if report.recommendation == "Buy" and report.upside_pct < 5:
            warnings.append(
                "Buy recommendation with <5% upside — may reflect quality premium. "
                "Verify recommendation logic."
            )
        if report.recommendation == "Sell" and report.upside_pct > 0:
            warnings.append(
                "Sell recommendation with positive upside — may reflect quality/risk override."
            )

    # 6. Peer count
    if report.peer_count < 3:
        warnings.append(
            f"Only {report.peer_count} sector peers available for benchmarking — "
            "sector statistics may not be representative."
        )

    passed = len([w for w in warnings if "distorted" in w.lower()]) == 0

    if warnings:
        logger.info("QA warnings for %s: %s", report.ticker, warnings)

    return QAResult(passed=passed, warnings=warnings, report=report)
