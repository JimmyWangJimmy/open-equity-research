from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from open_equity_research.analysis_engine import build_claims, build_findings
from open_equity_research.config import Settings
from open_equity_research.evidence import build_evidence, index_evidence
from open_equity_research.exceptions import ConfigurationError, ValuationError
from open_equity_research.facts import extract_all_metrics, serialize_metrics
from open_equity_research.filing_text import extract_10k_sections, html_to_text
from open_equity_research.models import Filing
from open_equity_research.orchestrator import ResearchOrchestrator
from open_equity_research.prompt_pack import run_command_agents
from open_equity_research.sec_client import SECClient
from open_equity_research.valuation import calculate_dcf, DCFScenario, run_valuation


FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def sample_10k_html() -> str:
    business = "The company designs products and sells services. " * 40
    risks = "Demand, competition, supply, regulation, and execution may affect results. " * 40
    mdna = "Management discusses revenue, margins, liquidity, and capital allocation. " * 40
    return f"""
    <html><body>
    <h1>ITEM 1. BUSINESS</h1><p>{business}</p>
    <h1>ITEM 1A. RISK FACTORS</h1><p>{risks}</p>
    <h1>ITEM 1B. UNRESOLVED STAFF COMMENTS</h1><p>None.</p>
    <h1>ITEM 7. MANAGEMENT'S DISCUSSION AND ANALYSIS</h1><p>{mdna}</p>
    <h1>ITEM 7A. QUANTITATIVE AND QUALITATIVE DISCLOSURES</h1><p>Market risk.</p>
    <h1>ITEM 8. FINANCIAL STATEMENTS</h1><p>Statements follow.</p>
    </body></html>
    """


class SettingsTests(unittest.TestCase):
    def test_network_validation_requires_declared_identity(self):
        with self.assertRaises(ConfigurationError):
            Settings(sec_user_agent="Your Name your@email.com").validate_network_access()
        Settings(sec_user_agent="Research Team contact@real-domain.test").validate_network_access()

    def test_rate_interval_cannot_exceed_sec_ceiling(self):
        with self.assertRaises(ConfigurationError):
            Settings(
                sec_user_agent="Research Team contact@real-domain.test",
                request_interval_seconds=0.05,
            ).validate_network_access()


class SECClientTests(unittest.TestCase):
    def test_resolve_ticker_supports_exchange_mapping(self):
        client = SECClient.__new__(SECClient)
        client._get_json = lambda url: load_fixture("tickers.json")
        result = client.resolve_ticker("exm")
        self.assertEqual(result["cik"], "0000320193")
        self.assertEqual(result["exchange"], "Nasdaq")


class FactsTests(unittest.TestCase):
    def setUp(self):
        self.metrics = extract_all_metrics(load_fixture("companyfacts.json"), "0000320193")

    def test_latest_filing_wins_for_same_period(self):
        revenue = self.metrics["revenue"]
        point_2023 = next(point for point in revenue.points if point.period_end == "2023-09-30")
        self.assertEqual(point_2023.value, 383_000_000_000)
        self.assertEqual(point_2023.filed, "2024-11-01")

    def test_derived_free_cash_flow_and_net_cash(self):
        latest_fcf = self.metrics["free_cash_flow"].points[-1]
        latest_net_cash = self.metrics["net_cash"].points[-1]
        self.assertAlmostEqual(latest_fcf.value, 108_600_000_000)
        self.assertAlmostEqual(latest_net_cash.value, -65_100_000_000)

    def test_findings_and_claims_reference_known_evidence(self):
        evidence = build_evidence(self.metrics)
        evidence_index = index_evidence(evidence)
        known = {item.evidence_id for item in evidence}
        findings = build_findings(self.metrics, evidence_index)
        claims = build_claims(self.metrics, evidence_index)
        self.assertTrue(findings)
        self.assertTrue(claims)
        for item in [*findings, *claims]:
            self.assertTrue(set(item.evidence_ids).issubset(known))


class FilingTextTests(unittest.TestCase):
    def test_extracts_longest_10k_sections(self):
        text = html_to_text(sample_10k_html())
        sections = extract_10k_sections(text)
        self.assertGreater(len(sections["item_1_business"]), 500)
        self.assertGreater(len(sections["item_1a_risk_factors"]), 500)
        self.assertGreater(len(sections["item_7_mdna"]), 500)


class ValuationTests(unittest.TestCase):
    def test_human_gate_blocks_generic_assumptions(self):
        with self.assertRaises(ValuationError):
            run_valuation({"human_reviewed": False})

    def test_dcf_produces_positive_per_share_value(self):
        result = calculate_dcf(
            100.0,
            20.0,
            10.0,
            DCFScenario("base", (0.05, 0.05, 0.04, 0.03, 0.03), 0.10, 0.025),
            market_price=100.0,
        )
        self.assertGreater(result.value_per_share, 0)
        self.assertIsNotNone(result.implied_return)


class FakeSECClient:
    def __init__(self, settings, force_refresh=False):
        self.settings = settings

    def resolve_ticker(self, ticker):
        return {"ticker": "EXM", "cik": "0000320193", "name": "Example Technology Inc.", "exchange": "Nasdaq"}

    def get_submissions(self, cik):
        return load_fixture("submissions.json")

    def get_companyfacts(self, cik):
        return load_fixture("companyfacts.json")

    def recent_filings(self, submissions, cik, forms=None, limit=20):
        return [
            Filing(
                accession_number="0000320193-24-000123",
                form="10-K",
                filing_date="2024-11-01",
                report_date="2024-09-28",
                primary_document="example-20240928.htm",
                source_url="https://www.sec.gov/Archives/edgar/data/320193/000032019324000123/example-20240928.htm",
            ),
            Filing(
                accession_number="0000320193-25-000010",
                form="10-Q",
                filing_date="2025-02-01",
                report_date="2024-12-28",
                primary_document="example-20241228.htm",
                source_url="https://www.sec.gov/Archives/edgar/data/320193/000032019325000010/example-20241228.htm",
            ),
        ]

    def get_document_text(self, url):
        return sample_10k_html()

    @staticmethod
    def snapshot_metadata():
        return {"source": "fixture", "fetched_at": "2026-06-20T00:00:00+00:00"}


class OrchestratorTests(unittest.TestCase):
    def test_end_to_end_workspace_and_command_agents(self):
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary) / "research"
            settings = Settings(
                workspace=workspace,
                sec_user_agent="Research Team contact@real-domain.test",
            )
            with patch("open_equity_research.orchestrator.SECClient", FakeSECClient):
                result = ResearchOrchestrator(settings).run("EXM")

            company_dir = workspace / "EXM"
            self.assertTrue(result["verification_ok"])
            self.assertTrue((company_dir / "report.md").exists())
            self.assertIn(
                "not investment advice",
                (company_dir / "report.md").read_text(encoding="utf-8").lower(),
            )
            assumptions = json.loads((company_dir / "valuation_assumptions.json").read_text())
            self.assertFalse(assumptions["human_reviewed"])

            mock_agent = Path(__file__).parents[1] / "examples" / "mock_agent.py"
            written = run_command_agents(
                company_dir / "agent_tasks",
                company_dir / "agent_outputs",
                f"{sys.executable} {mock_agent}",
                roles=["fundamental", "bear"],
            )
            self.assertEqual(len(written), 2)
            output = json.loads(written[0].read_text())
            self.assertFalse(output["trusted"])


if __name__ == "__main__":
    unittest.main()
