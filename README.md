# StockSense AI

> A seven-role AI trading agent for the **Moomoo × Qoder AI Trading Agent Challenge** — paper/SIMULATE only, with an executable pre-trade risk gate, a hash-chained audit journal, and decision-to-broker reconciliation.

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://python.org)
[![Next.js](https://img.shields.io/badge/Next.js-16-black.svg)](https://nextjs.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688.svg)](https://fastapi.tiangolo.com)

**Paper window:** 2026-11-19 → 2026-11-30 (submission deadline) · **Strategy:** `s1.1` · **Evidence through:** 2026-11-20

> **Safety.** Every order this repository can produce is a LIMIT order against a moomoo **SIMULATE** paper account. There is no code path to a live account: the environment guard rejects any `trd_env != SIMULATE` before the SDK is called, and the allowlist denies the `trading_*`, `crypto_*`, `grid_*` and live `account_*` namespaces before anything reaches a broker or MCP server.

---

## What It Does

StockSense AI turns a directional ML ensemble into a **gated, auditable paper-trading decision**:

```
moomoo market data (OpenD, or the local K-line snapshot)
  → 60 s freshness check → XGBoost + FinBERT + LSTM ensemble
  → position sizing (0.5 % equity risk, ATR stop)
  → deterministic risk gate  ──reject──▶ decision ledger (reason code)
  → decision ledger (append-only, before the broker call)
  → SIMULATE order tagged with the decision id
  → hash-chained journal → broker reconciliation → ops dashboard
```

Every tool call passes the allowlist in `app/agents/policy.py` first; the
runtime then executes it through an in-process binding layer
(`app/agents/bindings.py`) over the existing data layer and paper broker. The
104-tool moomoo MCP inventory is the reference the allowlist is compiled
against, so the same names can be bound to a hosted MCP session unchanged.

The submission is built for inspection: every accepted, rejected, dry-run, duplicate and failed decision is recorded, and the broker order list is reconciled back to the ledger.

---

## Why This Submission Is Auditable

| Guarantee | Implementation |
|-----------|----------------|
| Paper-only, fail-closed | `verify_paper_guard` refuses any non-SIMULATE environment and fails closed when the paper account id is missing (`tests/test_trade_guard.py`) |
| Live tools unreachable | The 104-tool `mcp__moomoo__*` surface is pinned in `app/agents/moomoo_tools.json`; live namespaces are denied by prefix (`app/agents/policy.py`) |
| Risk decisions are executable, not prose | Pure-function risk gate returns PASS/REJECT with one reason code per breach (`app/services/risk_gate.py`) |
| Ledger writes first | The order route fails closed if the decision ledger is unavailable (`test_a08_ledger_unavailable_fails_closed`) |
| One order per decision | Redis `NX` idempotency key (24 h); decision id is stamped into the broker order `remark` |
| Tamper-evident audit trail | Append-only JSONL journal with `seq/prev_hash/hash`; `GET /api/agents/journal/verify` → `hash_chain_ok` |
| Decision ↔ broker parity | `GET /api/agents/reconciliation` reports `matched`, `missing_at_broker`, `untracked_at_ledger` |

Full test-by-test proof: [`docs/PROOF.md`](docs/PROOF.md). Rollout gates, recon and strategy change log: [`docs/ROLLOUT.md`](docs/ROLLOUT.md).

---

## Agent Design

Seven roles share artifact contracts (`app/agents/artifacts.py`) and a single runtime (`app/agents/runtime.py`). The Supervisor runs health checks and triggers the pipeline; only the Executor holds a write capability, and only for paper orders.

| Agent | Reads | Write capability | Output |
|-------|-------|------------------|--------|
| Supervisor | `quote_market_state`, `quote_trading_days`, `quote_stock_basicinfo`, `sim_trade_history_order_list` | none | `RunRecord` |
| Data Steward | `quote_stock_quote`, `quote_history_kline`, `quote_cur_kline`, `quote_market_state`, `quote_trading_days` | none | `Dataset` |
| Technical Analyst | `quote_history_kline`, `quote_cur_kline` | none | `TechnicalSignal` |
| News Analyst | `news_search` | none | `SentimentSignal` |
| Risk Reviewer | `sim_trade_account_list`, `sim_trade_cash_info`, `sim_trade_position_list`, `sim_trade_history_order_list` | none | `RiskVerdict` |
| Executor | `sim_trade_account_list`, `sim_trade_position_list`, `sim_trade_history_order_list` | `place_paper_order` → `sim_trade_input_order`; `cancel_paper_order` → `sim_trade_cancel_order` | `ExecutionRecord` |
| Auditor | `sim_trade_account_list`, `sim_trade_position_list`, `sim_trade_history_order_list` | none | `AuditReport` |

Artifact schemas fail closed: stale datasets become `deny_reason`, a veto requires non-empty reasons, a filled execution requires at least one fill, and confidence is clamped to `[0, 1]` with no logits field.

No template may declare a write capability except the Executor, and `POST /api/agents/check-tool` lets any client ask the policy before calling a moomoo tool.

---

## Strategy

The runtime combines three components with fixed weights:

| Component | Weight | Notes |
|-----------|--------|-------|
| XGBoost | 0.5 | 3-class technical model, confidence empirically ≤ ~0.52 |
| FinBERT | 0.3 | 0.0 when `NEWS_API_KEY` is unset (zero headlines) |
| LSTM | 0.2 | 60-day sequence model |

- **Gate:** net signal must exceed `CHALLENGE_SIGNAL_THRESHOLD` (0.30 under `s1.1`; was 0.60 under `s1.0`).
- **Sizing:** 0.5 % of equity risked per trade; stop at `max(4 % of price, 2 × ATR)`.
- **Order type:** LIMIT only, long only, no shorting, US-only universe.
- **Universe:** `NVDA, AAPL, MSFT, AMD, GOOGL, META, AMZN, TSLA` (`CHALLENGE_UNIVERSE`).

The 0.60 → 0.30 change is documented with its reason and evidence in `docs/ROLLOUT.md` → *Strategy change log*.

---

## Risk Controls

| Limit | Default env var | Default |
|-------|-----------------|---------|
| Max position | `RISK_MAX_POSITION_PCT` | 25 % of equity |
| Max gross exposure | `RISK_MAX_GROSS_EXPOSURE_PCT` | 90 % |
| Max order notional | `RISK_MAX_ORDER_NOTIONAL` | 50,000 |
| Max daily loss | `RISK_MAX_DAILY_LOSS_PCT` | 3 % |
| Max drawdown | `RISK_MAX_DRAWDOWN_PCT` | 15 % |
| Min cash buffer | `RISK_MIN_CASH_BUFFER_PCT` | 10 % |
| Max open positions | `RISK_MAX_OPEN_POSITIONS` | 5 |
| Quote freshness (buys) | `RISK_MAX_QUOTE_AGE_S` | 60 s |
| Limit-orders-only | `RISK_LIMIT_ORDERS_ONLY` | true |
| US-only universe | `RISK_US_ONLY` | true |

Reason codes returned by the gate: `KILL_SWITCH_ACTIVE`, `MARKET_ORDER_FORBIDDEN`, `QUOTE_TIMESTAMP_MISSING`, `STALE_QUOTE`, `UNIVERSE_NOT_TRADABLE`, `ORDER_NOTIONAL_EXCEEDED`, `POSITION_LIMIT_EXCEEDED`, `GROSS_EXPOSURE_EXCEEDED`, `INSUFFICIENT_CASH`, `CASH_BUFFER_BREACHED`, `DAILY_LOSS_LIMIT_BREACHED`, `MAX_DRAWDOWN_BREACHED`, `MAX_OPEN_POSITIONS_EXCEEDED`, `POSITION_NOT_HELD`.

Policy codes: `UNKNOWN_AGENT`, `NOT_IN_ALLOWLIST`, `LIVE_TOOL_DENIED`.

The kill switch blocks new buys and still allows flattening sells. A session halts with zero orders on a failed health check, a stale quote, or an entitlement-denied symbol.

---

## Evidence So Far

The s1.1 window runs one paper session per US trading day; sessions run so far:

| Date | Run | Order | Fill | Reconciliation |
|------|-----|-------|------|----------------|
| 2026-11-19 | `run-2026-11-19-paper-2904c7d8` | NVDA BUY 230 @ 150.96 LIMIT (`3117694`) | FILLED_ALL, 230 @ 150.93 | matched 2 / ledger 2 / broker 2 / breaks [] / ok |
| 2026-11-20 | `run-2026-11-20-paper-ee416fa9` | NVDA BUY 237 @ 139.09 LIMIT (`3120535`); TSLA rejected at submission | FILLED_ALL, 237 @ 139.04 | matched 3 / ledger 3 / broker 3 / breaks [] / ok |

- Journal chain verified after both sessions (`/api/agents/journal/verify` → `hash_chain_ok: true`).
- Duplicate execution of the same `(session_date, phase)` returns `reused: true` with zero executions.
- Shadow runs place zero orders (`test_five_shadow_sessions_produce_zero_orders`).

### What failed, and why

- **The s1.0 ten-session window (run on 2026-11-19) was structurally trade-free.** No loader-native model artifacts existed for the universe and `NEWS_API_KEY` was unset, so the net ensemble capped near 0.42 against a 0.60 gate. Fixed by `scripts/train_agent_models.py` provisioning `{TICKER}_xgb.pkl`, `{TICKER}_lstm.pt` and `{TICKER}_lstm_scaler.pkl` for all eight names, plus the documented gate change to 0.30 / `s1.1`.
- **TSLA (2026-11-20) cleared the gate but was rejected at submission.** moomoo refused a three-decimal limit price (369.125); no order exists, and the run records a failed execution in its audit. The fix is price rounding to the market's tick size — tracked, not yet applied.
- **Ledger terminal state is a known gap.** The ledger records `submitted`; terminal fill state is read from `sim_trade_history_order_list` during reconciliation. See *Open gaps* in [`docs/PROOF.md`](docs/PROOF.md).

---

## Reproduce

### Prerequisites

- Python 3.11+ and `stocksense-ai/backend/.venv`
- Node.js 20+ (dashboard)
- moomoo OpenD gateway on `127.0.0.1:11111` (market data; the loop also runs against the in-process demo broker with `DEMO_MODE=true`)
- Redis (or Docker)

```bash
cd stocksense-ai/backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # set SECRET_KEY, ADMIN_API_TOKEN, MOOMOO_PAPER_ACCOUNT_ID
```

### Run the proofs

```bash
cd stocksense-ai/backend
.venv/bin/python -m pytest -q
```

### Full stack via Docker

```bash
cp stocksense-ai/backend/.env.example stocksense-ai/backend/.env
docker compose up --build   # Redis, Postgres, ClickHouse, backend :8000, frontend :3000
```

Docker covers the read-only surfaces. Paper sessions still need a local OpenD gateway (or `DEMO_MODE=true`) and the SIMULATE account id.

### Run agent sessions

```bash
cd stocksense-ai/backend

# shadow: decisions logged, zero order tools called
.venv/bin/python -m app.agents.shadow --sessions 5

# paper: risk gate + Executor against SIMULATE (or the demo broker when DEMO_MODE=true)
.venv/bin/python -m app.agents.shadow --sessions 1 --phase paper --symbols AAPL,NVDA
```

### Inspect the audit trail

```bash
curl -s localhost:8000/api/agents/runs            | jq '.runs[0]'
curl -s localhost:8000/api/agents/journal/verify  | jq
curl -s localhost:8000/api/agents/reconciliation  | jq
curl -s localhost:8000/api/agents/policy          | jq '.manifest_sha256'
```

Pin the policy `manifest_sha256` before a challenge run; it changes whenever a template allowlist changes.

### Dashboard

```bash
cd stocksense-ai/frontend
npm install && npm run dev    # localhost:3000
```

---

## Market Data

The fetch chain in `app/data/fetcher.py` is:

1. Redis (`dataset:{TICKER}:{period}y`, 15 min)
2. ClickHouse OHLCV, when fresh
3. **Local moomoo K-line snapshot** (`MOOMOO_KLINE_CACHE_FIRST=1` puts this ahead of OpenD)
4. Live moomoo OpenD K-lines
5. Local snapshot again (stale-guarded)
6. yfinance fallback

The hosted moomoo MCP gateway was probed on 2026-11-19: US quotes and daily K-lines return `ret_code=0`; `SG.D05` returns `-9` (realtime quote permission required) and `MY.1155` returns `-8` (market not supported). **The universe is US-only by entitlement**, which the Data Steward encodes as `deny_reason` instead of fabricating data.

Market-data views also cover Bursa Malaysia (`/dashboard/bursa`, yfinance symbols such as `MAYBANK.KL`), but the paper-trading universe stays US-only.

### Read-only K-line cache

`scripts/cache_moomoo_klines.py` pulls daily bars through the quote gateway only — it imports no trade context, so no order, cancel, transfer or subscription endpoint is reachable.

```bash
cd stocksense-ai/backend

# Pull via OpenD (US.NVDA, US.AAPL)
.venv/bin/python scripts/cache_moomoo_klines.py --tickers NVDA,AAPL --bars 370

# Or import raw output from the moomoo MCP quote_cur_kline tool
.venv/bin/python scripts/cache_moomoo_klines.py --from-json nvda.json --ticker NVDA
```

Snapshots are JSON with a schema version, `fetched_at` freshness guard and atomic writes under `data/cache/moomoo/` (gitignored).

| Env var | Default | Purpose |
|---------|---------|---------|
| `MOOMOO_KLINE_CACHE_DIR` | `backend/data/cache/moomoo` | Snapshot directory |
| `MOOMOO_KLINE_CACHE_MAX_AGE_H` | `72` | Ignore snapshots older than this |
| `MOOMOO_KLINE_CACHE_FIRST` | unset | `1`/`true` prefers snapshots over live OpenD |

---

## API Reference

### Agent operations (paper/SIMULATE)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/agents` | Seven templates, tool bindings, manifest SHA-256 |
| GET | `/api/agents/policy` | Deny prefixes and per-agent allowlists |
| GET | `/api/agents/{agent_id}` | Full template: contract, prompt, artifacts |
| POST | `/api/agents/check-tool` | `{"agent_id","tool"}` → `{allowed, code}` |
| POST | `/api/agents/run` | Run one shadow/paper session (`X-Admin-Token`) |
| GET | `/api/agents/runs` | Recent sessions from the journal |
| GET | `/api/agents/runs/{run_id}` | Full event stream |
| GET | `/api/agents/journal/verify` | Verify the hash chain |
| GET | `/api/agents/reconciliation` | Ledger executions vs broker paper orders |

### Trading and portfolio

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/trading/account` | Guard status + paper account snapshot |
| GET | `/api/trading/positions` | Open paper positions |
| GET | `/api/trading/decisions` | Decision/execution ledger (`limit`, `ticker`) |
| POST | `/api/trading/orders` | Risk-gated order submission (`dry_run` supported) |
| GET/POST | `/api/risk/kill-switch` | Read / trip the kill switch (POST needs `X-Admin-Token`) |
| GET | `/api/portfolio/summary` | P&L, exposure, ledger counts; records an equity snapshot |
| GET | `/api/portfolio/equity-curve` | Snapshot time series |
| GET | `/api/portfolio/rejected` | Rejected orders with reason codes |

### Prediction and market data

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/predict/{ticker}` | Ensemble prediction |
| GET | `/api/predict/batch/{tickers}` | Batch predictions (max 10) |
| GET | `/api/stocks/{ticker}/realtime` | Real-time or fallback quote |
| GET | `/api/stocks/{ticker}/ticks` | Tick-by-tick trades |
| GET | `/api/stocks/{ticker}/orderbook` | Level 2 depth |
| WS | `/ws/ticker/{ticker}` | Live price stream |
| GET | `/health` | Health check: Redis, ClickHouse, broker guard |

---

## Dashboard and Clients

- `/dashboard` — prediction charts, the **Agent operations** panel (runs, journal integrity, reconciliation, break list)
- `/dashboard/ops` — equity curve, positions, rejected-order log
- `/dashboard/anomalies`, `/dashboard/sentiment`, `/dashboard/bursa` — model and market views
- `mobile/` — Expo companion showing the same paper state; can submit a risk-gated paper order with a dry-run confirmation step

Charts use Recharts throughout.

---

## Environment Variables

### Backend (`stocksense-ai/backend/.env`)

```env
# Core
REDIS_URL=redis://localhost:6379
SECRET_KEY=run-openssl-rand-hex-32
ADMIN_API_TOKEN=run-openssl-rand-hex-32

# moomoo data
MOOMOO_HOST=127.0.0.1
MOOMOO_PORT=11111
MOOMOO_ENABLED=true
DEMO_MODE=false                 # true = in-process demo broker, never calls moomoo

# Paper trading — SIMULATE only
MOOMOO_TRADE_ENABLED=true
MOOMOO_TRD_ENV=SIMULATE
MOOMOO_PAPER_ACCOUNT_ID=from-challenge-dashboard
MOOMOO_TRD_MARKET=US
MOOMOO_SECURITY_FIRM=FUTUSECURITIES

# Challenge loop
CHALLENGE_UNIVERSE=["NVDA","AAPL","MSFT","AMD","GOOGL","META","AMZN","TSLA"]
CHALLENGE_STRATEGY_VERSION=s1.1
CHALLENGE_SIGNAL_THRESHOLD=0.30
RISK_PER_TRADE_PCT=0.005
RISK_MAX_OPEN_POSITIONS=5
AGENT_JOURNAL_JSONL=data/agent_journal.jsonl
DECISION_LEDGER_JSONL=data/decision_ledger.jsonl
PORTFOLIO_HISTORY_JSONL=data/portfolio_history.jsonl

# Risk limits
RISK_MAX_POSITION_PCT=0.25
RISK_MAX_GROSS_EXPOSURE_PCT=0.90
RISK_MAX_ORDER_NOTIONAL=50000
RISK_MAX_DAILY_LOSS_PCT=0.03
RISK_MAX_DRAWDOWN_PCT=0.15
RISK_MIN_CASH_BUFFER_PCT=0.10

# Read-only cloud demo
READ_ONLY_MODE=false

# News / sentiment (FinBERT contributes 0 without a key)
NEWS_API_KEY=

# Optional
SUPABASE_URL=
SUPABASE_SERVICE_KEY=
CLICKHOUSE_HOST=localhost
CLICKHOUSE_PORT=8123
ALLOWED_ORIGINS=["http://localhost:3000","http://localhost:8888"]
```

### Frontend (`stocksense-ai/frontend/.env.local`)

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_SUPABASE_URL=
NEXT_PUBLIC_SUPABASE_ANON_KEY=
```

---

## ML Pipeline

The original three-stage pipeline still powers the prediction routes and the dashboard; the agent loop consumes the ensemble components directly.

```
Stage 1 — Isolation Forest (unsupervised)
  OHLCV + 25 technical features → anomaly_score [-1, 1], is_anomaly

Stage 2 — XGBoost Classifier (supervised)
  Technical features + anomaly_score, TimeSeriesSplit CV → P(Up), P(Down)

Stage 3 — LR meta-learner (calibrated stacker)
  XGBoost probs + FinBERT sentiment + anomaly_score → BUY / SELL / HOLD + confidence
```

| Metric | Target | Baseline |
|--------|--------|----------|
| Directional accuracy | ≥ 60 % | 50 % |
| ROC-AUC | ≥ 0.65 | 0.50 |
| Anomaly precision | ≥ 70 % | — |
| Inference (cached) | ≤ 50 ms | — |
| Inference (cold) | ≤ 500 ms | — |

Models are pre-trained artifacts and are **never** retrained at runtime. Provision them with:

```bash
cd stocksense-ai/backend
.venv/bin/python ml/scripts/train.py --ticker NVDA --days 365      # 3-stage pipeline
.venv/bin/python scripts/train_agent_models.py                    # loader-native agent artifacts
.venv/bin/python scripts/validate_models.py                       # artifact check
```

Model artifacts: `isolation_forest_{T}.pkl`, `xgb_{T}.json`, `lr_meta_{T}.pkl` for the stacker, and `{T}_xgb.pkl`, `{T}_lstm.pt`, `{T}_lstm_scaler.pkl` for the agent loader.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Agent runtime | Python 3.11 · asyncio · artifact contracts · allowlist policy |
| Backend | FastAPI · APScheduler · SSE · Pydantic Settings |
| ML | scikit-learn · XGBoost · PyTorch LSTM · HuggingFace FinBERT |
| Data | moomoo OpenD · pinned MCP tool inventory · yfinance fallback · Redis · ClickHouse |
| Audit | Append-only JSONL journal (hash-chained) · decision ledger · broker reconciliation |
| Frontend | Next.js 16 (App Router) · TypeScript · Tailwind CSS · Recharts · Framer Motion |
| Mobile | Expo (React Native) |
| MCP server | `@modelcontextprotocol/sdk` — 5 read-only tools (`stocksense-mcp`) |
| Deploy | Vercel (frontend) · AWS App Runner via ECR (backend, read-only demo) |

### Read-only MCP server

```bash
cd stocksense-ai/mcp-server && npm install && npm run build
```

Tools: `get_prediction`, `get_anomalies`, `get_sentiment`, `compare_mlflow_runs`, `get_feature_importance`. None of them can place or cancel an order.

---

## Repository Layout

```
stocksense-ai/
├── stocksense-ai/
│   ├── backend/                    # Canonical FastAPI backend
│   │   ├── app/
│   │   │   ├── agents/             # 7 templates, policy, runtime, journal, reconciliation
│   │   │   ├── api/routes/         # predict, stocks, agents, agent_run, trading, portfolio, …
│   │   │   ├── core/               # config, redis, ClickHouse, stock codes
│   │   │   ├── data/               # fetcher, moomoo_fetcher, local K-line cache
│   │   │   ├── ml/                 # LSTM + XGBoost ensemble
│   │   │   └── services/           # risk gate, ledger, portfolio, scheduler
│   │   ├── scripts/                # train_agent_models, cache_moomoo_klines, ingest_news
│   │   ├── tests/                  # A1–A16 acceptance, policy, runtime, read-only tests
│   │   └── data/                   # journal, ledger, snapshots (gitignored)
│   ├── frontend/                   # Next.js 16 dashboard
│   ├── mcp-server/                 # Read-only MCP server (5 tools)
│   └── supabase/migrations/
├── mobile/                         # Expo paper-trading companion
├── docs/
│   ├── PROOF.md                    # Acceptance matrix A1–A16 + evidence
│   └── ROLLOUT.md                  # Gates, recon, strategy change log, hard stops
├── deploy/
│   └── apprunner.env.example
├── docker-compose.yml
└── README.md
```

---

## Deployment

The cloud deployment is a **read-only demo**. It serves predictions and dashboards but refuses `POST /api/trading/orders`, `POST /api/risk/kill-switch` and `POST /api/agents/run` with `READ_ONLY_MODE`. The container filesystem is ephemeral, so the audit chain resets on redeploy; challenge fills are produced by the local stack and recorded in [`docs/PROOF.md`](docs/PROOF.md).

### Frontend → Vercel

- Root Directory: `stocksense-ai/frontend` (the repo has several apps; do not group them)
- `NEXT_PUBLIC_API_URL` and `NEXT_PUBLIC_SUPABASE_*` are baked in at build time — redeploy after changes
- `next.config.ts` fails the build when `NEXT_PUBLIC_API_URL` is missing, so a bundle cannot silently call `localhost`

### Backend → AWS App Runner (via ECR)

1. Create the ECR repository `stocksense/backend` in `ap-southeast-1`.
2. Publish model artifacts to S3 (they are gitignored), then set `MODELS_S3_URI` and optionally `DATA_S3_URI`; `deploy.yml` syncs them into the build context and aborts if `NVDA_xgb.pkl` / `NVDA_lstm.pt` are missing.
3. Create the App Runner service on port `8000`, health check `/health`, 1 vCPU · 2 GB.
4. Copy env keys from [`deploy/apprunner.env.example`](./deploy/apprunner.env.example) and set `READ_ONLY_MODE=true`, `MOOMOO_ENABLED=false`, `MOOMOO_TRADE_ENABLED=false`, `CLICKHOUSE_ENABLED=false`, a fresh `SECRET_KEY`, a separate `ADMIN_API_TOKEN`, and `ALLOWED_ORIGINS` with the Vercel domain.

`deploy.yml` triggers on push to `master`; `ci.yml` runs lint, type-check, tests and a Docker build on every branch.

### Optional services

- **Supabase** — run `supabase/migrations/001_predictions.sql`, `002_anomalies.sql`, `003_sentiment.sql` in order (RLS enabled) for auth and prediction history. The paper-trading path does not require it.
- **MLflow** — `MLFLOW_TRACKING_URI` for experiment tracking; the 3-stage training script logs there when reachable.

---

## Budget

| Service | Cost |
|---------|------|
| Vercel Hobby (frontend) | $0 |
| AWS App Runner 1 vCPU · 2 GB | ~$35–50/month |
| Supabase Free | $0 |
| ECR storage (~500 MB) | ~$0.05/month |

Pause the App Runner service between demos to cut cost to near zero.

---

## Known Gaps

Tracked in [`docs/PROOF.md`](docs/PROOF.md) → *Open gaps vs PRD v0.2*:

- Ledger rows stay `submitted`; terminal fill state is reconciled from the broker.
- `sim_trade_input_order` has no server-side idempotency; the decision-id `remark` plus read-before-retry is the mitigation.
- Gross exposure (90 %), daily-loss stop (3 %) and intraday-only sessions differ from the PRD; they remain at their deployed defaults pending an explicit decision.
- ClickHouse ledger/journal mirror is best-effort; JSONL is authoritative.

---

## License

MIT — see [LICENSE](LICENSE)

---

## Author

**Timothy Lee** — Full-Stack / AI Engineer, Malaysia  
[GitHub](https://github.com/timothylee58) · timothylee_lyy@hotmail.com
