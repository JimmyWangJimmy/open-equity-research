from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from .analysis_engine import build_claims, build_findings
from .config import Settings
from .evidence import build_evidence, index_evidence
from .facts import extract_all_metrics, serialize_metrics
from .filing_text import extract_10k_sections, html_to_text
from .io_utils import (
    append_jsonl,
    atomic_write_json,
    atomic_write_text,
    load_json,
    utc_now_iso,
    write_jsonl,
)
from .models import CompanyIdentity, ResearchState, ReviewIssue
from .prompt_pack import export_prompt_pack
from .report import generate_report
from .sec_client import SECClient
from .valuation import write_assumption_template
from .verify import verify_company_workspace


class ResearchOrchestrator:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @staticmethod
    def _task_spec(identity: CompanyIdentity) -> str:
        return f'''# Research contract: {identity.name} ({identity.ticker})

## Objective

Create an auditable, evidence-first U.S. equity research packet from public SEC disclosures. The packet must surface both supportive and adverse evidence but must not issue a trade instruction.

## Primary questions

1. What do the latest annual filings establish about revenue, margins, cash generation, leverage, and dilution?
2. Which observations weaken an attractive thesis?
3. Which claims remain unsupported by the current evidence?
4. What company-specific assumptions would be required for valuation?

## Falsification rules

- A claim is invalid if its cited evidence does not directly support its wording.
- A derived metric is provisional if the issuer's accounting definition differs from the implemented formula.
- A valuation is blocked until a human documents and approves company-specific assumptions.
- Missing or contradictory evidence must remain visible; it must not be silently filled by an LLM.

## Out of scope

Broker connectivity, order execution, personalized suitability, tax advice, leverage recommendations, options strategies, and claims of guaranteed or risk-free return.
'''

    @staticmethod
    def _review_issues(
        identity: CompanyIdentity,
        metrics: dict[str, Any],
        sections: dict[str, str],
        filings_count: int,
    ) -> list[ReviewIssue]:
        issues = [
            ReviewIssue(
                "R-VALUATION-HUMAN-GATE",
                "blocking",
                "valuation",
                "The generated DCF assumptions are generic placeholders and have not been approved.",
                "Document company-specific growth, reinvestment, discount-rate, terminal-value, dilution, and net-debt assumptions; then set human_reviewed=true.",
            ),
            ReviewIssue(
                "R-INDUSTRY-EVIDENCE",
                "high",
                "competitive_analysis",
                "SEC financial facts alone do not establish market structure, competitive advantage, customer behavior, or product quality.",
                "Add independently verified industry, customer, competitor, and product evidence with source provenance.",
            ),
            ReviewIssue(
                "R-REALTIME-PRICE",
                "medium",
                "market_data",
                "No licensed real-time or point-in-time market-price source is included.",
                "Provide an as-of price from an authorized source and record its timestamp before comparing price with valuation.",
            ),
        ]
        try:
            sic = int(identity.sic) if identity.sic else 0
        except ValueError:
            sic = 0
        if 6000 <= sic <= 6799:
            issues.append(
                ReviewIssue(
                    "R-FINANCIAL-SECTOR-MODEL",
                    "blocking",
                    "sector_model",
                    "The generic free-cash-flow and net-debt framework is generally inappropriate for financial companies.",
                    "Use a sector-specific capital, credit, liquidity, and valuation model before drawing conclusions.",
                )
            )
        essential = ("revenue", "net_income", "operating_cash_flow", "cash", "diluted_shares")
        missing = [key for key in essential if not metrics.get(key, {}).get("points")]
        if missing:
            issues.append(
                ReviewIssue(
                    "R-XBRL-COVERAGE",
                    "high",
                    "data_quality",
                    "Essential XBRL series are missing: " + ", ".join(missing) + ".",
                    "Inspect the issuer's custom tags and financial statements, then add explicit mappings or manual evidence.",
                )
            )
        if filings_count == 0:
            issues.append(
                ReviewIssue(
                    "R-NO-FILINGS",
                    "blocking",
                    "data_quality",
                    "No recent 10-K, 10-Q, or 8-K filing metadata was captured.",
                    "Verify ticker/CIK resolution and SEC availability before continuing.",
                )
            )
        if not any(sections.values()):
            issues.append(
                ReviewIssue(
                    "R-NARRATIVE-EXTRACTION",
                    "medium",
                    "document_parsing",
                    "The latest 10-K narrative sections were not extracted reliably.",
                    "Review the original 10-K and add business, risk-factor, and MD&A evidence manually.",
                )
            )
        return issues

    def run(self, ticker: str, *, force_refresh: bool = False) -> dict[str, Any]:
        normalized = ticker.strip().upper()
        company_dir = self.settings.workspace / normalized
        company_dir.mkdir(parents=True, exist_ok=True)
        previous = load_json(company_dir / "progress.json", {}) or {}
        iteration = int(previous.get("iteration", 0)) + 1
        state = ResearchState(
            ticker=normalized,
            status="running",
            iteration=iteration,
            stale_count=int(previous.get("stale_count", 0)),
            updated_at=utc_now_iso(),
            completed_stages=[],
            open_blockers=[],
        )
        atomic_write_json(company_dir / "progress.json", asdict(state))

        try:
            client = SECClient(self.settings, force_refresh=force_refresh)
            mapping = client.resolve_ticker(normalized)
            submissions = client.get_submissions(mapping["cik"])
            companyfacts = client.get_companyfacts(mapping["cik"])
            state.completed_stages.append("sec_data_collected")

            exchanges = submissions.get("exchanges") or []
            identity = CompanyIdentity(
                ticker=normalized,
                cik=mapping["cik"],
                name=str(submissions.get("name") or mapping["name"]),
                exchange=str(mapping.get("exchange") or (exchanges[0] if exchanges else "")),
                sic=str(submissions.get("sic") or ""),
                sic_description=str(submissions.get("sicDescription") or ""),
                fiscal_year_end=str(submissions.get("fiscalYearEnd") or ""),
            )
            company_payload = asdict(identity)
            atomic_write_json(company_dir / "company.json", company_payload)
            atomic_write_text(company_dir / "task_spec.md", self._task_spec(identity))

            snapshots = company_dir / "source_snapshots"
            snapshots.mkdir(parents=True, exist_ok=True)
            atomic_write_json(snapshots / "submissions.json", submissions)
            atomic_write_json(snapshots / "companyfacts.json", companyfacts)
            atomic_write_json(snapshots / "metadata.json", client.snapshot_metadata())

            filings = client.recent_filings(
                submissions, identity.cik, forms={"10-K", "10-K/A", "10-Q", "10-Q/A", "8-K"}, limit=20
            )
            write_jsonl(company_dir / "filings.jsonl", [asdict(filing) for filing in filings])

            narrative_sections: dict[str, str] = {}
            latest_10k = next((filing for filing in filings if filing.form in {"10-K", "10-K/A"}), None)
            if latest_10k:
                raw_document = client.get_document_text(latest_10k.source_url)
                plain_text = html_to_text(raw_document)
                narrative_sections = extract_10k_sections(plain_text)
                atomic_write_text(snapshots / "latest_10k.html", raw_document)
                atomic_write_text(snapshots / "latest_10k.txt", plain_text)
                atomic_write_json(snapshots / "10k_sections.json", narrative_sections)
                state.completed_stages.append("latest_10k_parsed")

            metric_objects = extract_all_metrics(companyfacts, identity.cik)
            metrics = serialize_metrics(metric_objects)
            atomic_write_json(company_dir / "metrics.json", metrics)
            state.completed_stages.append("metrics_normalized")

            evidence_objects = build_evidence(metric_objects)
            evidence_rows = [asdict(item) for item in evidence_objects]
            write_jsonl(company_dir / "evidence.jsonl", evidence_rows)
            evidence_index = index_evidence(evidence_objects)
            findings_objects = build_findings(metric_objects, evidence_index)
            claims_objects = build_claims(metric_objects, evidence_index)
            findings = [asdict(item) for item in findings_objects]
            claims = [asdict(item) for item in claims_objects]
            write_jsonl(company_dir / "findings.jsonl", findings)
            write_jsonl(company_dir / "claims.jsonl", claims)
            state.completed_stages.append("claim_evidence_graph_built")

            issues_objects = self._review_issues(identity, metrics, narrative_sections, len(filings))
            issues = [asdict(item) for item in issues_objects]
            write_jsonl(company_dir / "review_issues.jsonl", issues)

            write_assumption_template(company_dir / "valuation_assumptions.json", metrics)
            export_prompt_pack(company_dir, company_payload)
            state.completed_stages.append("agent_tasks_exported")

            generate_report(
                company_dir / "report.md",
                company=company_payload,
                filings=filings,
                metrics=metrics,
                findings=findings,
                claims=claims,
                issues=issues,
                narrative_sections=narrative_sections,
            )
            state.completed_stages.append("report_generated")

            previous_count = int(previous.get("evidence_count", 0))
            current_count = len(evidence_rows)
            state.stale_count = 0 if current_count > previous_count else state.stale_count + 1
            state.status = "research_packet_ready"
            state.updated_at = utc_now_iso()
            state.open_blockers = [
                issue.issue_id for issue in issues_objects if issue.severity == "blocking"
            ]
            progress_payload = asdict(state)
            progress_payload["evidence_count"] = current_count
            progress_payload["finding_count"] = len(findings)
            progress_payload["claim_count"] = len(claims)
            atomic_write_json(company_dir / "progress.json", progress_payload)

            directions = load_json(company_dir / "directions_tried.json", []) or []
            direction = {
                "iteration": iteration,
                "direction": "SEC submissions + XBRL normalization + latest 10-K narrative extraction",
                "evidence_count": current_count,
                "completed_at": state.updated_at,
            }
            directions.append(direction)
            atomic_write_json(company_dir / "directions_tried.json", directions)
            append_jsonl(
                company_dir / "iteration_log.jsonl",
                {
                    "iteration": iteration,
                    "status": state.status,
                    "evidence_count": current_count,
                    "stale_count": state.stale_count,
                    "completed_stages": state.completed_stages,
                    "updated_at": state.updated_at,
                },
            )
            verification = verify_company_workspace(company_dir)
            return {
                "company_dir": str(company_dir),
                "report": str(company_dir / "report.md"),
                "evidence_count": current_count,
                "finding_count": len(findings),
                "claim_count": len(claims),
                "open_blockers": state.open_blockers,
                "verification_ok": verification["ok"],
            }
        except Exception as exc:
            state.status = "error"
            state.updated_at = utc_now_iso()
            state.last_error = str(exc)
            atomic_write_json(company_dir / "progress.json", asdict(state))
            append_jsonl(
                company_dir / "iteration_log.jsonl",
                {
                    "iteration": iteration,
                    "status": "error",
                    "error": str(exc),
                    "updated_at": state.updated_at,
                },
            )
            raise
