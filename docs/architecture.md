# Architecture

## Design principles

1. Persist state outside model context.
2. Preserve raw source snapshots before transformation.
3. Keep raw facts, derived metrics, claims, and model output in separate layers.
4. Require evidence IDs for material claims.
5. Run an explicit adversarial role rather than only a thesis writer.
6. Treat all model output as untrusted until verified.
7. Keep trading and irreversible financial actions outside the system.

## Modules

```text
config.py           local settings and SEC access validation
sec_client.py       SEC requests, identity headers, throttling, retries, cache
filing_text.py      HTML-to-text and best-effort 10-K section extraction
facts.py            XBRL concept aliases, annual-period selection, derived metrics
evidence.py         deterministic evidence IDs and provenance records
analysis_engine.py  fundamental, bear, risk screens and falsifiable claims
valuation.py        explicit scenario DCF with a mandatory human gate
prompt_pack.py      isolated role tasks and command-adapter runtime
orchestrator.py     state transitions and artifact production
verify.py           integrity and evidence-reference checks
report.py           human-readable research packet
cli.py              command-line interface
```

## State machine

```text
running
  → sec_data_collected
  → latest_10k_parsed (when available)
  → metrics_normalized
  → claim_evidence_graph_built
  → agent_tasks_exported
  → report_generated
  → research_packet_ready
```

Failures are written to `progress.json` and `iteration_log.jsonl`. Re-running the same ticker compares the current evidence count with the prior run. No new evidence increments `stale_count`; this is a simple hook for future pivot policies.

## Trust boundaries

- SEC documents are primary-source inputs, not automatically correct economic interpretations.
- XBRL normalization is deterministic but may select the wrong tag for an issuer.
- Derived metrics are reproducible formulas, not GAAP facts.
- LLM output is stored outside the evidence ledger and marked untrusted.
- Valuation requires human approval.
- A trade decision is never represented as an automated stage.
