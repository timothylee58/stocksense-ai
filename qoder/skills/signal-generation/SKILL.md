---
name: signal-generation
description: Report BUY/SELL/HOLD signals with confidence for the watchlist. Use each cycle; the trading loop generates them in-cycle.
---

# Signal generation

The ensemble lives in `app/ml/predictor.py` (`run_prediction`) and is wrapped by
`predictor_source` in `app/agent/loop.py`. Each cycle calls it for every ticker, so signals are
produced in-cycle, not by a separate step. Per ticker it yields: action, confidence (0-1), last
price and a suggested stop-loss.

1. Report which source produced each signal (`signal_source` on the prediction). There is one
   XGBoost model, `models/xgb_<TICKER>.json` (binary next-day), shared by the signal, `/api/explain`
   and `/api/backtest`. Without it the XGBoost leg is a rule-based RSI/MACD fallback
   (`signal_source: "rule_based"`) and the risk gate will not open positions on it. If a model is
   missing, say so. Train out-of-band, never inside a trading cycle:
   `DEMO_MODE=false python -m scripts.train_model --ticker <TICKER>` (live data; with `DEMO_MODE=true`
   or `--demo` it trains on synthetic data) or `POST /api/train/<TICKER>`.
2. Optional explanations: `GET /api/explain/<TICKER>` explains that same model, trained live
   (`DEMO_MODE=false`); a model trained with `DEMO_MODE=true` is synthetic. If the response has
   `"demo": true` (backend in demo mode), the drivers are synthetic: do not quote them.
3. Output a table: ticker, action, confidence, price, stop, signal source (xgb_binary or rule_based).
   Show SHAP drivers beside it; they explain the XGBoost leg only, not the LSTM leg of the ensemble.

Rules
- Always include `confidence`; never show raw logits.
- Demo-mode metrics are noise. Do not present them as performance.
- Models are pre-trained artefacts: never retrain inside a trading cycle.
