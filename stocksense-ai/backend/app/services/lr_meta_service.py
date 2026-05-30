"""Stage 3 — Logistic Regression meta-learner stacker."""
from __future__ import annotations
import logging
import os
import joblib
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.calibration import CalibratedClassifierCV
from typing import Literal

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

Signal = Literal["BUY", "SELL", "HOLD"]


def _model_path(ticker: str) -> str:
    os.makedirs(settings.models_dir, exist_ok=True)
    return os.path.join(settings.models_dir, f"lr_meta_{ticker.upper()}.pkl")


def train_lr_meta(
    meta_features: list[list[float]],
    labels: list[int],
    ticker: str,
) -> CalibratedClassifierCV:
    """
    Train calibrated LR stacker.
    meta_features: rows of [xgb_prob_up, xgb_prob_down, anomaly_score, is_anomaly_int,
                             finbert_score, reddit_sentiment, news_volume_norm]
    labels: 1=Up, 0=Down
    """
    X = np.array(meta_features)
    y = np.array(labels)

    if len(X) < 20:
        raise ValueError(f"Insufficient meta-samples for LR: {len(X)}")

    lr = LogisticRegression(C=1.0, solver="lbfgs", max_iter=1000, random_state=42)
    calibrated = CalibratedClassifierCV(lr, cv=min(5, len(X) // 4), method="sigmoid")
    calibrated.fit(X, y)

    joblib.dump(calibrated, _model_path(ticker))
    logger.info("LR meta-learner trained for %s — %d samples", ticker, len(X))
    return calibrated


def predict_lr_meta(
    xgb_prob_up: float,
    xgb_prob_down: float,
    anomaly_score: float,
    is_anomaly: bool,
    finbert_score: float,
    reddit_sentiment: float,
    news_volume_norm: float,
    ticker: str,
) -> tuple[Signal, float]:
    """
    Run LR meta-learner on single observation.
    Returns (signal, confidence).
    Falls back to XGBoost signal if no model trained.
    """
    mp = _model_path(ticker)

    if not os.path.exists(mp):
        # Fallback: use XGBoost signal directly
        threshold = settings.direction_threshold
        if xgb_prob_up >= threshold:
            return "BUY", round(xgb_prob_up, 3)
        elif xgb_prob_down >= threshold:
            return "SELL", round(xgb_prob_down, 3)
        return "HOLD", round(max(xgb_prob_up, xgb_prob_down), 3)

    model = joblib.load(mp)
    X = np.array([[
        xgb_prob_up,
        xgb_prob_down,
        float(anomaly_score) if anomaly_score is not None else 0.0,
        int(is_anomaly),
        float(finbert_score),
        float(reddit_sentiment),
        float(news_volume_norm),
    ]])

    proba = model.predict_proba(X)[0]
    prob_up = float(proba[1]) if len(proba) > 1 else float(proba[0])
    prob_down = float(proba[0])

    threshold = settings.direction_threshold
    if prob_up >= threshold:
        signal: Signal = "BUY"
        confidence = prob_up
    elif prob_down >= threshold:
        signal = "SELL"
        confidence = prob_down
    else:
        signal = "HOLD"
        confidence = max(prob_up, prob_down)

    return signal, round(min(0.99, confidence), 3)
