"""Stage 1 — Isolation Forest anomaly detection."""
from __future__ import annotations
import logging
import os
import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import RobustScaler

from app.core.config import get_settings
from app.services.feature_service import build_anomaly_matrix

logger = logging.getLogger(__name__)
settings = get_settings()


def _model_path(ticker: str) -> str:
    os.makedirs(settings.models_dir, exist_ok=True)
    return os.path.join(settings.models_dir, f"isolation_forest_{ticker.upper()}.pkl")


def _scaler_path(ticker: str) -> str:
    return os.path.join(settings.models_dir, f"if_scaler_{ticker.upper()}.pkl")


def train_isolation_forest(df: pd.DataFrame, ticker: str) -> tuple[IsolationForest, RobustScaler]:
    """Train and save Isolation Forest model. Returns (model, scaler)."""
    X = build_anomaly_matrix(df)
    if X.empty or len(X) < 50:
        raise ValueError(f"Insufficient data for Isolation Forest: {len(X)} rows")

    scaler = RobustScaler()
    X_scaled = scaler.fit_transform(X)

    model = IsolationForest(
        n_estimators=200,
        contamination=settings.anomaly_contamination,
        max_samples="auto",
        random_state=42,
        n_jobs=-1,
    )
    model.fit(X_scaled)

    joblib.dump(model, _model_path(ticker))
    joblib.dump(scaler, _scaler_path(ticker))
    logger.info("Isolation Forest trained for %s — %d samples", ticker, len(X))
    return model, scaler


def predict_anomalies(df: pd.DataFrame, ticker: str) -> pd.DataFrame:
    """
    Runs Isolation Forest inference on df.
    Returns df with added columns: anomaly_score, is_anomaly.
    Trains model if none exists.
    """
    mp = _model_path(ticker)
    sp = _scaler_path(ticker)

    if os.path.exists(mp) and os.path.exists(sp):
        model = joblib.load(mp)
        scaler = joblib.load(sp)
    else:
        logger.info("No Isolation Forest model for %s — training now", ticker)
        model, scaler = train_isolation_forest(df, ticker)

    X = build_anomaly_matrix(df)
    available_idx = X.index
    X_scaled = scaler.transform(X.fillna(0))

    # scores: negative = more anomalous; decision_function returns raw scores
    raw_scores = model.decision_function(X_scaled)
    labels = model.predict(X_scaled)  # -1 = anomaly, 1 = normal

    result = df.copy()
    result["anomaly_score"] = np.nan
    result["is_anomaly"] = False
    result.loc[available_idx, "anomaly_score"] = raw_scores
    result.loc[available_idx, "is_anomaly"] = labels == -1

    return result


def get_anomaly_history_from_df(df: pd.DataFrame, ticker: str, days: int = 30) -> list[dict]:
    """Run IF on recent data and return anomaly records."""
    df_with_anomalies = predict_anomalies(df, ticker)
    recent = df_with_anomalies.tail(days)
    records = []
    for idx, row in recent.iterrows():
        records.append({
            "ticker": ticker.upper(),
            "trading_date": str(idx)[:10],
            "anomaly_score": round(float(row.get("anomaly_score", 0)), 4),
            "is_anomaly": bool(row.get("is_anomaly", False)),
            "price_close": round(float(row.get("Close", 0)), 4),
            "volume": int(row.get("Volume", 0)),
            "daily_return": round(float(row.get("daily_return", 0)), 6) if "daily_return" in row else None,
            "bb_width": round(float(row.get("bb_width", 0)), 6) if "bb_width" in row else None,
            "volume_zscore": round(float(row.get("volume_zscore", 0)), 4) if "volume_zscore" in row else None,
        })
    return records
