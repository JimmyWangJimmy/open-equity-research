from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from typing import Any

from .models import MetricPoint, MetricSeries
from .sec_client import SECClient


@dataclass(frozen=True)
class MetricSpec:
    key: str
    label: str
    concepts: tuple[tuple[str, str], ...]
    units: tuple[str, ...]
    kind: str  # duration or instant


METRIC_SPECS: tuple[MetricSpec, ...] = (
    MetricSpec(
        "revenue",
        "Revenue",
        (
            ("us-gaap", "RevenueFromContractWithCustomerExcludingAssessedTax"),
            ("us-gaap", "SalesRevenueNet"),
            ("us-gaap", "Revenues"),
        ),
        ("USD",),
        "duration",
    ),
    MetricSpec(
        "gross_profit",
        "Gross profit",
        (("us-gaap", "GrossProfit"),),
        ("USD",),
        "duration",
    ),
    MetricSpec(
        "operating_income",
        "Operating income",
        (("us-gaap", "OperatingIncomeLoss"),),
        ("USD",),
        "duration",
    ),
    MetricSpec(
        "net_income",
        "Net income",
        (("us-gaap", "NetIncomeLoss"), ("us-gaap", "ProfitLoss")),
        ("USD",),
        "duration",
    ),
    MetricSpec(
        "operating_cash_flow",
        "Operating cash flow",
        (("us-gaap", "NetCashProvidedByUsedInOperatingActivities"),),
        ("USD",),
        "duration",
    ),
    MetricSpec(
        "capital_expenditures",
        "Capital expenditures",
        (
            ("us-gaap", "PaymentsToAcquirePropertyPlantAndEquipment"),
            ("us-gaap", "PaymentsForAdditionsToPropertyPlantAndEquipment"),
        ),
        ("USD",),
        "duration",
    ),
    MetricSpec(
        "research_and_development",
        "Research and development",
        (("us-gaap", "ResearchAndDevelopmentExpense"),),
        ("USD",),
        "duration",
    ),
    MetricSpec(
        "stock_compensation",
        "Share-based compensation",
        (("us-gaap", "ShareBasedCompensation"),),
        ("USD",),
        "duration",
    ),
    MetricSpec(
        "cash",
        "Cash and cash equivalents",
        (
            ("us-gaap", "CashAndCashEquivalentsAtCarryingValue"),
            ("us-gaap", "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"),
        ),
        ("USD",),
        "instant",
    ),
    MetricSpec(
        "debt_current",
        "Current debt",
        (
            ("us-gaap", "LongTermDebtCurrent"),
            ("us-gaap", "ShortTermBorrowings"),
            ("us-gaap", "ShortTermDebtCurrent"),
        ),
        ("USD",),
        "instant",
    ),
    MetricSpec(
        "debt_noncurrent",
        "Non-current debt",
        (("us-gaap", "LongTermDebtNoncurrent"),),
        ("USD",),
        "instant",
    ),
    MetricSpec(
        "assets",
        "Total assets",
        (("us-gaap", "Assets"),),
        ("USD",),
        "instant",
    ),
    MetricSpec(
        "liabilities",
        "Total liabilities",
        (("us-gaap", "Liabilities"),),
        ("USD",),
        "instant",
    ),
    MetricSpec(
        "equity",
        "Stockholders' equity",
        (
            ("us-gaap", "StockholdersEquity"),
            ("us-gaap", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"),
        ),
        ("USD",),
        "instant",
    ),
    MetricSpec(
        "diluted_shares",
        "Diluted weighted-average shares",
        (("us-gaap", "WeightedAverageNumberOfDilutedSharesOutstanding"),),
        ("shares",),
        "duration",
    ),
)


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _is_annual_observation(observation: dict[str, Any], kind: str) -> bool:
    form = str(observation.get("form", ""))
    if form not in {"10-K", "10-K/A"}:
        return False
    end = _parse_date(str(observation.get("end", "")))
    if end is None:
        return False
    if kind == "instant":
        return not observation.get("start")
    start = _parse_date(str(observation.get("start", "")))
    if start is None:
        return False
    duration = (end - start).days
    return 270 <= duration <= 430


def _candidate_observations(
    companyfacts: dict[str, Any], spec: MetricSpec
) -> list[tuple[int, str, str, str, dict[str, Any]]]:
    output: list[tuple[int, str, str, str, dict[str, Any]]] = []
    facts_root = companyfacts.get("facts", {})
    if not isinstance(facts_root, dict):
        return output
    for priority, (taxonomy, concept) in enumerate(spec.concepts):
        concept_payload = facts_root.get(taxonomy, {}).get(concept, {})
        units_payload = concept_payload.get("units", {}) if isinstance(concept_payload, dict) else {}
        if not isinstance(units_payload, dict):
            continue
        for unit in spec.units:
            observations = units_payload.get(unit, [])
            if not isinstance(observations, list):
                continue
            for observation in observations:
                if isinstance(observation, dict) and _is_annual_observation(observation, spec.kind):
                    output.append((priority, taxonomy, concept, unit, observation))
    return output


def extract_metric_series(
    companyfacts: dict[str, Any], cik: str, spec: MetricSpec, years: int = 5
) -> MetricSeries:
    selected: dict[str, tuple[int, str, str, str, dict[str, Any]]] = {}
    for candidate in _candidate_observations(companyfacts, spec):
        priority, taxonomy, concept, unit, observation = candidate
        period_end = str(observation.get("end", ""))
        if not period_end:
            continue
        value = observation.get("val")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        existing = selected.get(period_end)
        if existing is None:
            selected[period_end] = candidate
            continue
        existing_priority, _, _, _, existing_observation = existing
        existing_filed = str(existing_observation.get("filed", ""))
        candidate_filed = str(observation.get("filed", ""))
        if priority < existing_priority or (
            priority == existing_priority and candidate_filed > existing_filed
        ):
            selected[period_end] = candidate

    points: list[MetricPoint] = []
    for period_end, selected_candidate in selected.items():
        _, taxonomy, concept, unit, observation = selected_candidate
        accession = str(observation.get("accn", ""))
        points.append(
            MetricPoint(
                metric=spec.key,
                label=spec.label,
                value=float(observation["val"]),
                unit=unit,
                period_start=str(observation.get("start")) if observation.get("start") else None,
                period_end=period_end,
                filed=str(observation.get("filed", "")),
                form=str(observation.get("form", "")),
                accession=accession,
                taxonomy=taxonomy,
                concept=concept,
                source_url=SECClient.filing_index_url(cik, accession),
            )
        )
    points.sort(key=lambda point: (point.period_end, point.filed))
    return MetricSeries(spec.key, spec.label, spec.units[0], tuple(points[-years:]))


def _derive_binary_series(
    key: str,
    label: str,
    left: MetricSeries,
    right: MetricSeries,
    operator,
    formula: str,
    unit: str,
) -> MetricSeries:
    left_map = {point.period_end: point for point in left.points}
    right_map = {point.period_end: point for point in right.points}
    output: list[MetricPoint] = []
    for period_end in sorted(set(left_map) & set(right_map)):
        a = left_map[period_end]
        b = right_map[period_end]
        try:
            value = float(operator(a.value, b.value))
        except (ZeroDivisionError, ValueError, OverflowError):
            continue
        output.append(
            MetricPoint(
                metric=key,
                label=label,
                value=value,
                unit=unit,
                period_start=a.period_start or b.period_start,
                period_end=period_end,
                filed=max(a.filed, b.filed),
                form=a.form,
                accession=a.accession,
                taxonomy="derived",
                concept=formula,
                source_url=a.source_url,
            )
        )
    return MetricSeries(key, label, unit, tuple(output), derived=True)


def _derive_optional_sum(
    key: str,
    label: str,
    left: MetricSeries,
    right: MetricSeries,
) -> MetricSeries:
    left_map = {point.period_end: point for point in left.points}
    right_map = {point.period_end: point for point in right.points}
    output: list[MetricPoint] = []
    for period_end in sorted(set(left_map) | set(right_map)):
        a = left_map.get(period_end)
        b = right_map.get(period_end)
        if a is None and b is None:
            continue
        anchor = a or b
        assert anchor is not None
        value = (a.value if a else 0.0) + (b.value if b else 0.0)
        output.append(
            MetricPoint(
                metric=key,
                label=label,
                value=value,
                unit="USD",
                period_start=None,
                period_end=period_end,
                filed=max(a.filed if a else "", b.filed if b else ""),
                form=anchor.form,
                accession=anchor.accession,
                taxonomy="derived",
                concept="debt_current + debt_noncurrent",
                source_url=anchor.source_url,
            )
        )
    return MetricSeries(key, label, "USD", tuple(output), derived=True)


def extract_all_metrics(
    companyfacts: dict[str, Any], cik: str, years: int = 5
) -> dict[str, MetricSeries]:
    metrics = {
        spec.key: extract_metric_series(companyfacts, cik, spec, years=years)
        for spec in METRIC_SPECS
    }
    metrics["free_cash_flow"] = _derive_binary_series(
        "free_cash_flow",
        "Free cash flow",
        metrics["operating_cash_flow"],
        metrics["capital_expenditures"],
        lambda cfo, capex: cfo - abs(capex),
        "operating_cash_flow - abs(capital_expenditures)",
        "USD",
    )
    metrics["total_debt"] = _derive_optional_sum(
        "total_debt", "Total debt", metrics["debt_current"], metrics["debt_noncurrent"]
    )
    metrics["net_cash"] = _derive_binary_series(
        "net_cash",
        "Net cash",
        metrics["cash"],
        metrics["total_debt"],
        lambda cash, debt: cash - debt,
        "cash - total_debt",
        "USD",
    )
    metrics["operating_margin"] = _derive_binary_series(
        "operating_margin",
        "Operating margin",
        metrics["operating_income"],
        metrics["revenue"],
        lambda operating_income, revenue: operating_income / revenue,
        "operating_income / revenue",
        "ratio",
    )
    metrics["net_margin"] = _derive_binary_series(
        "net_margin",
        "Net margin",
        metrics["net_income"],
        metrics["revenue"],
        lambda net_income, revenue: net_income / revenue,
        "net_income / revenue",
        "ratio",
    )
    metrics["free_cash_flow_margin"] = _derive_binary_series(
        "free_cash_flow_margin",
        "Free cash flow margin",
        metrics["free_cash_flow"],
        metrics["revenue"],
        lambda fcf, revenue: fcf / revenue,
        "free_cash_flow / revenue",
        "ratio",
    )
    metrics["cash_conversion"] = _derive_binary_series(
        "cash_conversion",
        "Operating cash flow / net income",
        metrics["operating_cash_flow"],
        metrics["net_income"],
        lambda cfo, net_income: cfo / net_income,
        "operating_cash_flow / net_income",
        "ratio",
    )
    return metrics


def serialize_metrics(metrics: dict[str, MetricSeries]) -> dict[str, Any]:
    return {key: asdict(series) for key, series in sorted(metrics.items())}
