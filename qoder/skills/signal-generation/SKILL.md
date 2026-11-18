---
name: signal-generation
description: Report BUY/SELL/HOLD signals with confidence for the watchlist. Use each cycle; the trading loop generates them in-cycle.
---

# Signal generation

The ensemble lives in `app/ml/predictor.py` (`run_prediction`) and is wrapped by
`predictor_source` in `app/agent/loop.py`. Each cycle calls it for every ticker, so signals are
produced in-cycle, not by a separate step. Per ticker it yields: action, confidence (0-1), last
price and a suggested stop-loss.

1. Report which source produced each signal. The predictor loads `models/<TICKER>_xgb.pkl` (and
   `models/<TICKER>_lstm.pt`); without the pickle, `predict_xgb` silently falls back to a
   rule-based RSI/MACD signal. If a model is missing, say so and carry on with the fallback.
   Train out-of-band, never inside a trading cycle: `POST /api/train/<TICKER>` runs in the
   background and will not produce a model for the current cycle.
2. Optional explanations: `GET /api/explain/<TICKER>` needs a different model,
   `models/xgb_<TICKER>.json`, created offline by `python -m scripts.train_model --ticker <TICKER>`
   (live data, not `--demo`). Without it the endpoint returns "No XGBoost model". If the response has
   `"demo": true`, the drivers are synthetic: do not quote them.
3. Output a table: ticker, action, confidence, price, stop, signal source (pkl or rule-based).
   Show SHAP drivers separately, labelled as the explain model's drivers, not the signal's, until
   the two pipelines are unified (docs/challenge/PRD.md s.8).

Rules
- Always include `confidence`; never show raw logits.
- Demo-mode metrics are noise. Do not present them as performance.
- Models are pre-trained artefacts: never retrain inside a trading cycle.
