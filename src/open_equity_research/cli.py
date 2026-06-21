from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .config import Settings, write_example_config
from .exceptions import OpenEquityResearchError
from .io_utils import atomic_write_json, load_json, load_jsonl
from .models import Filing
from .orchestrator import ResearchOrchestrator
from .prompt_pack import run_command_agents
from .report import generate_report
from .valuation import load_assumptions, run_valuation
from .verify import verify_company_workspace


def _settings(args: argparse.Namespace) -> Settings:
    return Settings.load(
        args.config,
        workspace=args.workspace,
        sec_user_agent=args.sec_user_agent,
    )


def _company_dir(settings: Settings, ticker: str) -> Path:
    return settings.workspace / ticker.strip().upper()


def _print_json(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def _regenerate_report(company_dir: Path, valuation_results: list[dict[str, Any]] | None = None) -> None:
    company = load_json(company_dir / "company.json", {}) or {}
    metrics = load_json(company_dir / "metrics.json", {}) or {}
    findings = load_jsonl(company_dir / "findings.jsonl")
    claims = load_jsonl(company_dir / "claims.jsonl")
    issues = load_jsonl(company_dir / "review_issues.jsonl")
    filing_rows = load_jsonl(company_dir / "filings.jsonl")
    filings = [Filing(**row) for row in filing_rows]
    sections = load_json(company_dir / "source_snapshots" / "10k_sections.json", {}) or {}
    generate_report(
        company_dir / "report.md",
        company=company,
        filings=filings,
        metrics=metrics,
        findings=findings,
        claims=claims,
        issues=issues,
        narrative_sections=sections,
        valuation_results=valuation_results,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="equity-research",
        description="Evidence-first, agent-ready U.S. equity research from public SEC filings.",
    )
    parser.add_argument("--config", type=Path, default=Path("oer.toml"), help="Path to TOML configuration")
    parser.add_argument("--workspace", type=Path, help="Override research workspace")
    parser.add_argument("--sec-user-agent", help="Override SEC declared user agent")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Write an example configuration")
    init_parser.add_argument("--output", type=Path, default=Path("oer.toml"))
    init_parser.add_argument("--force", action="store_true")

    research_parser = subparsers.add_parser("research", help="Build or refresh a company research packet")
    research_parser.add_argument("ticker")
    research_parser.add_argument("--force-refresh", action="store_true")

    status_parser = subparsers.add_parser("status", help="Show persisted research state")
    status_parser.add_argument("ticker")

    verify_parser = subparsers.add_parser("verify", help="Verify artifact integrity and evidence references")
    verify_parser.add_argument("ticker")

    value_parser = subparsers.add_parser("value", help="Run a human-reviewed scenario DCF")
    value_parser.add_argument("ticker")
    value_parser.add_argument("--assumptions", type=Path)
    value_parser.add_argument("--price", type=float, help="Override market_price in the assumptions file")

    agent_parser = subparsers.add_parser("agents", help="Run isolated agent tasks through a local command")
    agent_parser.add_argument("ticker")
    agent_parser.add_argument(
        "--command",
        dest="agent_command",
        required=True,
        help="Executable receiving task JSON on stdin and emitting one JSON object on stdout",
    )
    agent_parser.add_argument(
        "--roles",
        nargs="+",
        choices=("fundamental", "bear", "risk", "verifier"),
    )
    agent_parser.add_argument("--timeout", type=int, default=300)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "init":
            if args.output.exists() and not args.force:
                parser.error(f"{args.output} already exists; use --force to replace it")
            write_example_config(args.output)
            print(f"Wrote {args.output}")
            return 0

        settings = _settings(args)
        company_dir = _company_dir(settings, args.ticker)

        if args.command == "research":
            result = ResearchOrchestrator(settings).run(
                args.ticker, force_refresh=args.force_refresh
            )
            _print_json(result)
            return 0

        if args.command == "status":
            progress = load_json(company_dir / "progress.json")
            if progress is None:
                raise OpenEquityResearchError(f"No research state exists for {args.ticker.upper()}")
            _print_json(progress)
            return 0

        if args.command == "verify":
            result = verify_company_workspace(company_dir)
            _print_json(result)
            return 0 if result["ok"] else 1

        if args.command == "value":
            assumptions_path = args.assumptions or company_dir / "valuation_assumptions.json"
            assumptions = load_assumptions(assumptions_path)
            if args.price is not None:
                assumptions["market_price"] = args.price
            results = run_valuation(assumptions)
            atomic_write_json(company_dir / "valuation_results.json", results)
            _regenerate_report(company_dir, valuation_results=results)
            _print_json(results)
            return 0

        if args.command == "agents":
            written = run_command_agents(
                company_dir / "agent_tasks",
                company_dir / "agent_outputs",
                args.agent_command,
                roles=args.roles,
                timeout_seconds=args.timeout,
            )
            _print_json([str(path) for path in written])
            return 0

        parser.error("Unknown command")
    except OpenEquityResearchError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except (OSError, ValueError, TimeoutError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
