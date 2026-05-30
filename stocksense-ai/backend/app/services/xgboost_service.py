"""Stage 2 — XGBoost direction classifier."""
from __future__ import annotations
import logging
import os
import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.model_selection import TimeSeriesSplit

from app.core.config import get_settings
from app.services.feature_service import build_feature_matrix, build_target_series

logger = logging.getLogger(__name__)
settings = get_settings()


def _model_path(ticker: str) -> str:
    os.makedirs(settings.models_dir, exist_ok=True)
    return os.path.join(settings.models_dir, f"xgb_{ticker.upper()}.json")


def train_xgboost(df: pd.DataFrame, ticker: str) -> xgb.XGBClassifier:
    """Train XGBoost with TimeSeriesSplit CV. Returns trained model."""
    X = build_feature_matrix(df, include_anomaly=True)
    y = build_target_series(df)

    # Align — drop last row (no target label)
    X = X.iloc[:-1]
    y = y.iloc[:-1]

    if len(X) < 100:
        raise ValueError(f"Insufficient data for XGBoost training: {len(X)} rows")

    model = xgb.XGBClassifier(
        n_estimators=500,
        learning_rate=0.05,
        max_depth=6,
        subsample=0.8,
        colsample_bytree=0.8,
        min_child_weight=5,
        eval_metric="auc",
        early_stopping_rounds=30,
        random_state=42,
        verbosity=0,
    )

    # TimeSeriesSplit — NEVER random split for financial time series
    tscv = TimeSeriesSplit(n_splits=5)
    splits = list(tscv.split(X))
    train_idx, val_idx = splits[-1]  # use last fold for eval_set

    X_arr = X.values
    y_arr = y.values

    model.fit(
        X_arr[train_idx], y_arr[train_idx],
        eval_set=[(X_arr[val_idx], y_arr[val_idx])],
        verbose=False,
    )

    model.save_model(_model_path(ticker))
    logger.info("XGBoost trained for %s — %d samples, %d features", ticker, len(X), X.shape[1])
    return model


def predict_xgboost(df: pd.DataFrame, ticker: str) -> tuple[float, float]:
    """
    Run XGBoost on latest row.
    Returns (prob_up, prob_down) as floats.
    Trains model if none exists.
    """
    mp = _model_path(ticker)
    if os.path.exists(mp):
        model = xgb.XGBClassifier()
        model.load_model(mp)
    else:
        logger.info("No XGBoost model for %s — training now", ticker)
        model = train_xgboost(df, ticker)

    X = build_feature_matrix(df, include_anomaly=True)
    if X.empty:
        return 0.5, 0.5

    X_last = X.iloc[[-1]].fillna(0)
    proba = model.predict_proba(X_last.values)[0]
    # proba = [P(Down), P(Up)]
    prob_down = float(proba[0])
    prob_up = float(proba[1])
    return prob_up, prob_down
