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

Invalidation latches: once triggered, new entries stay blocked (and this is saved in
`logs/risk_state.json` for the Moomoo broker) until a human reviews the thesis and resets it
(delete the state file, or call `RiskManager.reset_invalidation()`). A later winning exit does
not clear it. With the in-memory sim broker nothing persists across processes.

Sizing scope: in soft drawdown the risk and per-position terms are halved; a binding
gross-exposure or cash cap is not halved further.

Procedures
- Audit: read `logs/agent_ledger.jsonl` and list every rejected decision with its reason.
- Kill switch: from `stocksense-ai/backend` run `touch KILL_SWITCH`; from anywhere in the repo run
  `touch "$(git rev-parse --show-toplevel)/stocksense-ai/backend/KILL_SWITCH"` (the default path is anchored to the
  backend directory, so it works from any working directory). The next cycle flattens all
  positions and blocks entries. Remove the file only after a human decides to resume.
- Exits (stop-loss, SELL) are never blocked.

Rules
- The risk officer can veto the execution agent; nothing can override it except a human
  editing `RiskLimits`.
