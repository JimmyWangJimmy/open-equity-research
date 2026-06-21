from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any, Iterable

from .io_utils import atomic_write_text, utc_now_iso
from .models import Filing


DISPLAY_METRICS = (
    "revenue",
    "operating_income",
    "net_income",
    "operating_cash_flow",
    "capital_expenditures",
    "free_cash_flow",
    "cash",
    "total_debt",
    "net_cash",
    "diluted_shares",
    "operating_margin",
    "free_cash_flow_margin",
)


def _format_value(value: float, unit: str) -> str:
    if unit == "ratio":
        return f"{value:.1%}"
    if unit == "shares":
        absolute = abs(value)
        if absolute >= 1_000_000_000:
            return f"{value / 1_000_000_000:.2f}B"
        if absolute >= 1_000_000:
            return f"{value / 1_000_000:.2f}M"
        return f"{value:,.0f}"
    if unit == "USD":
        absolute = abs(value)
        sign = "-" if value < 0 else ""
        if absolute >= 1_000_000_000_000:
            return f"{sign}${absolute / 1_000_000_000_000:.2f}T"
        if absolute >= 1_000_000_000:
            return f"{sign}${absolute / 1_000_000_000:.2f}B"
        if absolute >= 1_000_000:
            return f"{sign}${absolute / 1_000_000:.2f}M"
        return f"{sign}${absolute:,.0f}"
    return f"{value:,.4g} {unit}".strip()


def _metric_table(metrics: dict[str, Any]) -> str:
    periods = sorted(
        {
            point["period_end"]
            for key in DISPLAY_METRICS
            for point in metrics.get(key, {}).get("points", [])
        }
    )[-5:]
    if not periods:
        return "No usable annual XBRL metrics were extracted."
    lines = ["| Metric | " + " | ".join(periods) + " |", "|---|" + "---:|" * len(periods)]
    for key in DISPLAY_METRICS:
        series = metrics.get(key, {})
        points = {point["period_end"]: point for point in series.get("points", [])}
        if not points:
            continue
        cells = []
        for period in periods:
            point = points.get(period)
            if not point:
                cells.append("—")
                continue
            rendered = _format_value(float(point["value"]), str(point["unit"]))
            source = point.get("source_url")
            cells.append(f"[{rendered}]({source})" if source else rendered)
        lines.append(f"| {series.get('label', key)} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


def _render_findings(findings: list[dict[str, Any]]) -> str:
    if not findings:
        return "No deterministic findings were generated."
    lines = ["| Severity | Agent | Finding | Evidence |", "|---|---|---|---|"]
    order = {"high": 0, "medium": 1, "info": 2, "low": 3}
    for item in sorted(findings, key=lambda row: (order.get(row.get("severity", ""), 9), row.get("finding_id", ""))):
        evidence = ", ".join(f"`{value}`" for value in item.get("evidence_ids", [])) or "—"
        description = str(item.get("description", "")).replace("|", "\\|")
        lines.append(
            f"| {item.get('severity', '')} | {item.get('agent', '')} | "
            f"**{item.get('title', '')}** — {description} | {evidence} |"
        )
    return "\n".join(lines)


def _render_claims(claims: list[dict[str, Any]]) -> str:
    if not claims:
        return "No claims were generated."
    lines = ["| Claim | Stance | Confidence | Evidence | Falsification condition |", "|---|---|---|---|---|"]
    for item in claims:
        evidence = ", ".join(f"`{value}`" for value in item.get("evidence_ids", [])) or "—"
        text = str(item.get("text", "")).replace("|", "\\|")
        falsification = str(item.get("falsification_condition", "")).replace("|", "\\|")
        lines.append(
            f"| {text} | {item.get('stance', '')} | {item.get('confidence', '')} | "
            f"{evidence} | {falsification} |"
        )
    return "\n".join(lines)


def _render_issues(issues: list[dict[str, Any]]) -> str:
    if not issues:
        return "No open review issues."
    lines = ["| Severity | Category | Problem | Required fix |", "|---|---|---|---|"]
    for item in issues:
        problem = str(item.get("problem", "")).replace("|", "\\|")
        required = str(item.get("required_fix", "")).replace("|", "\\|")
        lines.append(
            f"| {item.get('severity', '')} | {item.get('category', '')} | {problem} | {required} |"
        )
    return "\n".join(lines)


def _render_filings(filings: Iterable[Filing]) -> str:
    rows = list(filings)
    if not rows:
        return "No recent filings were recorded."
    lines = ["| Form | Filing date | Report date | Filing |", "|---|---|---|---|"]
    for filing in rows:
        lines.append(
            f"| {filing.form} | {filing.filing_date} | {filing.report_date} | "
            f"[{filing.accession_number}]({filing.source_url}) |"
        )
    return "\n".join(lines)


def _render_valuation(results: list[dict[str, Any]] | None) -> str:
    if not results:
        return (
            "No valuation result is included. Edit `valuation_assumptions.json`, document the evidence behind "
            "each assumption, set `human_reviewed` to `true`, and run the valuation command."
        )
    lines = ["| Scenario | Enterprise value | Equity value | Value/share | Implied return |", "|---|---:|---:|---:|---:|"]
    for item in results:
        implied = item.get("implied_return")
        implied_text = f"{float(implied):.1%}" if implied is not None else "—"
        lines.append(
            f"| {item['name']} | {_format_value(item['enterprise_value'], 'USD')} | "
            f"{_format_value(item['equity_value'], 'USD')} | ${item['value_per_share']:.2f} | "
            f"{implied_text} |"
        )
    return "\n".join(lines)


def generate_report(
    path: Path,
    *,
    company: dict[str, Any],
    filings: list[Filing],
    metrics: dict[str, Any],
    findings: list[dict[str, Any]],
    claims: list[dict[str, Any]],
    issues: list[dict[str, Any]],
    narrative_sections: dict[str, str] | None = None,
    valuation_results: list[dict[str, Any]] | None = None,
) -> None:
    sections = narrative_sections or {}
    section_status = "\n".join(
        f"- `{name}`: {len(text):,} extracted characters" for name, text in sections.items() if text
    ) or "- No narrative 10-K sections were extracted reliably."
    content = f'''# {company.get("name", company.get("ticker", "Company"))} ({company.get("ticker", "")}) — Evidence-First Research Packet

> **Research artifact only. This is not investment advice, a buy/sell rating, or an instruction to trade.**<br>
> The system has no broker integration and does not execute orders.

Generated: {utc_now_iso()}<br>
CIK: `{company.get("cik", "")}`<br>
Exchange: {company.get("exchange", "") or "not supplied"}<br>
SIC: {company.get("sic", "") or "not supplied"} — {company.get("sic_description", "") or "not supplied"}<br>
Fiscal year end: {company.get("fiscal_year_end", "") or "not supplied"}

## Research status

The automated stage has collected and normalized public SEC evidence. It has **not** established an investment recommendation. Business quality, competitive position, management credibility, valuation assumptions, portfolio fit, and real-time market data require separate verification and human judgment.

## Recent SEC filings

{_render_filings(filings)}

## Annual financial evidence

Each linked number points to the SEC filing index used as provenance. Derived values are deterministic screens and still require accounting review.

{_metric_table(metrics)}

## Deterministic agent findings

These are rule-based observations designed to surface questions, not predict returns.

{_render_findings(findings)}

## Claim–evidence ledger

{_render_claims(claims)}

The machine-readable ledger is in `evidence.jsonl`; every evidence item contains period, filing date, taxonomy concept, accession number, and source URL.

## Narrative filing extraction

The parser made a best-effort extraction from the latest 10-K. Heading conventions vary, so extracted boundaries must be checked against the original filing.

{section_status}

## Valuation gate

{_render_valuation(valuation_results)}

## Open review issues

{_render_issues(issues)}

## Agent work packets

`agent_tasks/` contains isolated tasks for Fundamental, Bear, Risk, and Verifier roles. Every material output is required to cite evidence IDs. Outputs from an LLM remain untrusted until independently checked.

## Known limitations

- The current release prioritizes SEC filings and does not include licensed market data, earnings-call transcripts, news, alternative data, or broker execution.
- XBRL tags vary by issuer. Alias matching and derived metrics can be incomplete or economically misleading.
- Free cash flow is screened as operating cash flow minus the absolute value of tagged capital expenditures; company-specific definitions may differ.
- The generic DCF is unsuitable for many financial institutions and may be inappropriate for REITs, early-stage firms, cyclicals, or businesses with material off-balance-sheet obligations.
- Historical financial evidence does not establish future returns. Price, dilution, taxes, incentives, competition, regulation, and portfolio context remain material.

## Human decision gates

1. Verify the latest 10-K/10-Q facts and accounting definitions.
2. Add company-specific industry and competitive evidence.
3. Write both a positive thesis and a disconfirming thesis.
4. Replace generic valuation assumptions and document their sources.
5. Review portfolio concentration, liquidity, tax, and maximum-loss constraints.
6. Keep any trade decision outside this repository's automated workflow.
'''
    atomic_write_text(path, content)
