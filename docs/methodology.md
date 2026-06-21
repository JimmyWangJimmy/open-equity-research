# Methodology

## Evidence hierarchy

The current implementation prioritizes:

1. SEC filing documents and XBRL facts.
2. Deterministic transformations with an explicit formula.
3. Rule-based findings citing evidence IDs.
4. Human or model hypotheses that remain separate from source evidence.

A future source connector must preserve retrieval time, publication time, issuer, document identifier, exact location, license/usage constraints, and whether the source was available at the historical decision date.

## Annual-period selection

For duration concepts, the extractor accepts 10-K or 10-K/A facts with a period length of 270–430 days. For instant concepts, it accepts 10-K or 10-K/A facts without a start date. When the same fiscal period appears in multiple filings, the system prefers the higher-priority concept alias and then the latest filed observation, allowing restatements to supersede earlier values.

This rule is transparent but not universally correct. Transition reports, acquisitions, custom fiscal calendars, segment facts, and issuer-specific tags may require manual handling.

## Derived metrics

Current formulas include:

```text
free_cash_flow = operating_cash_flow - abs(capital_expenditures)
total_debt = current_debt + noncurrent_debt
net_cash = cash - total_debt
operating_margin = operating_income / revenue
net_margin = net_income / revenue
free_cash_flow_margin = free_cash_flow / revenue
cash_conversion = operating_cash_flow / net_income
```

Each derived evidence record names its formula. These are screening definitions, not claims that the issuer or an analyst would use the same definition.

## Claim discipline

A claim contains:

- stable claim ID;
- bounded wording;
- supportive/adverse/neutral stance;
- confidence level;
- evidence IDs;
- an explicit falsification condition.

Claims are phrased as observations about disclosed historical data. They do not infer future returns.

## Adversarial review

The Bear role is not a sentiment score. It should search for explanations under which an apparently attractive pattern is misleading—for example acquisition-driven growth, working-capital distortion, stock compensation, dilution, cyclicality, weak unit economics, refinancing dependence, or omitted debt-like obligations.

The Verifier checks whether the cited evidence supports the exact wording, period, unit, and causal strength of a claim.

## Valuation

The scenario DCF discounts explicitly forecast free cash flow and a Gordon-growth terminal value, then adds net cash and divides by diluted shares. It refuses to run unless `human_reviewed` is true.

The model does not determine a correct discount rate, terminal growth rate, reinvestment need, normalized margin, or cycle position. Those are research judgments and must be documented separately.

## Completion standard

A generated report is a research packet, not a completed investment decision. A serious decision process would additionally require verified industry evidence, competitive analysis, management/incentive review, point-in-time price and share data, valuation sensitivity, portfolio constraints, and an independent human challenge.
