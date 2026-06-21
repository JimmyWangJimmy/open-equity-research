from __future__ import annotations

from dataclasses import asdict
from typing import Iterable

from .io_utils import safe_identifier
from .models import Evidence, MetricSeries


def evidence_id(metric: str, period_end: str) -> str:
    return f"E-{safe_identifier(metric).upper()}-{period_end.replace('-', '')}"


def build_evidence(metrics: dict[str, MetricSeries]) -> list[Evidence]:
    output: list[Evidence] = []
    for metric_key, series in sorted(metrics.items()):
        for point in series.points:
            notes = ""
            kind = "derived_metric" if series.derived else "sec_xbrl_fact"
            if series.derived:
                notes = f"Deterministic formula: {point.concept}. Verify underlying raw facts."
            output.append(
                Evidence(
                    evidence_id=evidence_id(metric_key, point.period_end),
                    kind=kind,
                    metric=metric_key,
                    label=series.label,
                    value=point.value,
                    unit=point.unit,
                    period_start=point.period_start,
                    period_end=point.period_end,
                    filed=point.filed,
                    form=point.form,
                    accession=point.accession,
                    taxonomy=point.taxonomy,
                    concept=point.concept,
                    source_url=point.source_url,
                    notes=notes,
                )
            )
    return output


def index_evidence(evidence: Iterable[Evidence]) -> dict[tuple[str, str], str]:
    return {(item.metric, item.period_end): item.evidence_id for item in evidence}


def serialize_evidence(evidence: Iterable[Evidence]) -> list[dict]:
    return [asdict(item) for item in evidence]
