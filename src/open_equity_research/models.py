from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class CompanyIdentity:
    ticker: str
    cik: str
    name: str
    exchange: str = ""
    sic: str = ""
    sic_description: str = ""
    fiscal_year_end: str = ""


@dataclass(frozen=True)
class Filing:
    accession_number: str
    form: str
    filing_date: str
    report_date: str
    primary_document: str
    source_url: str


@dataclass(frozen=True)
class MetricPoint:
    metric: str
    label: str
    value: float
    unit: str
    period_start: str | None
    period_end: str
    filed: str
    form: str
    accession: str
    taxonomy: str
    concept: str
    source_url: str


@dataclass(frozen=True)
class MetricSeries:
    key: str
    label: str
    unit: str
    points: tuple[MetricPoint, ...] = field(default_factory=tuple)
    derived: bool = False


@dataclass(frozen=True)
class Evidence:
    evidence_id: str
    kind: str
    metric: str
    label: str
    value: float
    unit: str
    period_start: str | None
    period_end: str
    filed: str
    form: str
    accession: str
    taxonomy: str
    concept: str
    source_url: str
    notes: str = ""


@dataclass(frozen=True)
class Finding:
    finding_id: str
    agent: str
    severity: str
    title: str
    description: str
    evidence_ids: tuple[str, ...] = field(default_factory=tuple)
    status: str = "open"


@dataclass(frozen=True)
class Claim:
    claim_id: str
    text: str
    stance: str
    confidence: str
    evidence_ids: tuple[str, ...] = field(default_factory=tuple)
    falsification_condition: str = ""
    status: str = "observed"


@dataclass(frozen=True)
class ReviewIssue:
    issue_id: str
    severity: str
    category: str
    problem: str
    required_fix: str
    status: str = "open"
    evidence_ids: tuple[str, ...] = field(default_factory=tuple)


@dataclass
class ResearchState:
    ticker: str
    status: str
    iteration: int
    stale_count: int
    updated_at: str
    completed_stages: list[str]
    open_blockers: list[str]
    last_error: str | None = None


def dataclass_dict(value: Any) -> dict[str, Any]:
    from dataclasses import asdict

    return asdict(value)
