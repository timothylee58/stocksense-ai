---
name: paper-execution
description: Run trading cycles against the Moomoo paper account. Use to execute approved signals; paper (SIMULATE) trading only.
---

# Paper execution

Prerequisites: moomoo OpenD running and logged in; `MOOMOO_HOST`/`MOOMOO_PORT` set.

1. Dry check with the in-memory broker:
   `python -m app.agent.loop --tickers NVDA --broker sim`
2. Paper account, one cycle:
   `python -m app.agent.loop --tickers NVDA,AAPL --broker moomoo --market US`
3. Continuous: add `--cycles N --interval 300`.
4. Confirm `logs/agent_ledger.jsonl` gained `decision`, `fill` and `equity` records.

Rules
- Only the simulated environment is used; there is no flag for live trading.
- If an order returns no fill, report it; never retry blindly or resize past risk limits.
- Orders block up to 20 seconds waiting for fills; unfilled remainders are cancelled.
- Stops are tracked locally in `logs/moomoo_stops.json`.
