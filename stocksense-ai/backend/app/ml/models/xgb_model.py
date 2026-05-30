"""
XGBoost signal classifier: BUY / HOLD / SELL.
Label generation: compare next-5-day return vs threshold.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import numpy as np
import pandas as pd
import joblib
from sklearn.preprocessing import LabelEncoder
from xgboost import XGBClassifier

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

FEATURE_COLS = [
    "rsi",
    "macd", "macd_signal", "macd_hist",
    "sma_20", "sma_50",
    "bb_upper", "bb_lower",
    # derived
    "close_to_sma20", "close_to_sma50",
    "close_to_bb_upper", "close_to_bb_lower",
    "volume_change",
    "price_change_1d", "price_change_5d",
]

BUY_THRESHOLD  = 0.015   # +1.5 % over 5 days
SELL_THRESHOLD = -0.015  # -1.5 %


def _model_path(ticker: str) -> Path:
    return Path(settings.models_dir) / f"{ticker.upper()}_xgb.pkl"


def _build_features(df: pd.DataFrame) -> pd.DataFrame:
    close = df["Close"].squeeze()
    feat = pd.DataFrame(index=df.index)

    for col in ["rsi", "macd", "macd_signal", "macd_hist",
                "sma_20", "sma_50", "bb_upper", "bb_lower"]:
        feat[col] = df[col] if col in df.columns else np.nan

    feat["close_to_sma20"]   = (close - feat["sma_20"]) / feat["sma_20"].replace(0, np.nan)
    feat["close_to_sma50"]   = (close - feat["sma_50"]) / feat["sma_50"].replace(0, np.nan)
    feat["close_to_bb_upper"] = (close - feat["bb_upper"]) / feat["bb_upper"].replace(0, np.nan)
    feat["close_to_bb_lower"] = (close - feat["bb_lower"]) / feat["bb_lower"].replace(0, np.nan)
    feat["volume_change"]    = df["Volume"].squeeze().pct_change()
    feat["price_change_1d"]  = close.pct_change(1)
    feat["price_change_5d"]  = close.pct_change(5)

    return feat


def _make_labels(close: pd.Series, horizon: int = 5) -> pd.Series:
    future_ret = close.shift(-horizon).divide(close) - 1
    labels = pd.Series("HOLD", index=close.index)
    labels[future_ret > BUY_THRESHOLD]  = "BUY"
    labels[future_ret < SELL_THRESHOLD] = "SELL"
    return labels


def train_xgb(df: pd.DataFrame, ticker: str) -> dict:
    feat = _build_features(df)
    close = df["Close"].squeeze()
    labels = _make_labels(close)

    combined = feat.join(labels.rename("label")).dropna()
    if len(combined) < 50:
        raise ValueError(f"Not enough data to train XGB for {ticker}")

    X = combined[FEATURE_COLS].values
    y = combined["label"].values
    le = LabelEncoder()
    y_enc = le.fit_transform(y)

    split = int(len(X) * 0.85)
    X_tr, y_tr = X[:split], y_enc[:split]
    X_va, y_va = X[split:], y_enc[split:]

    model = XGBClassifier(
        n_estimators=200,
        max_depth=4,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        use_label_encoder=False,
        eval_metric="mlogloss",
        early_stopping_rounds=20,
        verbosity=0,
    )
    model.fit(X_tr, y_tr, eval_set=[(X_va, y_va)], verbose=False)

    val_acc = float((model.predict(X_va) == y_va).mean())

    os.makedirs(settings.models_dir, exist_ok=True)
    joblib.dump({"model": model, "label_encoder": le}, _model_path(ticker))

    logger.info("XGB trained for %s — val_acc=%.3f", ticker, val_acc)
    return {"val_accuracy": round(val_acc, 4)}


def predict_xgb(df: pd.DataFrame, ticker: str) -> tuple[str, float]:
    """
    Returns (signal, confidence) using the last row of features.
    Falls back to rule-based signal if no model found.
    """
    path = _model_path(ticker)
    if not path.exists():
        return _rule_based_signal(df)

    checkpoint = joblib.load(path)
    model: XGBClassifier = checkpoint["model"]
    le: LabelEncoder = checkpoint["label_encoder"]

    feat = _build_features(df)
    last_row = feat.iloc[[-1]][FEATURE_COLS].ffill().bfill()

    if last_row.isnull().all(axis=None):
        return _rule_based_signal(df)

    proba = model.predict_proba(last_row.values)[0]
    pred_idx = int(np.argmax(proba))
    signal = le.inverse_transform([pred_idx])[0]
    confidence = float(proba[pred_idx])

    return signal, confidence


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
