"""Stage 2 — XGBoost direction classifier."""
from __future__ import annotations

import json
import logging
import math
import os
from datetime import UTC, datetime

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


def _features_path(ticker: str) -> str:
    return os.path.join(settings.models_dir, f"xgb_{ticker.upper()}.features.json")


def save_feature_columns(ticker: str, columns: list[str], demo: bool | None = None) -> None:
    """Write the model's metadata sidecar atomically: the exact feature columns (and order) it
    was trained on, and whether the training data was synthetic (`demo`).

    `demo` defaults to the backend's DEMO_MODE. Only a model recorded as demo=False is allowed
    to drive trades; see `signal_source`."""
    _write_meta(ticker, columns, settings.demo_mode if demo is None else demo)


def _meta_tmp(ticker: str) -> str:
    return _features_path(ticker) + ".tmp"


def _write_meta(ticker: str, columns: list[str], demo: bool, publish: bool = True) -> None:
    os.makedirs(settings.models_dir, exist_ok=True)
    tmp = _meta_tmp(ticker)
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"columns": list(columns), "demo": bool(demo),
                   "trained_at": datetime.now(UTC).isoformat()}, f)
    if publish:
        os.replace(tmp, _features_path(ticker))


def _load_meta(ticker: str) -> dict | None:
    """Sidecar as {"columns": [...], "demo": bool|None}. A legacy list-only file has no
    provenance (demo None). Returns None if absent or malformed."""
    try:
        with open(_features_path(ticker), encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, ValueError):
        return None
    if isinstance(raw, list):
        cols, demo = raw, None
    elif isinstance(raw, dict):
        cols, demo = raw.get("columns"), raw.get("demo")
    else:
        return None
    if not isinstance(cols, list) or not all(isinstance(c, str) for c in cols):
        return None
    return {"columns": cols, "demo": demo if isinstance(demo, bool) else None}


def signal_source(ticker: str) -> str:
    """Provenance of the saved model: "xgb_binary" only when it is recorded as trained on real
    data; "xgb_demo" for synthetic training data; "xgb_unverified" when unknown (legacy
    sidecar or none), so the risk gate can allow-list "xgb_binary" alone."""
    meta = _load_meta(ticker)
    if meta is None or meta["demo"] is None:
        return "xgb_unverified"
    return "xgb_demo" if meta["demo"] else "xgb_binary"


def aligned_features(df: pd.DataFrame, ticker: str, model: xgb.XGBClassifier) -> pd.DataFrame:
    """Feature matrix in exactly the model's training columns, for every consumer (trading
    signal, SHAP, backtest, pipeline). Raises ValueError rather than fabricating a column the
    model was trained on (e.g. `anomaly_score`) when the data cannot supply it."""
    X = build_feature_matrix(df, include_anomaly=True)
    meta = _load_meta(ticker)
    if meta:
        missing = [c for c in meta["columns"] if c not in X.columns]
        if missing:
            raise ValueError(f"{ticker}: data lacks model feature(s) {missing}")
        if len(meta["columns"]) != model.n_features_in_:
            raise ValueError(f"{ticker}: feature list ({len(meta['columns'])}) does not match the "
                             f"model ({model.n_features_in_}); retrain")
        return X[meta["columns"]]
    if X.shape[1] != model.n_features_in_:
        raise ValueError(f"{ticker}: model expects {model.n_features_in_} features, data has "
                         f"{X.shape[1]} and no feature list was saved")
    return X


def predict_prob_up(df: pd.DataFrame, ticker: str) -> float | None:
    """P(next-day close > today's close) from the trained binary model.

    This is the ONE model the trading signal, `/api/explain` and `/api/backtest` all use.
    Returns None when there is no usable model (or the data cannot supply its features); it
    never trains (models are pre-trained artefacts), so callers can fall back and say so.
    """
    mp = _model_path(ticker)
    if not os.path.exists(mp):
        return None
    model = xgb.XGBClassifier()
    model.load_model(mp)
    try:
        X = aligned_features(df, ticker, model)
    except ValueError as exc:
        logger.warning("%s", exc)
        return None
    if X.empty:
        return None
    X_last = X.iloc[[-1]].fillna(0).values.astype(np.float64)
    p = float(model.predict_proba(X_last)[0][1])
    return p if math.isfinite(p) else None


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

    # write both artefacts to temp files first, then publish the pair, so a failed write
    # cannot leave a new model next to another run's feature list
    mp = _model_path(ticker)
    tmp_model = mp[:-len(".json")] + ".tmp.json"        # XGBoost picks the format by extension
    model.save_model(tmp_model)
    _write_meta(ticker, list(X.columns), settings.demo_mode, publish=False)
    os.replace(_meta_tmp(ticker), _features_path(ticker))
    os.replace(tmp_model, mp)
    logger.info("XGBoost trained for %s — %d samples, %d features", ticker, len(X), X.shape[1])
    return model


def shap_explain(df: pd.DataFrame, ticker: str) -> dict:
    """
    Compute SHAP feature contributions for the latest row using TreeExplainer.

    Returns a dict with per-feature contributions sorted by |contribution|.
    Uses first 80 % of feature rows as the background distribution — never
    data from the test / recent window, so no leakage into the explainer.
    """
    import shap

    mp = _model_path(ticker)
    if not os.path.exists(mp):
        raise ValueError(f"No XGBoost model for {ticker} — run training first")

    model = xgb.XGBClassifier()
    model.load_model(mp)

    X = aligned_features(df, ticker, model).fillna(0)
    if X.empty:
        raise ValueError("Empty feature matrix")

    n = len(X)
    split = int(n * 0.80)
    X_bg   = X.iloc[:split].values     # background: training-era distribution
    X_last = X.iloc[[-1]].values       # the single row we're explaining

    explainer   = shap.TreeExplainer(model, data=X_bg, feature_perturbation="interventional")
    shap_vals   = explainer.shap_values(X_last)   # (1, n_features) or list[array]

    # For a binary XGBClassifier shap_values is a single (1, n_feats) array (log-odds space)
    sv = shap_vals[0] if shap_vals.ndim == 2 else shap_vals          # shape (n_features,)

    proba   = model.predict_proba(X_last)[0]
    prob_up = float(proba[1])
    ev      = float(explainer.expected_value) if np.isscalar(explainer.expected_value) \
              else float(explainer.expected_value[1])

    features = [
        {"feature": fn, "value": round(float(fv), 4), "contribution": round(float(c), 4)}
        for fn, fv, c in zip(X.columns, X_last[0], sv)
    ]
    features.sort(key=lambda f: abs(f["contribution"]), reverse=True)

    return {
        "ticker":         ticker,
        "prediction":     "UP" if prob_up >= 0.5 else "DOWN",
        "probability":    round(prob_up, 4),
        "expected_value": round(ev, 4),
        "top_features":   features[:12],   # top 12 most impactful
        "all_features":   features,
    }


def predict_xgboost(df: pd.DataFrame, ticker: str) -> tuple[float, float]:
    """(prob_up, prob_down) for the latest row from the saved model; (0.5, 0.5) when there is
    no usable model. Inference never trains (models are pre-trained artefacts)."""
    p = predict_prob_up(df, ticker)
    if p is None:
        return 0.5, 0.5
    return p, 1.0 - p
