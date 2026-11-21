# Round 2 + Round 3 — Allowlist and Proof

Paper/SIMULATE only. Nothing in this document, the tests, or the templates
authorizes a live order.

## Round 2 — machine-checkable allowlist

Source of truth: `stocksense-ai/backend/app/agents/templates/*.yaml`
(one file per agent). `app/agents/policy.py` compiles them into an allowlist and
refuses to import if any pattern can reach the live tool namespace, so the API
cannot boot with an unsafe policy.

| Rule | Behaviour |
| --- | --- |
| Live prefixes | `trading_*`, `crypto_*`, `grid_*`, `account_*` are always denied (deny wins over any allow rule); `account_*` is the live brokerage namespace |
| Default | Unknown agent → `UNKNOWN_AGENT`; unmatched tool → `NOT_IN_ALLOWLIST` |
| Patterns | Exact tool names or trailing `*` prefixes; bare `*` is rejected at load |
| Normalisation | `mcp__moomoo__` prefix stripped, names lower-cased before matching |
| Inventory | The 104-tool `mcp__moomoo__*` surface is pinned in `app/agents/moomoo_tools.json`; an allowlisted read tool not in the snapshot fails template load |

Endpoints:

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/agents` | Seven templates + tool bindings + manifest hash |
| GET | `/api/agents/policy` | Deny prefixes, per-agent allowlists and write bindings, SHA-256 of the canonical manifest |
| POST | `/api/agents/check-tool` | `{"agent_id","tool"}` → `{allowed, code}` — call before any moomoo MCP tool |
| GET | `/api/agents/{agent_id}` | Full template including artifact contract and system prompt |

Agent contracts (read tools / write capability):

| Agent | Read tools | Write | Output | Hooks |
| --- | --- | --- | --- | --- |
| Supervisor | `quote_market_state`, `quote_trading_days`, `quote_stock_basicinfo`, `sim_trade_history_order_list` | none | `RunRecord` | A4, A7 |
| Data Steward | `quote_stock_quote`, `quote_history_kline`, `quote_cur_kline`, `quote_market_state`, `quote_trading_days` | none | `Dataset` | A1, A2 |
| Technical Analyst | `quote_history_kline`, `quote_cur_kline` | none | `TechnicalSignal` | A7 |
| News Analyst | `news_search` | none | `SentimentSignal` | A3 |
| Risk Reviewer | `sim_trade_account_list`, `sim_trade_cash_info`, `sim_trade_position_list`, `sim_trade_history_order_list` | none | `RiskVerdict` | A5, A9 |
| Executor | `sim_trade_account_list`, `sim_trade_position_list`, `sim_trade_history_order_list` | `place_paper_order` → `sim_trade_input_order`; `cancel_paper_order` → `sim_trade_cancel_order` | `ExecutionRecord` | A6, A9 |
| Auditor | `sim_trade_account_list`, `sim_trade_position_list`, `sim_trade_history_order_list` | none (ClickHouse journal is internal) | `AuditReport` | A8, A10 |

Artifact schemas live in `app/agents/artifacts.py`; signals require `confidence`
in [0, 1] and provenance refs, and invalid states are forced (stale dataset →
`deny_reason`, zero headlines → neutral/0, insufficient bars → `insufficient_data`,
veto → non-empty reasons, filled execution → at least one fill).

Pin the `sha256` from `/api/agents/policy` in the agent harness; the hash changes
if any template's allowlist changes.

## Round 3 — failure table

| # | Failure mode | Detection / guard | Automated proof |
| --- | --- | --- | --- |
| 1 | Live environment configured | `verify_paper_guard` rejects any `trd_env != SIMULATE` before the SDK opens | A1 |
| 2 | Agent calls a live moomoo tool | Allowlist deny prefixes; check-tool endpoint | A2 |
| 3 | Market order submitted | Gate rejects when `require_limit_orders`; intent defaults to LIMIT | A3 |
| 4 | Buy sized on a missing or stale quote | `QUOTE_TIMESTAMP_MISSING` / `STALE_QUOTE`; sells exempt | A4 |
| 5 | Non-US symbol evaluated | `UNIVERSE_NOT_TRADABLE` on prefixes/suffixes | A5 |
| 6 | Oversized order, position, gross, cash use, daily loss, drawdown | Pure-function risk gate returns one reason code per breach | A6 |
| 7 | Kill switch ignored | Active switch blocks new buys, allows flattening sells | A7 |
| 8 | Ledger down but order still sent | Route fails closed when the ledger is unavailable | A8 |
| 9 | Duplicate submission on retry | Redis `NX` idempotency key, duplicate blocked | A9 |
| 10 | Timeout on non-idempotent `sim_trade_input_order` | Decision id stamped into order `text`; template requires read-before-retry | A10 |
| 11 | Account drift / client-supplied account id | `acc_id` resolved from settings at runtime; broker mismatch refused; intents carry no account field | A10, A11 |
| 12 | Shorting | Sell quantity above holding → `POSITION_NOT_HELD`; no short side exists | A12 |
| 13 | Overconfident or raw model output surfaced | Confidence clamped to [0, 1]; no logits field | A13 |
| 14 | Raw feature vectors exposed | `feature_snapshot` dropped from intents and ledger; SHAP returns contributions only | A14 |
| 15 | Runtime retraining triggered by inference | XGBoost/Isolation Forest fail closed with neutral output; never train or write artefacts | A15 |
| 16 | Demo sandbox accidentally calls the broker | Demo mode executes in-process; broker call raises | A16 |

## Acceptance matrix

| ID | Criterion | Test |
| --- | --- | --- |
| A1 | Paper/SIMULATE only; live env refused before SDK | `test_a01_paper_only_guard` |
| A2 | Live tools excluded for every agent | `test_a02_live_tools_are_excluded_for_every_agent` |
| A3 | LIMIT only | `test_a03_limit_orders_only` |
| A4 | Quote freshness for buys | `test_a04_quote_freshness` |
| A5 | US-only universe | `test_a05_us_only_universe` |
| A6 | Risk limits enforced | `test_a06_risk_limits` |
| A7 | Kill switch blocks buys, not sells | `test_a07_kill_switch_blocks_buys_not_sells` |
| A8 | Ledger outage fails closed | `test_a08_ledger_unavailable_fails_closed` |
| A9 | Duplicate order blocked | `test_a09_duplicate_order_is_blocked` |
| A10 | Non-idempotent order carries decision tag | `test_a10_broker_remark_stamps_decision_id` |
| A11 | Runtime account resolution; mismatch refused | `test_a11_account_resolved_at_runtime_and_mismatch_refused` |
| A12 | Shorting disabled | `test_a12_shorting_disabled` |
| A13 | Bounded confidence; no logits | `test_a13_confidence_bounded_and_no_logits` |
| A14 | No feature-vector exposure | `test_a14_no_feature_vectors_exposed` |
| A15 | Pre-trained artefacts only | `test_a15_pre_trained_artifacts_only` |
| A16 | Demo sandbox never calls the broker | `test_a16_demo_sandbox_never_calls_broker` |

Run everything:

```bash
cd stocksense-ai/backend
.venv/bin/python -m pytest -q
```

## Sandbox runbook

The sandbox is the local demo broker or the moomoo SIMULATE account — never a
live account.

```bash
cd stocksense-ai/backend
DEMO_MODE=true .venv/bin/python -m uvicorn app.main:app --port 8001

# allowlist
curl -s localhost:8001/api/agents | jq '.count, .manifest_sha256'
curl -s -X POST localhost:8001/api/agents/check-tool \
     -H 'content-type: application/json' \
     -d '{"agent_id":"executor","tool":"sim_trade_input_order"}'      # allowed
curl -s -X POST localhost:8001/api/agents/check-tool \
     -H 'content-type: application/json' \
     -d '{"agent_id":"executor","tool":"trading_order_place"}'       # LIVE_TOOL_DENIED

# dry-run decision through the gate
curl -s -X POST localhost:8001/api/trading/orders \
     -H 'content-type: application/json' \
     -d '{"ticker":"AAPL","side":"BUY","quantity":10,"price":100,
          "dry_run":true,"idempotency_key":"sandbox-1",
          "quote_ts":"<ISO-8601-UTC>"}'
```

Expected: allowlist check denies `trading_*`; a fresh-quote LIMIT intent is
approved with `execution.status = dry_run`; a stale or missing quote is rejected;
`GET /api/trading/account` reports `trd_env = SIMULATE`.

## Recon and hook map

The hosted moomoo gateway was probed on 2026-11-19: `mcp_list(server="moomoo")`
returns 104 tools; US.AAPL quoted 352.45 (`ret_code=0`); SG.D05 returns `-9`
(realtime quote permission required) and MY.1155 returns `-8` (market not
supported). The universe is therefore US-only **by entitlement**. Full evidence
and the 104-tool bindings are in [`ROLLOUT.md`](./ROLLOUT.md).

Canonical agent hooks (from the agent contract) mapped to repo proof:

| Hook | Meaning | Repo evidence | Status |
| --- | --- | --- | --- |
| A1 | Fresh, valid dataset (age ≤ 60 s, price > 0) | `test_agent_contracts.py::test_dataset_freshness_and_deny_rules`; `test_agent_runtime.py::test_stale_quote_is_denied` | runtime |
| A2 | SG/MY entitlement denial | deny_reason validator + Data Steward hard rule; gateway probes in ROLLOUT | schema only |
| A3 | Zero headlines → neutral, confidence 0 | `test_sentiment_zero_headlines_is_neutral` | schema |
| A4 | Idempotent session; abort on unhealthy | `test_agent_runtime.py` (`test_second_run_same_key_is_idempotent`, `test_health_failure_aborts_before_any_decision`) | runtime |
| A5 | Round-2 limits veto | `test_a06_risk_limits` (+ A03, A04, A05, A07, A12); runtime risk gate in `test_agent_runtime.py::test_paper_phase_executes_one_limit_order` | runtime |
| A6 | SIMULATE-only, verdict-bound execution | `test_a01_paper_only_guard`, `test_a16_demo_sandbox_never_calls_broker`; `test_agent_runtime.py::test_live_tools_are_refused_by_the_binding_guard` | runtime |
| A7 | Kill switch / halt | `test_a07_kill_switch_blocks_buys_not_sells`; `test_agent_runtime.py::test_kill_switch_blocks_new_buys` | runtime |
| A8 | Fail-closed ledger, append-only audit | `test_a08_ledger_unavailable_fails_closed`; `test_agent_runtime.py::test_ledger_outage_fails_closed`; `journal.verify()` endpoint | runtime (hash-chained journal + verify) |
| A9 | One order per key; intent-hash binding | `test_a09_duplicate_order_is_blocked`; `test_agent_runtime.py::test_duplicate_execution_is_blocked` | runtime + schema |
| A10 | Decision tag / hash chain | `test_a10_broker_remark_stamps_decision_id`; order remark == decision id in `test_agent_runtime.py`; `test_agent_runtime.py::test_journal_tamper_is_detected`; `/api/agents/reconciliation` | runtime |
| A11 | Account resolved at runtime; mismatch refused | `test_a11_account_resolved_at_runtime_and_mismatch_refused` | runtime |
| A12 | No shorting / no leverage | `test_a12_shorting_disabled`; `test_agent_runtime.py::test_signal_without_a_position_never_shorts` | runtime |

## Phase 1–3 runtime evidence (sandbox, 2026-11-19)

Run loop: `app/agents/runtime.py` — Supervisor health check → per-symbol
dataset (60 s freshness) → XGBoost technical + FinBERT sentiment + LSTM ensemble
(0.5 / 0.3 / 0.2, threshold `challenge_signal_threshold` = 0.30 since s1.1) → sizing
(0.5 % risk, stop = max(4 % of price, 2 × ATR)) → risk gate → decision ledger →
shadow: `execution_skipped`; paper: idempotent order (key = decision id) →
`sim_trade_input_order` binding requiring `trd_env = SIMULATE`.

| Check | Evidence |
| --- | --- |
| Shadow never trades | `test_five_shadow_sessions_produce_zero_orders`; sandbox run `2026-11-18-shadow-11c61cb4`: completed, 0 executions, journal chain OK |
| Unhealthy session aborts with zero orders | `test_health_failure_aborts_before_any_decision` |
| Paper order carries decision id | demo fill `DEMO-12C6FFB26495`, remark `stocksense:{decision_id}`, 26 GOOGL @ 282.44 |
| Duplicate execution blocked | rerun of the same `(session_date, phase)` returns `reused: true`, 0 executions |
| Ledger outage fails closed | `test_ledger_outage_fails_closed` → run status ABORTED |
| Journal integrity | `/api/agents/journal/verify` → `hash_chain_ok: true`; tamper detected in `test_journal_tamper_is_detected` |
| Reconciliation | `/api/agents/reconciliation` → `matched`, `missing_at_broker`, `untracked_at_ledger`; demo mode ignores ledger rows older than the in-process broker start |
| Dashboard | "Agent operations" panel on `/dashboard`: reconciliation + journal chips, runs table, break list |

Note: the rows above were sandbox sessions (demo broker). The SIMULATE window
that follows is the Phase 3 gate evidence.

### 10-session paper window (SIMULATE, 2026-11-19)

Ran `python -m app.agents.shadow --sessions 10 --phase paper` against the configured
moomoo SIMULATE account (account identifier omitted):

| Check | Result |
| --- | --- |
| Sessions | 10/10 `completed` (`2026-11-06` … `2026-11-19`), 8 names each, no halts |
| Decisions / executions | 0 / 0 — every name scored NEUTRAL at the 0.60 ensemble gate |
| Journal | `Journal().verify()` → `hash_chain_ok: true`, no breaks |
| Broker reconciliation | `matched: 1`, `ledger_executions: 1`, no missing/untracked orders (order `3116213`, NVDA, submitted 2026-11-18) |
| Broker portfolio | 3 positions (NVDA 1, PLTR 2, SMCI 20), equity ≈ $999k |

The zero-trade outcome was structural, not market-driven: at the time of the
window `models/` had no loader-native `{TICKER}_xgb.pkl` / `{TICKER}_lstm.pt`
artifacts (only a stale `xgb_NVDA.json` from another pipeline), and
`NEWS_API_KEY` is unset so FinBERT returns 0.0 with zero headlines. The
achievable net was therefore rule-based XGB (≤ 0.31 contribution) plus LSTM
(± 0.11), i.e. ≤ ~0.42 — below the 0.60 gate by construction.

Two follow-ups closed that gap:

1. `scripts/train_agent_models.py` now provisions loader-native artifacts for
   all eight universe names (`{TICKER}_xgb.pkl`, `{TICKER}_lstm.pt`,
   `{TICKER}_lstm_scaler.pkl`). The 3-class XGB confidence is empirically
   ≤ ~0.52, so a real model alone caps the net near 0.42.
2. With the owner's approval the gate moved to **0.30** under strategy version
   **s1.1** (see `ROLLOUT.md` → "Strategy change log"); weights are unchanged.

### s1.1 session window (SIMULATE)

One paper session per US trading day from 2026-11-19 to the 2026-11-30
deadline, all under strategy version s1.1 (gate 0.30, weights unchanged).
Each row records what the broker reported for that day's order plus the
read-only ledger ↔ broker reconciliation.

`run-2026-11-19-paper-2904c7d8` was the first s1.1 session. NVDA scored above
the gate and one LIMIT BUY 230 @ 150.96 was submitted as broker order
`3117694` with remark `stocksense:e6d74b85-8cbc-47d5-8f1b-3ac5e87a5f52` (A10).
It was created pre-market (`PRE_MARKET_BEGIN`, `status=2`) and filled in the
regular session.

| Date | Run | Execution | Fill | Reconciliation |
| --- | --- | --- | --- | --- |
| 2026-11-19 | `run-2026-11-19-paper-2904c7d8` | NVDA BUY 230 @ 150.96 LIMIT, order `3117694` | FILLED_ALL, `cum_qty` 230, `avg_fill_price` 150.93 | matched 2 / ledger_executions 2 / broker_orders 2 / breaks [] / ok |
| 2026-11-20 | `run-2026-11-20-paper-ee416fa9` | NVDA BUY 237 @ 139.09 LIMIT, order `3120535`; TSLA BUY 135 @ 369.125 rejected at submission on price precision (three decimals), no order | FILLED_ALL, `cum_qty` 237, `avg_fill_price` 139.04 | matched 3 / ledger_executions 3 / broker_orders 3 / breaks [] / ok |

The ledger row remains `submitted` for 2026-11-19 (the known gap — terminal
fill state is read from the broker). Journal chain OK. SIMULATE position after
the fill: NVDA 231 @ 150.934.


SDK compatibility fixes found while running the window:
`history_order_list_query` in moomoo 10.12.7208 accepts neither
`status_filter` nor `refresh_cache` (fallback to `order_list_query` works);
demo-mode fills (`DEMO-*` order ids) are excluded from real-mode
reconciliation; the CLI closes moomoo contexts on exit so it terminates.

## Open gaps vs PRD v0.2

Resolved since the first draft:

- Agent orchestration: `AgentRuntime` drives all seven roles (`runtime.py`),
  emitting run, decision, verdict, execution, audit and finish events.
- Intent-hash binding: the Executor requires the risk verdict for the intent and
  paper orders are idempotent on the decision id (Redis NX, 24 h).
- Hash-chained audit journal: append-only JSONL with `seq/prev_hash/hash` and
  artifact hashes; `verify()` detects tampering.
- Max concurrent positions: `risk_max_open_positions` = 5, enforced in the gate.
- Position sizing: 0.5 % risk per trade (`risk_per_trade_pct`) with an
  ATR-based stop, per PRD.

Still open (defaults intentionally unchanged, listed for an explicit decision):

- Gross exposure: PRD 30 %; deployed default 90 %.
- Daily loss stop: PRD 1.5 %; deployed default 3 %.
- Intraday-only session window: not enforced server-side.
- Fill reconciliation records broker `order_id`, not terminal `FILLED_ALL`;
  the broker order list is the authority in `/api/agents/reconciliation`.
- `sim_trade_input_order` has no server-side idempotency; the decision-id tag in
  the order `remark` plus read-before-retry is the mitigation.
- ClickHouse mirror of the journal: best-effort only; `agent_journal` DDL not
  created yet.

Changing any of these limits affects behaviour, so they are listed here for an
explicit decision before the defaults are moved.
