---
name: signal-generation
description: Produce BUY/SELL/HOLD signals with confidence for the watchlist. Use each cycle after market-research.
---

# Signal generation

The ensemble lives in `app/ml/predictor.py` (`run_prediction`) and is wrapped by
`predictor_source` in `app/agent/loop.py`. It yields, per ticker: action, confidence (0-1),
last price and a suggested stop-loss.

1. Check a trained model exists: `models/xgb_<TICKER>.json`. If not, run
   `python -m scripts.train_model --ticker <TICKER>` (live data, not `--demo`).
2. For explanations, call `GET /api/explain/<TICKER>` (SHAP contributions) and quote the top 3.
3. Output a table: ticker, action, confidence, price, stop, top drivers.

Rules
- Always include `confidence`; never show raw logits.
- Demo-mode metrics are noise. Do not present them as performance.
- Models are pre-trained artefacts: never retrain inside a trading cycle.
