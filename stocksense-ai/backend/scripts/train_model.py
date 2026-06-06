#!/usr/bin/env python3
"""Full ML training pipeline with Optuna hyperparameter tuning.

Usage:
    python -m scripts.train_model --ticker NVDA
    python -m scripts.train_model --ticker MY.MAYBANK --trials 100
    python -m scripts.train_model --ticker NVDA --mlflow
    DEMO_MODE=true python -m scripts.train_model   # synthetic data

Pipeline
--------
1. Fetch OHLCV + compute indicators (chronological)
2. Build feature matrix via feature_service (leakage-proof: all features from t-1)
3. Chronological split: first 80 % train, last 20 % test (NO random shuffle)
4. Optuna: 50 trials of XGBoost hyperparams, optimising AUC on last TimeSeriesSplit fold
5. Retrain best model on full 80 % training set
6. Evaluate on held-out 20 % test set (AUC, accuracy, log-loss)
7. Train LSTM with Huber loss (replaces MSE, see lstm.py)
8. Compute SHAP values for the 10 most-impactful features
9. Run walk-forward backtest → Sharpe / alpha / drawdown
10. Log everything to MLflow (if --mlflow flag set)

Leakage-prevention notes
------------------------
- Target is defined as sign(close[t+1] - close[t]) via build_target_series.
  This shift is applied AFTER feature computation, so features at row t only
  use data through time t.  We then drop the last row (no future close yet).
- StandardScaler (if used for LSTM) is fit on the TRAINING split only and
  applied to both train and test — never fit on the full dataset.
- TimeSeriesSplit folds are chronologically ordered: no data from fold k leaks
  into the evaluation of fold k-1.

Ensemble design note
--------------------
We use a RULE-BASED ensemble (not a meta-learner) by default because:
  - Meta-learners require OOF predictions from all base models, which needs
    sufficient data across all assets (expensive, not always available).
  - Rule-based weights (XGB 0.50, FinBERT 0.30, LSTM 0.20) are interpretable
    and can be tuned by a domain expert without additional ML complexity.
  - The meta-learner (lr_meta_service.py) remains available and is preferred
    when trained on a large enough OOF dataset (>= 200 samples per ticker).
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb
import optuna

from sklearn.metrics import roc_auc_score, accuracy_score, log_loss
from sklearn.model_selection import TimeSeriesSplit

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("train_model")
optuna.logging.set_verbosity(optuna.logging.WARNING)

# ── Helpers ───────────────────────────────────────────────────────────────────

def _fetch_data(ticker: str, period: str = "2y") -> pd.DataFrame:
    """Fetch OHLCV + indicators. Uses moomoo if connected, yfinance fallback."""
    import sys, os
    sys.path.insert(0, str(Path(__file__).parent.parent))

    try:
        from app.data.fetcher import fetch_stock_data
        from app.core.config import get_settings
        settings = get_settings()

        loop = asyncio.get_event_loop()
        df = loop.run_until_complete(fetch_stock_data(ticker, period="2y"))
        if df is not None and len(df) > 100:
            logger.info("Fetched %d rows for %s via primary fetcher", len(df), ticker)
            return df
    except Exception as e:
        logger.warning("Primary fetcher failed (%s) — falling back to yfinance", e)

    import yfinance as yf
    # MY stocks use .KL suffix on yfinance
    yf_ticker = ticker.replace("MY.", "").replace(".", "") + ".KL" \
                if ticker.startswith("MY.") else ticker
    df = yf.download(yf_ticker, period=period, progress=False, auto_adjust=True)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    logger.info("yfinance: fetched %d rows for %s (%s)", len(df), ticker, yf_ticker)
    return df


def _make_demo_df(n: int = 500) -> pd.DataFrame:
    """Generate synthetic OHLCV data with realistic autocorrelation for demo training."""
    rng = np.random.default_rng(42)
    log_ret = rng.normal(0.0003, 0.015, n)
    close   = 10.0 * np.exp(np.cumsum(log_ret))
    df = pd.DataFrame({
        "Close":  close,
        "Open":   close * (1 - rng.uniform(0, 0.005, n)),
        "High":   close * (1 + rng.uniform(0, 0.010, n)),
        "Low":    close * (1 - rng.uniform(0, 0.010, n)),
        "Volume": rng.integers(1_000_000, 20_000_000, n).astype(float),
    })
    # Add required indicator columns
    df["rsi"]         = 50 + rng.normal(0, 10, n)
    df["macd"]        = rng.normal(0, 0.05, n)
    df["macd_signal"] = df["macd"].ewm(span=9).mean()
    df["macd_hist"]   = df["macd"] - df["macd_signal"]
    df["roc_5"]       = df["Close"].pct_change(5).fillna(0)
    df["roc_20"]      = df["Close"].pct_change(20).fillna(0)
    roll = df["Close"].rolling(20)
    df["sma_20"]      = roll.mean().fillna(df["Close"])
    df["sma_50"]      = df["Close"].rolling(50).mean().fillna(df["Close"])
    df["ema_12"]      = df["Close"].ewm(span=12).mean()
    df["ema_26"]      = df["Close"].ewm(span=26).mean()
    std20             = roll.std().fillna(1)
    df["bb_upper"]    = df["sma_20"] + 2 * std20
    df["bb_lower"]    = df["sma_20"] - 2 * std20
    df["bb_width"]    = (df["bb_upper"] - df["bb_lower"]) / df["sma_20"]
    df["bb_pct_b"]    = (df["Close"] - df["bb_lower"]) / (df["bb_upper"] - df["bb_lower"]).replace(0, 1)
    df["atr_14"]      = (df["High"] - df["Low"]).rolling(14).mean().fillna(0)
    df["daily_return"]= df["Close"].pct_change().fillna(0)
    df["return_5d"]   = df["Close"].pct_change(5).fillna(0)
    df["price_vs_sma20"] = df["Close"] / df["sma_20"] - 1
    df["golden_cross"]= (df["ema_12"] > df["ema_26"]).astype(float)
    vol_mean = df["Volume"].rolling(20).mean().replace(0, 1)
    df["volume_zscore"] = (df["Volume"] - vol_mean) / (df["Volume"].rolling(20).std().replace(0, 1))
    df["anomaly_score"] = rng.normal(0, 0.5, n)
    return df


# ── Optuna objective ──────────────────────────────────────────────────────────

def _optuna_objective(
    trial: optuna.Trial,
    X_train: np.ndarray,
    y_train: np.ndarray,
    X_val: np.ndarray,
    y_val: np.ndarray,
) -> float:
    """Maximise ROC-AUC on the validation fold."""
    params = {
        "n_estimators":     trial.suggest_int("n_estimators", 100, 800, step=50),
        "max_depth":        trial.suggest_int("max_depth", 3, 8),
        "learning_rate":    trial.suggest_float("learning_rate", 5e-3, 0.3, log=True),
        "subsample":        trial.suggest_float("subsample", 0.5, 1.0),
        "colsample_bytree": trial.suggest_float("colsample_bytree", 0.5, 1.0),
        "min_child_weight": trial.suggest_int("min_child_weight", 1, 10),
        "gamma":            trial.suggest_float("gamma", 0.0, 0.5),
        "reg_alpha":        trial.suggest_float("reg_alpha", 1e-5, 1.0, log=True),
        "reg_lambda":       trial.suggest_float("reg_lambda", 1e-5, 1.0, log=True),
        "eval_metric":      "auc",
        "early_stopping_rounds": 20,
        "verbosity":        0,
        "random_state":     42,
    }
    model = xgb.XGBClassifier(**params)
    model.fit(X_train, y_train, eval_set=[(X_val, y_val)], verbose=False)
    proba = model.predict_proba(X_val)[:, 1]
    return roc_auc_score(y_val, proba)


# ── Main pipeline ─────────────────────────────────────────────────────────────

def train_pipeline(ticker: str, n_trials: int = 50, use_mlflow: bool = False, demo: bool = False) -> dict:
    """
    Full training pipeline. Returns dict of all metrics.

    Chronological split rationale:
      train: rows 0..split-1   (80 %)
      test:  rows split..n-1   (20 %)

    We pass the LAST TimeSeriesSplit fold as the eval_set inside Optuna so that
    the tuner never sees test-set rows, yet optimises on held-out validation.
    """
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from app.services.feature_service import build_feature_matrix, build_target_series
    from app.services.xgboost_service import shap_explain
    from app.services.backtest_service import run_backtest
    from app.core.config import get_settings
    settings = get_settings()

    # ── 1. Data ───────────────────────────────────────────────────────────────
    if demo or settings.demo_mode:
        logger.info("DEMO_MODE: using synthetic training data for %s", ticker)
        df = _make_demo_df(n=500)
    else:
        df = _fetch_data(ticker)

    if len(df) < 150:
        raise ValueError(f"Insufficient data for {ticker}: {len(df)} rows (need ≥150)")

    # ── 2. Features (leakage-proof) ───────────────────────────────────────────
    X = build_feature_matrix(df, include_anomaly=True).fillna(0)
    y = build_target_series(df)
    X = X.iloc[:-1]   # drop last row (no target close[t+1] yet)
    y = y.iloc[:-1]

    n     = len(X)
    split = int(n * 0.80)
    logger.info("Dataset: %d rows → train %d, test %d, features %d", n, split, n - split, X.shape[1])

    X_tr, y_tr = X.iloc[:split].values, y.iloc[:split].values
    X_te, y_te = X.iloc[split:].values, y.iloc[split:].values

    # Optuna uses the last fold of TimeSeriesSplit over the TRAINING portion
    tscv = TimeSeriesSplit(n_splits=5)
    folds = list(tscv.split(X_tr))
    tr_idx, va_idx = folds[-1]
    X_opt_tr, y_opt_tr = X_tr[tr_idx], y_tr[tr_idx]
    X_opt_va, y_opt_va = X_tr[va_idx], y_tr[va_idx]

    # ── 3. Optuna hyperparameter search ───────────────────────────────────────
    logger.info("Starting Optuna study (%d trials) for %s…", n_trials, ticker)
    study = optuna.create_study(
        direction="maximize",
        pruner=optuna.pruners.MedianPruner(n_warmup_steps=10),
        sampler=optuna.samplers.TPESampler(seed=42),
    )
    study.optimize(
        lambda t: _optuna_objective(t, X_opt_tr, y_opt_tr, X_opt_va, y_opt_va),
        n_trials=n_trials,
        show_progress_bar=False,
    )
    best = study.best_params
    logger.info("Best params (AUC=%.4f): %s", study.best_value, best)

    # ── 4. Retrain on full training set with best params ──────────────────────
    final_model = xgb.XGBClassifier(
        **{k: v for k, v in best.items()},
        eval_metric="auc",
        early_stopping_rounds=30,
        verbosity=0,
        random_state=42,
    )
    final_model.fit(X_tr, y_tr, eval_set=[(X_opt_va, y_opt_va)], verbose=False)

    import os
    os.makedirs(settings.models_dir, exist_ok=True)
    mp = os.path.join(settings.models_dir, f"xgb_{ticker.upper()}.json")
    final_model.save_model(mp)
    logger.info("Model saved → %s", mp)

    # ── 5. Evaluate on held-out test set ─────────────────────────────────────
    proba_te = final_model.predict_proba(X_te)[:, 1]
    test_auc = roc_auc_score(y_te, proba_te)
    test_acc = accuracy_score(y_te, (proba_te > 0.5).astype(int))
    test_ll  = log_loss(y_te, proba_te)
    logger.info("Test set — AUC %.4f | Acc %.4f | LogLoss %.4f", test_auc, test_acc, test_ll)

    # ── 6. LSTM with Huber loss ───────────────────────────────────────────────
    lstm_meta: dict = {}
    if not demo and not settings.demo_mode:
        try:
            from app.ml.models.lstm import train_lstm
            lstm_meta = train_lstm(df, ticker)
            logger.info("LSTM trained: %s", lstm_meta)
        except Exception as e:
            logger.warning("LSTM training skipped: %s", e)

    # ── 7. SHAP values ────────────────────────────────────────────────────────
    shap_result: dict = {}
    try:
        shap_result = shap_explain(df, ticker)
        logger.info("SHAP top feature: %s (%.4f)",
                    shap_result["top_features"][0]["feature"],
                    shap_result["top_features"][0]["contribution"])
    except Exception as e:
        logger.warning("SHAP computation failed: %s", e)

    # ── 8. Backtest ───────────────────────────────────────────────────────────
    bt_result: dict = {}
    try:
        bt_result = run_backtest(df, ticker)
        m = bt_result["metrics"]
        logger.info(
            "Backtest: return %.1f%% | alpha %.1f%% | Sharpe %.2f | drawdown %.1f%%",
            m["total_return"] * 100, m["alpha"] * 100,
            m["sharpe_ratio"], m["max_drawdown"] * 100,
        )
    except Exception as e:
        logger.warning("Backtest failed: %s", e)

    summary = {
        "ticker":          ticker,
        "n_rows":          n,
        "n_features":      X.shape[1],
        "optuna_best_auc": round(study.best_value, 4),
        "test_auc":        round(test_auc, 4),
        "test_accuracy":   round(test_acc, 4),
        "test_log_loss":   round(test_ll, 4),
        "best_params":     best,
        "lstm":            lstm_meta,
        "backtest":        bt_result.get("metrics", {}),
        "shap_top":        shap_result.get("top_features", [])[:5],
    }

    # ── 9. MLflow logging ─────────────────────────────────────────────────────
    if use_mlflow:
        try:
            import mlflow
            mlflow.set_tracking_uri(settings.mlflow_tracking_uri)
            with mlflow.start_run(run_name=f"{ticker}_optuna"):
                mlflow.log_params(best)
                mlflow.log_metrics({
                    "optuna_best_auc":  study.best_value,
                    "test_auc":         test_auc,
                    "test_accuracy":    test_acc,
                    "test_log_loss":    test_ll,
                    **{f"bt_{k}": v for k, v in bt_result.get("metrics", {}).items()
                       if isinstance(v, (int, float))},
                })
                mlflow.log_artifact(mp, artifact_path="models")
            logger.info("MLflow run logged")
        except Exception as e:
            logger.warning("MLflow logging failed: %s", e)

    return summary


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Train XGBoost + LSTM for a stock ticker")
    parser.add_argument("--ticker",  default="NVDA",  help="Ticker symbol (e.g. NVDA, MY.MAYBANK)")
    parser.add_argument("--trials",  type=int, default=50, help="Optuna trials (default 50)")
    parser.add_argument("--mlflow",  action="store_true",  help="Log metrics to MLflow")
    parser.add_argument("--demo",    action="store_true",  help="Use synthetic data (no external APIs)")
    args = parser.parse_args()

    result = train_pipeline(
        ticker=args.ticker,
        n_trials=args.trials,
        use_mlflow=args.mlflow,
        demo=args.demo,
    )
    import json
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
