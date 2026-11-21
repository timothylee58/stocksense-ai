# Agent Rollout — StockSense Challenge

Paper/SIMULATE only. Gate 0–3 below are the only path to a challenge submission;
each gate names the proof that must exist before the next phase starts.

## Recon (2026-11-19)

| Check | Result |
| --- | --- |
| `mcp_list(server="moomoo")` | 104 tools, all `mcp__moomoo__*` |
| Runtime authorisation | ready (a frozen catalog in an older session was the only problem) |
| Settings-panel `list_tools` | `MCP_RUNTIME_AUTH_REQUIRED` — broken, but irrelevant: agent `mcp_call` works |
| US.AAPL quote (hosted gateway) | 352.45, prev close 351.91, data date 2026-11-18, `ret_code=0` |
| US.NVDA daily K-lines | 11-12 166.19 / 11-13 162.85 / 11-16 156.14 / 11-17 155.46 / 11-18 150.96 |
| SG.D05 realtime quote | `-9` realtime quote permission required (delayed only) |
| MY.1155 realtime quote | `-8` market not supported by this API |

Consequence: the universe is **US-only by entitlement**, not by choice. The Data
Steward encodes this as a hard rule (`deny_reason=ENTITLEMENT_DENIED` after ≤ 1
retry) rather than fabricating data.

The 104-tool inventory is pinned in
`stocksense-ai/backend/app/agents/moomoo_tools.json`; template load fails if any
allowlisted read tool is not in it. Live namespaces `trading_*`, `crypto_*`,
`grid_*`, and the live brokerage `account_*` namespace are denied by prefix for
every agent.

## Tool binding

| Logical need | Bound moomoo tool | Agents |
| --- | --- | --- |
| health | `quote_market_state`, `quote_trading_days` | supervisor, data_steward |
| universe check | `quote_stock_basicinfo` | supervisor |
| get_quote | `quote_stock_quote` | data_steward |
| get_klines | `quote_history_kline`, `quote_cur_kline` | data_steward, technical |
| get_news | `news_search` | news |
| account snapshot | `sim_trade_account_list`, `sim_trade_cash_info` | risk_reviewer, executor, auditor |
| positions | `sim_trade_position_list` | risk_reviewer, executor, auditor |
| open/history orders | `sim_trade_history_order_list` | supervisor, risk_reviewer, executor, auditor |
| place_paper_order | `sim_trade_input_order` | executor only |
| cancel_paper_order | `sim_trade_cancel_order` | executor only |

## Phases

| Phase | Scope | Entry gate | Exit gate |
| --- | --- | --- | --- |
| 0 · Contract | Seven templates, artifact schemas, pinned tool inventory, allowlist manifest | — | All backend tests pass; manifest sha256 pinned; A1–A16 repo proofs green |
| 1 · Shadow | 5 sessions, decisions logged, **zero orders** | Supervisor/handoff runtime implemented | A1–A4, A7, A8 pass; no order tool invoked in any shadow log |
| 2 · Paper | Risk gate live in the loop, Executor submits to SIMULATE | Phase 1 exit; Risk Reviewer runtime wired | A5, A6, A9, A12 pass |
| 3 · Challenge-ready | Full loop, reconciliation visible on the dashboard | Phase 2 exit; 10-session clean window | A10, A11 pass; dashboard shows decision ↔ broker reconciliation |

## Status today

- Phase 0: **complete** — templates, contracts, inventory, policy tests
  (`tests/test_agent_contracts.py`, `tests/test_agent_policy.py`).
- Phase 1 · Shadow: **implemented and exercised in the sandbox** —
  `AgentRuntime` runs the seven-role loop, logs every decision to the
  hash-chained journal, and places zero orders
  (`tests/test_agent_runtime.py::test_five_shadow_sessions_produce_zero_orders`).
  An unhealthy session aborts before any decision is made.
- Phase 2 · Paper: **implemented and exercised in the sandbox** — the risk gate
  runs in the loop; a filled LIMIT order is tagged with the decision id
  (`remark = stocksense:{decision_id}`) and a rerun of the same
  `(session_date, phase)` is reused with zero executions.
- Phase 3 · Challenge-ready: **first fresh agent order filled on SIMULATE** —
  the s1.0 ten-session window (2026-11-19) completed with a valid journal chain
  and 1/1 reconciliation, but was structurally trade-free: no loadable
  artefacts existed for the universe and `NEWS_API_KEY` is unset, so the
  ensemble capped at ≈0.42 against the 0.60 gate. Since then the eight-name
  universe has loader-native artefacts (`scripts/train_agent_models.py` writes
  `{TICKER}_xgb.pkl`, `{TICKER}_lstm.pt`, `{TICKER}_lstm_scaler.pkl`), and the
  gate/version moved to 0.30 / `s1.1` (see Strategy change log). The first s1.1
  paper session (`run-2026-11-19-paper-2904c7d8`) evaluated all eight names with
  real model components and submitted NVDA BUY 230 @ 150.96 — broker order
  `3117694`, remark `stocksense:e6d74b85-8cbc-47d5-8f1b-3ac5e87a5f52`. The
  order **filled in the 2026-11-19 regular session**: `status=4` (FILLED_ALL),
  `cum_qty=230`, `avg_fill_price=150.93`, and the SIMULATE position moved to
  NVDA 231 shares at avg cost 150.934. Reconciliation is `matched: 2`,
  `ledger_executions: 2`, `broker_orders: 2`, `breaks: []`, `ok: true`; journal
  chain OK. The ledger still records the execution as `submitted` — terminal
  fill state lives at the broker (`sim_trade_history_order_list`), the known
  ledger gap. The remaining nine session dates have not been re-run under
  `s1.1`; re-running them now would replay the same live quote under historic
  keys (nine near-duplicate NVDA buys), so the plan is one paper session per
  trading day through the 2026-11-30 deadline instead.
- 2026-11-20 s1.1 session: `run-2026-11-20-paper-ee416fa9` (`reused: false`)
  evaluated all eight names. NVDA cleared the 0.30 gate at 0.3326 (XGB 0.5052 /
  FinBERT 0.0 / LSTM 0.4) and was submitted as NVDA BUY 237 @ 139.09 LIMIT —
  broker order `3120535`, remark `stocksense:af4b93bf-0a55-440c-8537-8c053b9734e7`.
  It **filled in the 2026-11-20 regular session**: `status=4` (FILLED_ALL),
  `cum_qty=237`, `avg_fill_price=139.04`. TSLA also cleared the gate (0.4316)
  but its BUY 135 @ 369.125 was rejected at submission — moomoo refused the
  three-decimal limit price ("precision of Price in Place Order does not meet
  the specification"), so no TSLA order exists and the run halted with
  `failed execution 8681a489-9561-4045-8054-e76dabbb1e5a` in its audit.
  Reconciliation after the fill is `matched: 3`, `ledger_executions: 3`,
  `broker_orders: 3`, `breaks: []`, `ok: true`; journal chain OK. ClickHouse
  `decision_ledger` still falls back to JSONL (`UNKNOWN_TABLE`).

### Strategy change log

| Date | Change | Reason | Evidence |
| --- | --- | --- | --- |
| 2026-11-19 | `CHALLENGE_SIGNAL_THRESHOLD` 0.60 → 0.30; `CHALLENGE_STRATEGY_VERSION` `s1.0` → `s1.1` (owner decision) | With loader-native artefacts the 3-class XGB confidence peaks at ≈0.52 (HOLD dominates a ±1.5 % / 5 d label), so `0.5·xgb + 0.2·lstm` caps near 0.42 while FinBERT contributes 0 without a news key — 0.60 could never trade. | Shadow `run-2026-11-18-shadow-1f0fc3b0` (max net −0.417); paper `run-2026-11-19-paper-2904c7d8` (NVDA net +0.3326) |

### Running sessions

```bash
cd stocksense-ai/backend

# shadow: 5 sessions, decisions logged, no orders
.venv/bin/python -m app.agents.shadow --sessions 5

# paper: risk gate + Executor against SIMULATE (or demo broker when DEMO_MODE=true)
.venv/bin/python -m app.agents.shadow --sessions 1 --phase paper --symbols AAPL,NVDA

# via API (needs ADMIN_API_TOKEN when DEMO_MODE=false)
curl -s -X POST localhost:8000/api/agents/run \
     -H "X-Admin-Token: $ADMIN_API_TOKEN" \
     -H 'content-type: application/json' \
     -d '{"phase":"shadow"}'

curl -s localhost:8000/api/agents/runs            | jq '.runs[0]'
curl -s localhost:8000/api/agents/journal/verify  | jq
curl -s localhost:8000/api/agents/reconciliation  | jq
```

Decision path: health → dataset (60 s freshness) → XGBoost technical + FinBERT
sentiment + LSTM ensemble (weights 0.5 / 0.3 / 0.2, gate at
`CHALLENGE_SIGNAL_THRESHOLD` = 0.30 since s1.1) → sizing (0.5 % risk, stop =
max(4 % of price, 2 × ATR)) → risk gate → decision ledger → shadow skip or
paper order.

Sandbox reconciliation note: the demo broker is process-scoped (in-memory), so
in `DEMO_MODE` the reconciliation ignores ledger rows written before the current
process started. Restarting the backend therefore shows `matched: 0` until a
new paper session runs; that is expected, not a break.

## Hard stops

- Any live order tool (`trading_*`, `crypto_*`, `grid_*`) or live account read
  (`account_*`) is a policy violation: `policy.check_tool` returns
  `LIVE_TOOL_DENIED` before anything reaches the MCP server.
- No template may declare a write capability except the Executor, and only
  `place_paper_order` / `cancel_paper_order` exist as capabilities.
- A session halts (zero orders) on a failed health check, a stale quote, or an
  entitlement-denied symbol.
