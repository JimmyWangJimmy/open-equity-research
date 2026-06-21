from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .exceptions import ValuationError
from .io_utils import atomic_write_json


@dataclass(frozen=True)
class DCFScenario:
    name: str
    growth_rates: tuple[float, ...]
    discount_rate: float
    terminal_growth_rate: float


@dataclass(frozen=True)
class DCFResult:
    name: str
    enterprise_value: float
    equity_value: float
    value_per_share: float
    implied_return: float | None
    projected_free_cash_flow: tuple[float, ...]


def _latest_metric(metrics: dict[str, Any], key: str) -> float | None:
    payload = metrics.get(key, {})
    points = payload.get("points", []) if isinstance(payload, dict) else []
    if not points:
        return None
    value = points[-1].get("value")
    return float(value) if isinstance(value, (int, float)) else None


def generate_assumption_template(metrics: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "human_reviewed": False,
        "review_notes": "Replace generic assumptions with a documented, company-specific thesis.",
        "starting_free_cash_flow": _latest_metric(metrics, "free_cash_flow"),
        "net_cash": _latest_metric(metrics, "net_cash"),
        "diluted_shares": _latest_metric(metrics, "diluted_shares"),
        "market_price": None,
        "scenarios": [
            {
                "name": "bear",
                "growth_rates": [-0.05, -0.03, 0.00, 0.01, 0.02],
                "discount_rate": 0.12,
                "terminal_growth_rate": 0.015,
            },
            {
                "name": "base",
                "growth_rates": [0.03, 0.03, 0.03, 0.03, 0.03],
                "discount_rate": 0.10,
                "terminal_growth_rate": 0.025,
            },
            {
                "name": "bull",
                "growth_rates": [0.08, 0.07, 0.06, 0.05, 0.04],
                "discount_rate": 0.09,
                "terminal_growth_rate": 0.03,
            },
        ],
        "limitations": [
            "Generic scenarios are placeholders, not an investment thesis.",
            "This simple FCF DCF is generally unsuitable for banks, insurers, and many REITs.",
            "Debt-like obligations, excess assets, dilution, taxes, and cyclicality require company-specific review.",
        ],
    }


def write_assumption_template(path: Path, metrics: dict[str, Any]) -> None:
    if not path.exists():
        atomic_write_json(path, generate_assumption_template(metrics))


def load_assumptions(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise ValuationError(f"Unable to load valuation assumptions: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValuationError("Valuation assumptions must be a JSON object")
    return payload


def calculate_dcf(
    starting_free_cash_flow: float,
    net_cash: float,
    diluted_shares: float,
    scenario: DCFScenario,
    market_price: float | None = None,
) -> DCFResult:
    if starting_free_cash_flow <= 0:
        raise ValuationError("DCF requires positive starting free cash flow")
    if diluted_shares <= 0:
        raise ValuationError("DCF requires positive diluted shares")
    if scenario.discount_rate <= scenario.terminal_growth_rate:
        raise ValuationError("Discount rate must exceed terminal growth rate")
    if not scenario.growth_rates:
        raise ValuationError("At least one explicit growth rate is required")

    projected: list[float] = []
    current = starting_free_cash_flow
    present_value = 0.0
    for year, growth in enumerate(scenario.growth_rates, start=1):
        current *= 1 + growth
        projected.append(current)
        present_value += current / ((1 + scenario.discount_rate) ** year)

    terminal_value = current * (1 + scenario.terminal_growth_rate) / (
        scenario.discount_rate - scenario.terminal_growth_rate
    )
    terminal_present_value = terminal_value / (
        (1 + scenario.discount_rate) ** len(scenario.growth_rates)
    )
    enterprise_value = present_value + terminal_present_value
    equity_value = enterprise_value + net_cash
    value_per_share = equity_value / diluted_shares
    implied_return = value_per_share / market_price - 1 if market_price and market_price > 0 else None
    return DCFResult(
        name=scenario.name,
        enterprise_value=enterprise_value,
        equity_value=equity_value,
        value_per_share=value_per_share,
        implied_return=implied_return,
        projected_free_cash_flow=tuple(projected),
    )


def run_valuation(assumptions: dict[str, Any]) -> list[dict[str, Any]]:
    if assumptions.get("human_reviewed") is not True:
        raise ValuationError(
            "Refusing to run unreviewed valuation assumptions. Set human_reviewed=true after documenting "
            "company-specific assumptions and their evidence."
        )
    required = ("starting_free_cash_flow", "net_cash", "diluted_shares", "scenarios")
    missing = [key for key in required if assumptions.get(key) is None]
    if missing:
        raise ValuationError("Missing valuation inputs: " + ", ".join(missing))

    market_price = assumptions.get("market_price")
    results: list[dict[str, Any]] = []
    for raw in assumptions.get("scenarios", []):
        scenario = DCFScenario(
            name=str(raw["name"]),
            growth_rates=tuple(float(value) for value in raw["growth_rates"]),
            discount_rate=float(raw["discount_rate"]),
            terminal_growth_rate=float(raw["terminal_growth_rate"]),
        )
        result = calculate_dcf(
            float(assumptions["starting_free_cash_flow"]),
            float(assumptions["net_cash"]),
            float(assumptions["diluted_shares"]),
            scenario,
            float(market_price) if market_price is not None else None,
        )
        results.append(asdict(result))
    return results
