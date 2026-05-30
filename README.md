# StockSense AI

> ML-powered stock anomaly detection + directional prediction — full ML lifecycle portfolio project

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://python.org)
[![Next.js](https://img.shields.io/badge/Next.js-15-black.svg)](https://nextjs.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688.svg)](https://fastapi.tiangolo.com)

---

## What It Does

StockSense AI ingests OHLCV data + financial news daily, runs a 3-stage ML pipeline to detect unusual market behaviour and predict next-day direction, then streams results to a real-time dashboard. Covers NASDAQ (NVDA, AAPL, MSFT…) and Bursa Malaysia (MAYBANK.KL, PBBANK.KL).

---

## ML Pipeline

```
Stage 1 — Isolation Forest (unsupervised)
  yfinance OHLCV + 25 technical features
    → anomaly_score [-1, 1]
    → is_anomaly (bool)

Stage 2 — XGBoost Classifier (supervised)
  Technical features + anomaly_score
  TimeSeriesSplit CV (no data leakage)
    → P(Up), P(Down)

Stage 3 — LR Meta-Learner (calibrated stacker)
  XGBoost probs + FinBERT sentiment + anomaly_score
  CalibratedClassifierCV (Platt scaling)
    → BUY / SELL / HOLD + confidence %
```

**Why this pipeline:**
- Isolation Forest needs no anomaly labels — handles flash crashes and earnings surprises natively
- XGBoost captures non-linear RSI × volume interactions; handles missing data
- LR stacker takes calibrated probabilities as input (linear assumption holds); coefficients are interpretable for the portfolio README
- FinBERT (ProsusAI/finbert) is pre-trained on 10-Ks and earnings calls — far more accurate than general BERT on financial headlines

### Evaluation Targets

| Metric | Target | Baseline |
|--------|--------|----------|
| Directional Accuracy | ≥ 60% | 50% (random walk) |
| ROC-AUC | ≥ 0.65 | 0.50 |
| Anomaly Precision | ≥ 70% | — |
| Inference (cached) | ≤ 50ms | — |
| Inference (cold) | ≤ 500ms | — |

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 15 (App Router) · TypeScript · Tailwind CSS · Framer Motion · Recharts |
| Backend | FastAPI (Python 3.11) · APScheduler · SSE streaming |
| ML | scikit-learn · XGBoost · PyTorch LSTM · HuggingFace FinBERT |
| Experiment Tracking | MLflow |
| Database | Supabase (PostgreSQL + pgvector) · RLS enabled |
| Cache | Redis (TTL 300s predictions, 900s OHLCV) |
| Auth | Supabase Auth + JWT |
| MCP Server | `@modelcontextprotocol/sdk` — 6 Claude Code tools |
| Frontend Deploy | Vercel (free) |
| Backend Deploy | Railway Starter (~RM23/month) |
| CI/CD | GitHub Actions (lint → test → deploy + weekly retraining) |
| Containers | Docker + Docker Compose |

---

## Architecture

```
┌──────────────────────────────────────────────┐
│  Next.js 15 (Vercel)                         │
│  /dashboard  /anomalies  /sentiment          │
│  SSE live stream · Framer Motion animations  │
└─────────────────┬────────────────────────────┘
                  │ REST + SSE
                  ▼
┌──────────────────────────────────────────────┐
│  FastAPI (Railway)                           │
│  /api/predict   /api/anomalies               │
│  /api/sentiment /api/stream  /api/train      │
│  APScheduler → daily 9AM MYT ingestion       │
└──────┬──────────┬──────────┬─────────────────┘
       │          │          │
  Supabase     Redis      MLflow
  PostgreSQL   TTL cache  Experiment tracking
  pgvector     Rate limit Model registry
  RLS + Auth
       │
  yfinance · NewsAPI · Reddit PRAW · moomoo
```

---

## Repository Structure

```
stocksense-ai/
├── stocksense-ai/
│   ├── backend/               # Canonical FastAPI backend
│   │   ├── app/
│   │   │   ├── main.py        # FastAPI app + APScheduler
│   │   │   ├── api/routes/    # predict, anomalies, sentiment, stream, train, health
│   │   │   ├── core/          # config, redis_client, database (Supabase)
│   │   │   ├── data/          # fetcher (yfinance + moomoo), 25 indicators
│   │   │   ├── ml/            # LSTM + XGBoost predictor (original ensemble)
│   │   │   └── services/      # 3-stage pipeline services + FinBERT + MLflow
│   │   ├── ml/
│   │   │   └── scripts/       # train.py, backfill.py, evaluate.py (CLI)
│   │   └── requirements.txt
│   ├── frontend/              # Next.js 15 App Router
│   │   └── src/
│   │       ├── app/
│   │       │   ├── page.tsx           # Landing (animated 3D neural net)
│   │       │   └── dashboard/
│   │       │       ├── page.tsx       # Main trading dashboard
│   │       │       ├── anomalies/     # Isolation Forest history
│   │       │       └── sentiment/     # FinBERT headlines feed
│   │       ├── hooks/         # useAnomalies, useSentiment, useSSE, usePrediction
│   │       ├── lib/           # api.ts, constants.ts, utils.ts
│   │       └── types/         # stock.ts — all shared TypeScript interfaces
│   ├── mcp-server/            # Claude Code MCP integration (6 tools)
│   │   └── src/
│   │       ├── index.ts       # stdio transport entry point
│   │       ├── client.ts      # HTTP client → FastAPI
│   │       └── tools/         # prediction, anomalies, retrain, sentiment, mlflow
│   └── supabase/
│       └── migrations/        # 001_predictions, 002_anomalies, 003_sentiment (RLS)
├── backend/                   # Legacy backend (kept for reference)
├── .github/
│   └── workflows/
│       ├── ci.yml             # Lint + type-check + test
│       ├── deploy.yml         # Vercel + Railway deploy on push to main
│       └── ml-retrain.yml     # Weekly Monday 9AM MYT (matrix: NVDA/MAYBANK/PBBANK)
├── docker-compose.yml         # Redis + FastAPI + MLflow + Next.js
├── .gitignore
├── LICENSE
└── README.md
```

---

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 20+
- Docker + Docker Compose (optional)
- Redis (or use Docker)

### Full Stack via Docker

```bash
git clone https://github.com/timothylee58/stocksense-ai.git
cd stocksense-ai

# Copy and fill env files
cp stocksense-ai/backend/.env.example stocksense-ai/backend/.env
cp stocksense-ai/frontend/.env.local.example stocksense-ai/frontend/.env.local

docker-compose up --build
```

Services: FastAPI `localhost:8000` · Next.js `localhost:3000` · MLflow `localhost:5000`

### Backend Only

```bash
cd stocksense-ai/backend
python -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### Frontend Only

```bash
cd stocksense-ai/frontend
npm install
npm run dev   # localhost:3000
```

---

## Environment Variables

### Backend (`stocksense-ai/backend/.env`)

```env
# Supabase
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_KEY=your-service-role-key

# Redis
REDIS_URL=redis://localhost:6379

# MLflow
MLFLOW_TRACKING_URI=http://localhost:5000

# News / Sentiment
NEWS_API_KEY=your-newsapi-key
REDDIT_CLIENT_ID=your-reddit-client-id
REDDIT_CLIENT_SECRET=your-reddit-secret

# Auth
SECRET_KEY=run-openssl-rand-hex-32

# ML
ANOMALY_CONTAMINATION=0.08
DIRECTION_THRESHOLD=0.60
DEFAULT_TICKERS=["NVDA","MAYBANK.KL","PBBANK.KL"]

# CORS
ALLOWED_ORIGINS=["http://localhost:3000","https://your-frontend.vercel.app"]
```

### Frontend (`stocksense-ai/frontend/.env.local`)

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_SUPABASE_URL=https://your-project.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=your-anon-key
```

---

## ML Training

```bash
cd stocksense-ai/backend

# Train all 3 stages for a ticker
python ml/scripts/train.py --ticker NVDA --days 365

# Backfill historical anomaly data into Supabase
python ml/scripts/backfill.py --ticker NVDA --days 365

# Walk-forward backtest evaluation
python ml/scripts/evaluate.py --ticker NVDA
```

Models saved to `./models/` as:
- `isolation_forest_NVDA.pkl` + `if_scaler_NVDA.pkl`
- `xgb_NVDA.json`
- `lr_meta_NVDA.pkl`

---

## Supabase Setup

Run migrations in order via Supabase SQL editor:

```bash
supabase/migrations/001_predictions.sql   # predictions table + RLS
supabase/migrations/002_anomalies.sql     # anomalies table + RLS
supabase/migrations/003_sentiment.sql     # sentiment_scores table + RLS
```

---

## MCP Server (Claude Code Integration)

```bash
cd stocksense-ai/mcp-server
npm install && npm run build
```

Add to Claude Code settings (`~/.claude/settings.json`):

```json
{
  "mcpServers": {
    "stocksense": {
      "command": "node",
      "args": ["path/to/stocksense-ai/mcp-server/dist/index.js"],
      "env": { "STOCKSENSE_API_URL": "http://localhost:8000" }
    }
  }
}
```

**Available tools:**

| Tool | Description |
|------|-------------|
| `get_prediction` | Full 3-stage ML prediction for a ticker |
| `get_anomalies` | Isolation Forest anomaly history (up to 365 days) |
| `get_sentiment` | FinBERT score + top headlines |
| `trigger_retrain` | Kick off full pipeline retraining → MLflow run_id |
| `compare_mlflow_runs` | Metric delta table between two runs |
| `get_feature_importance` | XGBoost SHAP feature importance |

---

## API Reference

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/predict/{ticker}` | LSTM+XGBoost ensemble prediction |
| `GET` | `/api/predict/batch/{tickers}` | Batch predictions (max 10, comma-separated) |
| `GET` | `/api/anomalies/{ticker}?days=30` | Isolation Forest anomaly history |
| `GET` | `/api/sentiment/{ticker}?hours=24` | FinBERT sentiment + headlines |
| `GET` | `/api/stream/{ticker}` | SSE live prediction stream (30s interval) |
| `POST` | `/api/train/{ticker}` | Trigger background model training |
| `GET` | `/api/train/status/{ticker}` | Poll training progress |
| `GET` | `/health` | Health check (Redis + Supabase status) |
| `WS` | `/ws/ticker/{ticker}` | WebSocket live price stream |

---

## CI/CD

| Workflow | Trigger | Steps |
|----------|---------|-------|
| `ci.yml` | Push / PR to `main` | ESLint · TypeScript · Ruff · Pytest · `next build` |
| `deploy.yml` | Push to `main` | Vercel (frontend) · Railway (backend) |
| `ml-retrain.yml` | Monday 1AM UTC (9AM MYT) | Train IF + XGBoost for NVDA, MAYBANK.KL, PBBANK.KL |

---

## Deployment

### Frontend → Vercel

```bash
cd stocksense-ai/frontend
npx vercel --prod
```

Set environment variables in Vercel dashboard: `NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`

### Backend → Railway

```bash
# Install Railway CLI
npm install -g @railway/cli
railway login

cd stocksense-ai/backend
railway up
```

Set secrets in Railway dashboard — all vars from `.env.example`.

### GitHub Actions Secrets Required

```
VERCEL_TOKEN, VERCEL_ORG_ID, VERCEL_PROJECT_ID
RAILWAY_TOKEN
SUPABASE_URL, SUPABASE_SERVICE_KEY
MLFLOW_TRACKING_URI, REDIS_URL
SECRET_KEY
```

---

## Budget

| Service | Cost |
|---------|------|
| Railway Starter (FastAPI + Redis + MLflow) | $5/mo ≈ RM23 |
| Supabase Free (500MB DB, pgvector, 50k auth users) | $0 |
| Vercel Hobby (frontend) | $0 |
| **Total** | **~RM23/month** |

---

## Markets Covered

| Market | Tickers |
|--------|---------|
| NASDAQ | NVDA, AAPL, MSFT, AMZN, GOOGL, META, TSLA, JPM, V, WMT, XOM, NFLX, AMD, LLY, BRK-B |
| Bursa Malaysia | MAYBANK.KL, PBBANK.KL |

Malaysian market context is intentional — station names, MYR currency, and Bursa data are features, not bugs.

---

## License

MIT — see [LICENSE](LICENSE)

---

## Author

**Timothy Lee** — Full-Stack / AI Engineer, Malaysia  
[GitHub](https://github.com/timothylee58) · timothylee_lyy@hotmail.com
