from __future__ import annotations

from pathlib import Path
from typing import Any

from .io_utils import atomic_write_json, load_json, load_jsonl, utc_now_iso


def verify_company_workspace(company_dir: Path) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def record(name: str, ok: bool, detail: str) -> None:
        checks.append({"name": name, "ok": ok, "detail": detail})

    required = (
        "company.json",
        "progress.json",
        "metrics.json",
        "evidence.jsonl",
        "findings.jsonl",
        "claims.jsonl",
        "review_issues.jsonl",
        "report.md",
        "valuation_assumptions.json",
    )
    missing = [name for name in required if not (company_dir / name).exists()]
    record("required_artifacts", not missing, "missing: " + ", ".join(missing) if missing else "all present")

    evidence = load_jsonl(company_dir / "evidence.jsonl")
    evidence_ids = [str(item.get("evidence_id", "")) for item in evidence]
    record(
        "unique_evidence_ids",
        len(evidence_ids) == len(set(evidence_ids)) and all(evidence_ids),
        f"{len(evidence_ids)} evidence records",
    )

    allowed_sources = all(
        str(item.get("source_url", "")).startswith("https://www.sec.gov/Archives/edgar/data/")
        for item in evidence
        if item.get("source_url")
    )
    record("sec_source_provenance", allowed_sources, "all evidence URLs use SEC filing archives")

    known = set(evidence_ids)
    missing_references: list[str] = []
    for artifact_name in ("findings.jsonl", "claims.jsonl", "review_issues.jsonl"):
        for item in load_jsonl(company_dir / artifact_name):
            for reference in item.get("evidence_ids", []):
                if reference not in known:
                    missing_references.append(f"{artifact_name}:{reference}")
    record(
        "evidence_references",
        not missing_references,
        "unresolved: " + ", ".join(missing_references) if missing_references else "all references resolve",
    )

    report_path = company_dir / "report.md"
    report_text = report_path.read_text(encoding="utf-8") if report_path.exists() else ""
    record(
        "report_disclaimer",
        "not investment advice" in report_text.lower() and "does not execute orders" in report_text.lower(),
        "report contains non-advice and no-execution controls",
    )

    assumptions = load_json(company_dir / "valuation_assumptions.json", {}) or {}
    record(
        "valuation_human_gate",
        assumptions.get("human_reviewed") in {True, False},
        "human_reviewed field is explicit",
    )

    snapshot_dir = company_dir / "source_snapshots"
    snapshots = [snapshot_dir / "submissions.json", snapshot_dir / "companyfacts.json"]
    record("source_snapshots", all(path.exists() for path in snapshots), "SEC JSON snapshots preserved")

    result = {
        "ok": all(check["ok"] for check in checks),
        "verified_at": utc_now_iso(),
        "checks": checks,
    }
    atomic_write_json(company_dir / "verification.json", result)
    return result
