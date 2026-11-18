---
name: performance-report
description: Generate the daily results report from the decision ledger. Use at end of day and when preparing the submission deck.
---

# Performance report

1. `python -m app.agent.report --ledger logs/agent_ledger.jsonl --date YYYY-MM-DD > report.md`
   (without flags it reports the latest run; `--run-id` picks one run; `--date` reports every run on
   that UTC day for one broker, `--broker sim|moomoo`, defaulting to the broker of the latest event
   that day, so dry-run and paper-account equity are never mixed).
2. Add commentary: what worked, what failed and why, using the rejection reasons and risk
   events in the report. Quote real numbers only.
3. For the deck, take the report's metrics, then source the rest yourself: the risk limits table
   from the risk-officer skill (`RiskLimits` defaults), the trade log from the `fill` records in
   the ledger, and equity points from the `equity` records. Add one failure and what changed.

Rules
- Report paper results as paper results; they do not predict live returns.
- If there are fewer than ~20 closed trades, say the sample is too small to judge.
