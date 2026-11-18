---
name: performance-report
description: Generate the daily results report from the decision ledger. Use at end of day and when preparing the submission deck.
---

# Performance report

1. `python -m app.agent.report --ledger logs/agent_ledger.jsonl > report.md`
2. Add commentary: what worked, what failed and why, using the rejection reasons and risk
   events in the report. Quote real numbers only.
3. For the deck, include: strategy thesis, risk limits table, equity/drawdown, trade log,
   one failure and what changed because of it.

Rules
- Report paper results as paper results; they do not predict live returns.
- If there are fewer than ~20 closed trades, say the sample is too small to judge.
