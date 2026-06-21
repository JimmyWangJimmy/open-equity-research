# Open Equity Research

Evidence-first, agent-ready U.S. equity research from public SEC filings.

Open Equity Research turns a ticker into an auditable research workspace containing SEC source snapshots, normalized annual financial metrics, a claim–evidence ledger, deterministic fundamental/bear/risk screens, best-effort 10-K section extraction, isolated LLM work packets, review issues, and a Markdown report.

It is deliberately **not** a trading bot. It has no broker integration, does not place orders, and does not generate a buy/sell rating. Valuation is blocked until a human explicitly reviews the assumptions.

[中文说明](docs/README.zh-CN.md)

## Why this project exists

Many “AI investing” demos optimize for a polished answer. This project optimizes for a traceable process:

```text
Ticker
  → SEC ticker/CIK resolution
  → submissions + XBRL company facts
  → raw source snapshots
  → normalized annual series
  → evidence ledger
  → deterministic findings and falsifiable claims
  → isolated Fundamental / Bear / Risk / Verifier tasks
  → open review issues
  → human-reviewed valuation
  → research report
```

The core rule is simple: a material claim should be traceable to evidence, and missing evidence must remain visible.

## Current status

Version `0.1.0` is an alpha-quality research MVP. It supports:

- SEC ticker-to-CIK resolution.
- SEC submissions and XBRL company-facts ingestion.
- Declared user agent, caching, retry logic, and conservative throttling.
- Five-year annual series for revenue, margins, income, cash flow, capex, cash, debt, equity, shares, R&D, and stock compensation when tags are available.
- Deterministic free-cash-flow, net-cash, margin, dilution, and cash-conversion screens.
- Raw evidence records with filing date, period, accession number, taxonomy concept, and SEC source URL.
- Best-effort extraction of Item 1, Item 1A, and Item 7 from the latest 10-K.
- Fundamental, Bear, Risk, and Verifier task packets for an external LLM command.
- A human gate before scenario DCF execution.
- Artifact integrity checks and multi-version CI.

It does not yet include point-in-time market data, earnings-call transcripts, news, industry datasets, portfolio accounting, backtesting, or automated trade execution.

## Installation

Python 3.11 or newer is required.

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
python -m pip install -e .
cp oer.example.toml oer.toml
```

Edit `oer.toml` and replace the SEC user agent with your identity and contact address:

```toml
[open_equity_research]
workspace = "research"
sec_user_agent = "Your Name your@email.com"
request_interval_seconds = 0.15
```

The SEC EDGAR APIs do not require an API key. Automated requests must identify the requester and comply with SEC fair-access rules. The default interval is about 6.7 requests per second, below the SEC's published ceiling of 10 requests per second.

## Quick start

```bash
# Build an evidence packet
equity-research research AAPL

# Inspect persisted state
equity-research status AAPL

# Verify evidence references and required artifacts
equity-research verify AAPL
```

The primary report is written to:

```text
research/AAPL/report.md
```

The complete workspace includes:

```text
research/AAPL/
├── company.json
├── task_spec.md
├── progress.json
├── directions_tried.json
├── iteration_log.jsonl
├── filings.jsonl
├── metrics.json
├── evidence.jsonl
├── findings.jsonl
├── claims.jsonl
├── review_issues.jsonl
├── valuation_assumptions.json
├── verification.json
├── report.md
├── agent_tasks/
│   ├── fundamental.json
│   ├── bear.json
│   ├── risk.json
│   └── verifier.json
└── source_snapshots/
    ├── submissions.json
    ├── companyfacts.json
    ├── latest_10k.html
    ├── latest_10k.txt
    └── 10k_sections.json
```

## Valuation workflow

The research command writes `valuation_assumptions.json` with generic placeholders and:

```json
"human_reviewed": false
```

The valuation command refuses to run until a person replaces the generic values, documents the thesis, and changes the field to `true`.

```bash
# After reviewing the assumptions file
equity-research value AAPL --price 210.00
```

The DCF is intentionally simple. It is usually inappropriate for banks and insurers, and may also be unsuitable for REITs, early-stage companies, cyclicals, or businesses with material off-balance-sheet obligations.

## Optional LLM agents

The core pipeline is deterministic and has no model dependency. `agent_tasks/` contains isolated JSON tasks for four roles. An external executable can be connected through a narrow stdin/stdout contract:

```bash
equity-research agents AAPL \
   --command "python examples/mock_agent.py" \
   --roles fundamental bear risk verifier
```

The executable receives one task JSON object on stdin and must emit one JSON object on stdout. It is invoked without a shell. Outputs are written to `agent_outputs/` and marked `trusted: false`.

A real model adapter should preserve these controls:

- Every material claim cites evidence IDs.
- Observations are separated from hypotheses.
- The Bear role searches for disconfirming evidence.
- The Verifier rejects unsupported claims and mismatched periods.
- LLM output never becomes source evidence by itself.
- No role places orders or emits personalized suitability advice.

## Research methodology

See [Methodology](docs/methodology.md) for metric selection, evidence lineage, claim rules, review gates, and known accounting limitations.

See [Architecture](docs/architecture.md) for state flow and module boundaries.

See [Roadmap](docs/roadmap.md) for the planned point-in-time market-data interface, filing-diff engine, transcript/news provenance, backtesting harness, and portfolio risk layer.

## SEC data policy

The implementation uses official public SEC endpoints:

- `data.sec.gov/submissions/CIK##########.json`
- `data.sec.gov/api/xbrl/companyfacts/CIK##########.json`
- SEC filing archive documents under `www.sec.gov/Archives/edgar/data/`

The software preserves source snapshots and filing links for auditability. Users remain responsible for complying with SEC access policies and for verifying every material conclusion against the original filing.

## Development

```bash
make check
```

The runtime has no third-party Python dependencies. Tests use the standard library and local fixtures; CI runs on Python 3.11 through 3.14.

## License and disclaimer

MIT licensed. Read [DISCLAIMER.md](DISCLAIMER.md) before use.

This project is educational research software, not investment advice. Investing can result in partial or total loss of capital.
