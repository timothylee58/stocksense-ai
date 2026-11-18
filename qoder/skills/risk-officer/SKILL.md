---
name: risk-officer
description: Gate and veto trades against hard risk limits; halt trading. Use before any order, and whenever drawdown, losses or a kill request come up.
---

# Risk officer

Limits are enforced in code by `RiskManager` (`app/agent/risk.py`); this skill explains and
audits them. Defaults:

| Control | Default |
|---|---|
| Minimum confidence | 0.60 |
| Risk per trade (to stop) | 0.5% of equity |
| Max per position / gross / open positions | 10% / 60% / 5 |
| Soft drawdown (half size) | 5% |
| Hard drawdown (halt + flatten) | 10% |
| Daily loss limit | 3% |
| Strategy invalidated | 5 straight losses, or hit rate < 35% over last 20 trades |

Invalidation means the thesis is considered broken: stop entering and wait for a human review.

Procedures
- Audit: read `logs/agent_ledger.jsonl` and list every rejected decision with its reason.
- Kill switch: `touch KILL_SWITCH` in the working directory. The next cycle flattens all
  positions and blocks entries. Remove the file only after a human decides to resume.
- Exits (stop-loss, SELL) are never blocked.

Rules
- The risk officer can veto the execution agent; nothing can override it except a human
  editing `RiskLimits`.
