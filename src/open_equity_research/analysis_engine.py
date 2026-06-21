from __future__ import annotations

import math
from datetime import date
from typing import Iterable

from .models import Claim, Finding, MetricSeries


def _latest(series: MetricSeries | None):
    return series.points[-1] if series and series.points else None


def _previous(series: MetricSeries | None):
    return series.points[-2] if series and len(series.points) >= 2 else None


def _evidence_ids(
    evidence_index: dict[tuple[str, str], str], pairs: Iterable[tuple[str, str]]
) -> tuple[str, ...]:
    return tuple(
        evidence_index[pair] for pair in pairs if pair in evidence_index
    )


def _annualized_growth(first_value: float, last_value: float, first_end: str, last_end: str) -> float | None:
    if first_value <= 0 or last_value <= 0:
        return None
    try:
        years = (date.fromisoformat(last_end) - date.fromisoformat(first_end)).days / 365.25
    except ValueError:
        return None
    if years <= 0:
        return None
    return (last_value / first_value) ** (1 / years) - 1


def build_findings(
    metrics: dict[str, MetricSeries], evidence_index: dict[tuple[str, str], str]
) -> list[Finding]:
    findings: list[Finding] = []

    revenue = metrics.get("revenue")
    if revenue and len(revenue.points) >= 2:
        first, last = revenue.points[0], revenue.points[-1]
        growth = _annualized_growth(first.value, last.value, first.period_end, last.period_end)
        if growth is not None:
            findings.append(
                Finding(
                    finding_id="F-FUND-REVENUE-TREND",
                    agent="fundamental",
                    severity="info",
                    title="Multi-year revenue trajectory",
                    description=f"Annualized revenue change over the available period was {growth:.1%}.",
                    evidence_ids=_evidence_ids(
                        evidence_index,
                        (("revenue", first.period_end), ("revenue", last.period_end)),
                    ),
                )
            )

    operating_margin = metrics.get("operating_margin")
    latest_margin, previous_margin = _latest(operating_margin), _previous(operating_margin)
    if latest_margin:
        delta_text = ""
        if previous_margin:
            delta_text = f"; year-over-year change was {(latest_margin.value - previous_margin.value):+.1%}"
        findings.append(
            Finding(
                finding_id="F-FUND-OPERATING-MARGIN",
                agent="fundamental",
                severity="info",
                title="Operating profitability",
                description=f"Latest annual operating margin was {latest_margin.value:.1%}{delta_text}.",
                evidence_ids=_evidence_ids(
                    evidence_index,
                    (("operating_margin", latest_margin.period_end),),
                ),
            )
        )

    fcf = metrics.get("free_cash_flow")
    latest_fcf = _latest(fcf)
    if latest_fcf:
        severity = "high" if latest_fcf.value < 0 else "info"
        findings.append(
            Finding(
                finding_id="F-FUND-FCF",
                agent="fundamental",
                severity=severity,
                title="Free cash flow screen",
                description=(
                    "Latest derived free cash flow was negative."
                    if latest_fcf.value < 0
                    else "Latest derived free cash flow was positive."
                ),
                evidence_ids=_evidence_ids(
                    evidence_index, (("free_cash_flow", latest_fcf.period_end),)
                ),
            )
        )

    net_cash = metrics.get("net_cash")
    latest_net_cash = _latest(net_cash)
    if latest_net_cash:
        findings.append(
            Finding(
                finding_id="F-FUND-NET-CASH",
                agent="fundamental",
                severity="medium" if latest_net_cash.value < 0 else "info",
                title="Balance-sheet net cash screen",
                description=(
                    "Reported cash was below reported current and non-current debt."
                    if latest_net_cash.value < 0
                    else "Reported cash exceeded reported current and non-current debt."
                ),
                evidence_ids=_evidence_ids(
                    evidence_index, (("net_cash", latest_net_cash.period_end),)
                ),
            )
        )

    latest_revenue, previous_revenue = _latest(revenue), _previous(revenue)
    if latest_revenue and previous_revenue and latest_revenue.value < previous_revenue.value:
        findings.append(
            Finding(
                finding_id="F-BEAR-REVENUE-DECLINE",
                agent="bear",
                severity="medium",
                title="Revenue declined in the latest annual period",
                description="The latest annual revenue observation was below the prior annual observation.",
                evidence_ids=_evidence_ids(
                    evidence_index,
                    (
                        ("revenue", previous_revenue.period_end),
                        ("revenue", latest_revenue.period_end),
                    ),
                ),
            )
        )

    if latest_margin and previous_margin and latest_margin.value < previous_margin.value - 0.03:
        findings.append(
            Finding(
                finding_id="F-BEAR-MARGIN-COMPRESSION",
                agent="bear",
                severity="medium",
                title="Operating margin compression",
                description="Latest annual operating margin declined by more than three percentage points.",
                evidence_ids=_evidence_ids(
                    evidence_index,
                    (
                        ("operating_margin", previous_margin.period_end),
                        ("operating_margin", latest_margin.period_end),
                    ),
                ),
            )
        )

    cash_conversion = metrics.get("cash_conversion")
    latest_conversion = _latest(cash_conversion)
    if latest_conversion and math.isfinite(latest_conversion.value) and latest_conversion.value < 0.7:
        findings.append(
            Finding(
                finding_id="F-BEAR-CASH-CONVERSION",
                agent="bear",
                severity="medium",
                title="Cash conversion screening flag",
                description=(
                    "Operating cash flow was below 70% of net income in the latest annual period. "
                    "This is a screening flag, not a conclusion about accounting quality."
                ),
                evidence_ids=_evidence_ids(
                    evidence_index, (("cash_conversion", latest_conversion.period_end),)
                ),
            )
        )

    shares = metrics.get("diluted_shares")
    if shares and len(shares.points) >= 2:
        first, last = shares.points[0], shares.points[-1]
        dilution = _annualized_growth(first.value, last.value, first.period_end, last.period_end)
        if dilution is not None and dilution > 0.02:
            findings.append(
                Finding(
                    finding_id="F-BEAR-DILUTION",
                    agent="bear",
                    severity="medium",
                    title="Share-count dilution screen",
                    description=f"Diluted weighted-average shares increased at roughly {dilution:.1%} annualized.",
                    evidence_ids=_evidence_ids(
                        evidence_index,
                        (("diluted_shares", first.period_end), ("diluted_shares", last.period_end)),
                    ),
                )
            )

    required = ("revenue", "operating_income", "net_income", "operating_cash_flow", "cash")
    missing = [key for key in required if not metrics.get(key) or not metrics[key].points]
    if missing:
        findings.append(
            Finding(
                finding_id="F-RISK-DATA-GAPS",
                agent="risk",
                severity="high",
                title="Material XBRL coverage gaps",
                description="No usable annual observations were extracted for: " + ", ".join(missing) + ".",
                evidence_ids=(),
            )
        )

    return findings


def build_claims(
    metrics: dict[str, MetricSeries], evidence_index: dict[tuple[str, str], str]
) -> list[Claim]:
    claims: list[Claim] = []
    revenue = metrics.get("revenue")
    if revenue and len(revenue.points) >= 2:
        first, last = revenue.points[0], revenue.points[-1]
        direction = "expanded" if last.value > first.value else "contracted"
        claims.append(
            Claim(
                claim_id="C-REVENUE-TRAJECTORY",
                text=f"Reported annual revenue {direction} over the available multi-year SEC series.",
                stance="supportive" if direction == "expanded" else "adverse",
                confidence="medium",
                evidence_ids=_evidence_ids(
                    evidence_index,
                    (("revenue", first.period_end), ("revenue", last.period_end)),
                ),
                falsification_condition="A corrected or restated filing reverses the observed direction.",
            )
        )

    fcf = _latest(metrics.get("free_cash_flow"))
    if fcf:
        positive = fcf.value > 0
        claims.append(
            Claim(
                claim_id="C-LATEST-FCF",
                text=f"Latest derived annual free cash flow was {'positive' if positive else 'not positive'}.",
                stance="supportive" if positive else "adverse",
                confidence="medium",
                evidence_ids=_evidence_ids(
                    evidence_index, (("free_cash_flow", fcf.period_end),)
                ),
                falsification_condition=(
                    "A different, explicitly justified capital-expenditure definition or corrected SEC fact "
                    "changes the free-cash-flow sign."
                ),
            )
        )

    net_cash = _latest(metrics.get("net_cash"))
    if net_cash:
        claims.append(
            Claim(
                claim_id="C-NET-CASH",
                text=(
                    "Reported cash exceeded current plus non-current debt."
                    if net_cash.value >= 0
                    else "Current plus non-current debt exceeded reported cash."
                ),
                stance="supportive" if net_cash.value >= 0 else "adverse",
                confidence="medium",
                evidence_ids=_evidence_ids(
                    evidence_index, (("net_cash", net_cash.period_end),)
                ),
                falsification_condition=(
                    "Debt-like obligations excluded from tagged debt or restricted cash adjustments materially "
                    "change the balance-sheet conclusion."
                ),
            )
        )
    return claims
