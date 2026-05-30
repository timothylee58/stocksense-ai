# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Layout

```
stocksense-ai/               ← repo root
├── docker-compose.yml       ← orchestrates all 4 services
├── backend/                 ← standalone FastAPI service (separate from the monorepo backend)
│   ├── app/                 ← legacy/alternate backend (has db/ layer, no moomoo)
│   └── models/              ← saved ML artefacts
└── stocksense-ai/           ← primary monorepo
    ├── backend/             ← CANONICAL FastAPI backend (use this one)
    │   ├── app/
    │   │   ├── main.py
    │   │   ├── api/routes/  ← predict.py, train.py, stocks.py, websocket.py
    │   │   ├── core/        ← config.py, redis_client.py, stocks.py
    │   │   ├── data/        ← fetcher.py (yfinance + moomoo fallback), moomoo_fetcher.py
    │   │   └── ml/          ← predictor.py (ensemble), models/lstm.py, models/xgb_model.py
    │   └── requirements.txt
    └── frontend/            ← Next.js 15 App Router
        └── src/app/
            ├── page.tsx         ← landing page
            └── dashboard/page.tsx ← main UI (stock picker + charts + signals)
```

> The `docker-compose.yml` at root maps `backend:` → `./backend` and `frontend:` → `./stocksense-ai/frontend`. The canonical backend used in production is `stocksense-ai/backend/`.

## Common Commands

### Full Stack (Docker)

```bash
docker compose up           # boot Redis + Postgres + FastAPI + Next.js
docker compose up --build   # rebuild images after dependency changes
```

### Backend (FastAPI)

```bash
cd stocksense-ai/backend
pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000

# Run a single test (no test suite yet — use curl for smoke tests)
curl http://localhost:8000/health
curl http://localhost:8000/api/predict/AAPL
curl -X POST http://localhost:8000/api/train/AAPL
curl http://localhost:8000/api/train/status/AAPL
```

### Frontend (Next.js)

```bash
cd stocksense-ai/frontend
npm install
npm run dev          # dev server on :3000
npm run build        # production build (catches type errors)
npx next lint
```

## Architecture

### Prediction Pipeline

`GET /api/predict/{ticker}` → `predictor.run_prediction()`:

1. Check Redis cache (`prediction:{ticker}`, 5-min TTL)
2. `fetch_stock_data()` → moomoo historical K-lines **or** yfinance fallback → applies RSI-14, MACD-12/26/9, SMA-20/50, Bollinger Bands via `pandas-ta` (or manual fallback)
3. `predict_lstm()` → PyTorch LSTM (60-day sequence, 30-day forecast), loaded from `./models/{ticker}_lstm_latest.pt`
4. `predict_xgb()` → XGBoost classifier (BUY/SELL/HOLD), loaded from `./models/{ticker}_xgb_latest.json`
5. Ensemble: 60% LSTM direction + 40% XGBoost signal → `PredictionResult` dataclass → serialised to JSON

Training is triggered via `POST /api/train/{ticker}` and runs LSTM + XGBoost in parallel background tasks. Models are saved with versioned timestamps and aliased as `*_latest.*`.

### Data Sources

- **Primary**: moomoo API (requires moomoo OpenD gateway on `127.0.0.1:11111`)
- **Fallback**: yfinance (always available, 15-min delayed)
- Ticker format for moomoo: `US.AAPL`, `MY.MAYBANK`, `HK.00700`; plain tickers (e.g. `AAPL`) auto-prefix as US

### Caching (Redis)

| Key pattern | TTL | Content |
|---|---|---|
| `dataset:{ticker}:{period}y` | 15 min | OHLCV + indicators (DataFrame as dict) |
| `prediction:{ticker}` | 5 min | Full PredictionResult JSON |
| `realtime:{market}:{symbol}` | 10 s | moomoo real-time quote |
| `orderbook:{market}:{symbol}` | 5 s | Level 2 order book |

### API Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/api/predict/{ticker}` | Ensemble ML prediction |
| GET | `/api/predict/batch/{tickers}` | Comma-separated, max 10 |
| POST | `/api/train/{ticker}` | Kick off background training |
| POST | `/api/train/all/batch` | Train all 15 stocks |
| GET | `/api/train/status/{ticker}` | Poll training progress |
| GET | `/api/stocks/{ticker}/realtime` | moomoo real-time quote |
| GET | `/api/stocks/{ticker}/ticks` | Tick-by-tick trades |
| GET | `/api/stocks/{ticker}/orderbook` | Level 2 depth |
| WS | `/ws/ticker/{ticker}` | Live price stream (60s / 300s off-hours) |

### Frontend

- `src/app/page.tsx` — landing page (pure React, no data fetching; animated 3D neural net built with raw SVG math)
- `src/app/dashboard/page.tsx` — main trading dashboard; fetches `NEXT_PUBLIC_API_URL` (defaults to `http://localhost:8000`); uses Recharts for price/forecast charts
- `src/types/stock.ts` — shared `PredictionResponse` and `StockInfo` TypeScript types; keep in sync with the `PredictionResult` dataclass in `predictor.py`

## Environment Variables

Backend reads from `stocksense-ai/backend/.env`:

```env
REDIS_URL=redis://localhost:6379
SECRET_KEY=<openssl rand -hex 32>
MOOMOO_HOST=127.0.0.1
MOOMOO_PORT=11111
MOOMOO_ENABLED=true
```

Frontend reads from `stocksense-ai/frontend/.env.local`:

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
```

## moomoo Integration

moomoo OpenD must be running locally before the backend starts if `MOOMOO_ENABLED=true`. If it is absent, the system falls back to yfinance silently. See `MOOMOO_INTEGRATION.md` for setup details.

The `MoomooClient` connection state is checked via `MoomooClient.is_connected()` before every call; yfinance is used if disconnected.

## ML Model Notes

- LSTM: `seq_len=60` days input window, `forecast_days=30` output, `hidden=64`, `layers=2`, `epochs=80`
- Models stored in `./models/` relative to the working directory when uvicorn is started
- `run_in_executor` is used for both LSTM and XGBoost inference to avoid blocking the async event loop
- If no saved model artefact exists, `predict_lstm` / `predict_xgb` fall back to rule-based signals

---

## StockSense AI — Domain Rules

**Target**: binary next-trading-day direction prediction (UP / DOWN) for NVIDIA and other stocks.

### Service Layer (planned / in-progress)

| File | Responsibility |
|---|---|
| `backend/app/services/finbert_service.py` | HuggingFace FinBERT inference (`ProsusAI/finbert`) |
| `backend/app/services/xgboost_service.py` | Tabular feature prediction |
| `backend/app/services/lstm_service.py` | Sequence model |
| `backend/app/services/ensemble_service.py` | Weighted ensemble combiner |
| `app/(dashboard)/stocksense/page.tsx` | Prediction UI + charts |

### Feature Pipeline Order

```
raw OHLCV → technical indicators → FinBERT sentiment → ensemble
```

Technical indicators: RSI (14), MACD (12/26/9), Bollinger Bands (20/2), EMA (9, 21).

### Ensemble Weights

| Model | Weight |
|---|---|
| XGBoost | 0.5 |
| FinBERT | 0.3 |
| LSTM | 0.2 |

Document any weight changes with a comment and the reason.

### Redis Cache

Key pattern: `stocksense:prediction:{ticker}:{date}` — TTL **3600 s** (daily market data, not intraday).

### Invariants

- **FinBERT**: load `ProsusAI/finbert` once at startup and cache in memory — never reload per request.
- **LSTM sequence length**: 60 trading days — do not shorten without retraining the saved artefact.
- **Confidence score**: every prediction response must include a `confidence` field (0.0–1.0). Never display raw logits in the UI.
- **Numeric precision**: use `float64` / Python `Decimal` for all financial calculations — never `float32`.
- **Currency**: all financial figures displayed in USD — no conversion.
- **Data source**: Yahoo Finance via `yfinance` — respect rate limits; cache raw OHLCV in Redis.
- **Charts**: Recharts for candlestick + prediction overlay — do not switch charting libraries.
- **Models are pre-trained artefacts** — never retrain at runtime.
- **API surface**: never expose model weights or raw feature vectors via any endpoint.

---

## Obsidian + Claude Code — Memory Strategy

Load context on demand using `@file` references in the Claude Code prompt — do not auto-inject daily notes or entire vault content into every session.

```
# Good — load exactly what's needed
@vault/projects/stocksense/architecture.md
@vault/projects/stocksense/api-contracts.md

# Bad — bloats every session
@vault/daily/2026-04-13.md   ← irrelevant context burns tokens
```

When a session requires domain knowledge stored in Obsidian, reference the specific note explicitly. Treat Obsidian notes as on-demand documentation, not ambient context.
