---
name: signal-generation
description: Produce BUY/SELL/HOLD signals with confidence for the watchlist. Use each cycle after market-research.
---

# Signal generation

The ensemble lives in `app/ml/predictor.py` (`run_prediction`) and is wrapped by
`predictor_source` in `app/agent/loop.py`. It yields, per ticker: action, confidence (0-1),
last price and a suggested stop-loss.

1. Check the model the predictor actually loads: `models/<TICKER>_xgb.pkl` (and
   `models/<TICKER>_lstm.pt`). If missing, create it with `POST /api/train/<TICKER>`.
   Without the pickle, `predict_xgb` silently falls back to a rule-based RSI/MACD signal, so
   report which source produced each signal.
   Note: `scripts/train_model.py` writes a *different* model (`models/xgb_<TICKER>.json`,
   binary next-day) used only by `/api/explain` and `/api/backtest`. Training it does not
   change the trading signal until the two pipelines are unified (see docs/challenge/PRD.md s.8).
2. For explanations, call `GET /api/explain/<TICKER>` (SHAP contributions) and quote the top 3.
   If the response has `"demo": true` (backend in demo mode), the drivers are synthetic: do not
   quote them; say explanations are unavailable.
3. Output a table: ticker, action, confidence, price, stop, top drivers.

Rules
- Always include `confidence`; never show raw logits.
- Demo-mode metrics are noise. Do not present them as performance.
- Models are pre-trained artefacts: never retrain inside a trading cycle.
