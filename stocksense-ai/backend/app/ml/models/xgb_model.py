"""
XGBoost direction signal for the ensemble.

There is ONE XGBoost model: the binary next-day (UP/DOWN) classifier saved as
`models/xgb_<TICKER>.json` (by `scripts/train_model.py` or `POST /api/train`). The trading
signal, `/api/explain` (SHAP) and `/api/backtest` all use it, so what is explained and
backtested is what trades. With no trained model we fall back to a rule-based RSI/MACD
signal and say so (`source == "rule_based"`).
"""

from __future__ import annotations

import logging

import pandas as pd

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


def predict_xgb_with_source(df: pd.DataFrame, ticker: str) -> tuple[str, float, str]:
    """Returns (signal, confidence, source); source is "xgb_binary" (real-data model), "xgb_demo",
    "xgb_unverified" or "rule_based".

    BUY if P(UP) >= direction_threshold, SELL if P(UP) <= 1 - threshold, otherwise HOLD.
    Confidence is the probability of the chosen side (for HOLD, the larger side).
    """
    from app.services.xgboost_service import predict_prob_up, signal_source

    try:
        p = predict_prob_up(df, ticker)
    except Exception as exc:  # noqa: BLE001 - a bad model file must not break predictions
        logger.warning("XGBoost inference failed for %s: %s", ticker, exc)
        p = None
    if p is None:
        signal, conf = _rule_based_signal(df)
        return signal, conf, "rule_based"

    src = signal_source(ticker)       # "xgb_binary" only for a model trained on real data
    thr = settings.direction_threshold
    if p >= thr:
        return "BUY", p, src
    if p <= 1 - thr:
        return "SELL", 1 - p, src
    return "HOLD", max(p, 1 - p), src


def predict_xgb(df: pd.DataFrame, ticker: str) -> tuple[str, float]:
    """(signal, confidence) — see `predict_xgb_with_source`."""
    signal, conf, _ = predict_xgb_with_source(df, ticker)
    return signal, conf


def _rule_based_signal(df: pd.DataFrame) -> tuple[str, float]:
    """Deterministic fallback using RSI + MACD."""
    last = df.iloc[-1]
    rsi = last.get("rsi", 50) if hasattr(last, "get") else getattr(last, "rsi", 50)
    macd = last.get("macd", 0) if hasattr(last, "get") else getattr(last, "macd", 0)
    macd_sig = last.get("macd_signal", 0) if hasattr(last, "get") else getattr(last, "macd_signal", 0)

    try:
        rsi = float(rsi)
        macd = float(macd)
        macd_sig = float(macd_sig)
    except (TypeError, ValueError):
        return "HOLD", 0.50

    if rsi < 35 and macd > macd_sig:
        return "BUY", 0.62
    if rsi > 65 and macd < macd_sig:
        return "SELL", 0.62
    return "HOLD", 0.55
