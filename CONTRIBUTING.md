# Contributing

Contributions are welcome through focused pull requests.

1. Open an issue describing the research or engineering problem.
2. Keep financial claims evidence-backed and reproducible.
3. Add tests for parsers, formulas, state transitions, and safety gates.
4. Do not add broker execution, credential harvesting, undisclosed telemetry,
   or claims of guaranteed performance.
5. Run `make check` before opening a pull request.

For new financial metrics, document the exact SEC taxonomy concepts, units,
period selection logic, derivation formula, known issuer exceptions, and a
fixture covering at least one failure mode.
