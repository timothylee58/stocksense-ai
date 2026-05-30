"""Feature engineering: computes the full 25-feature vector from raw OHLCV + indicators."""
from __future__ import annotations
import numpy as np
import pandas as pd

ANOMALY_FEATURES = [
    "volume_zscore", "bb_width", "atr_14", "daily_return",
    "roc_5", "price_vs_sma20",
]

DIRECTION_FEATURES = [
    "rsi", "macd", "macd_signal", "macd_hist",
    "roc_5", "roc_20",
    "bb_width", "bb_pct_b", "atr_14",
    "daily_return", "return_5d",
    "sma_20", "ema_12", "ema_26",
    "price_vs_sma20", "golden_cross",
    "volume_zscore",
    "anomaly_score",  # Stage 1 output fed into Stage 2
]

META_FEATURES = [
    "xgb_prob_up", "xgb_prob_down",
    "anomaly_score", "is_anomaly_int",
    "finbert_score", "reddit_sentiment", "news_volume_norm",
]


def build_feature_matrix(df: pd.DataFrame, include_anomaly: bool = False) -> pd.DataFrame:
    """Return a copy of df with only the direction features, filling NaN with 0."""
    features = DIRECTION_FEATURES.copy()
    if not include_anomaly and "anomaly_score" in features:
        features = [f for f in features if f != "anomaly_score"]
    available = [f for f in features if f in df.columns]
    result = df[available].copy()
    result = result.fillna(0)
    return result


def build_anomaly_matrix(df: pd.DataFrame) -> pd.DataFrame:
    available = [f for f in ANOMALY_FEATURES if f in df.columns]
    result = df[available].copy()
    result = result.fillna(0)
    return result


def build_target_series(df: pd.DataFrame) -> pd.Series:
    """Binary target: 1 if next-day close > today close, else 0."""
    close = df["Close"].squeeze()
    return (close.shift(-1) > close).astype(int)
