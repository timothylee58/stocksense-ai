"""Walk-forward backtest engine.

Correctness guarantees
-----------------------
- Model is loaded from disk (trained on the TRAINING set only).
- Backtest runs on the held-out test window: the last `test_fraction` of rows.
- next-day return at row t is the return from close[t] to close[t+1], so the
  signal at t (computed from features through t) is used to decide whether to
  hold from t→t+1.  No look-ahead.
- Position: long-only (hold when predicted UP, flat otherwise).  No shorting.
- Risk-free rate for Sharpe/Sortino: 4 % annualised (Malaysian OPR proxy).
"""
from __future__ import annotations

import logging
import os
from datetime import timezone

import numpy as np
import pandas as pd
import xgboost as xgb

from app.services.feature_service import build_feature_matrix, build_target_series

logger = logging.getLogger(__name__)

_RISK_FREE_DAILY = 0.04 / 252


def _model_path(ticker: str) -> str:
    from app.core.config import get_settings
    settings = get_settings()
    return os.path.join(settings.models_dir, f"xgb_{ticker.upper()}.json")


def run_backtest(
    df: pd.DataFrame,
    ticker: str,
    test_fraction: float = 0.20,
) -> dict:
    """
    Walk-forward long-only backtest on the chronological test set.

    Returns:
        metrics  — Sharpe, Sortino, alpha, max_drawdown, win_rate, etc.
        equity_curve — list of {date, strategy, benchmark} dicts for charting.
    """
    mp = _model_path(ticker)
    if not os.path.exists(mp):
        raise ValueError(f"No trained model for {ticker}. Run `make train` first.")

    model = xgb.XGBClassifier()
    model.load_model(mp)

    # Feature matrix and targets — chronologically aligned
    X = build_feature_matrix(df, include_anomaly=True).fillna(0)
    close = df["Close"].squeeze()

    # Both X and close must be same length; X already drops the last target-less row
    X = X.iloc[:-1]
    close_aligned = close.iloc[: len(X)]

    n = len(X)
    if n < 60:
        raise ValueError(f"Insufficient history for backtest: {n} rows")

    split = int(n * (1 - test_fraction))
    X_test     = X.iloc[split:]
    close_test = close_aligned.iloc[split:]

    # Predict probability of UP for every test row
    prob_up    = model.predict_proba(X_test.values)[:, 1]
    position   = (prob_up > 0.5).astype(float)   # 1 = hold, 0 = flat

    # Next-day log-return (use log for compounding correctness)
    log_ret    = np.log(close_test / close_test.shift(1)).fillna(0).values
    strat_log  = log_ret * position                # 0 when flat
    bench_log  = log_ret                           # always long

    # Equity curves (start at 1.0)
    strat_eq   = np.exp(np.cumsum(strat_log))
    bench_eq   = np.exp(np.cumsum(bench_log))

    # ── Metrics ───────────────────────────────────────────────────────────────
    n_days          = len(strat_log)
    total_return    = float(strat_eq[-1] - 1)
    bench_return    = float(bench_eq[-1] - 1)
    alpha           = total_return - bench_return

    mean_d = float(np.mean(strat_log))
    std_d  = float(np.std(strat_log))
    sharpe = ((mean_d - _RISK_FREE_DAILY) / std_d * np.sqrt(252)) if std_d > 0 else 0.0

    downside_d = float(np.std(strat_log[strat_log < 0])) if np.any(strat_log < 0) else 1e-9
    sortino    = ((mean_d - _RISK_FREE_DAILY) / downside_d * np.sqrt(252))

    rolling_max  = np.maximum.accumulate(strat_eq)
    drawdown_arr = (strat_eq - rolling_max) / rolling_max
    max_drawdown = float(np.min(drawdown_arr))

    # Win rate: fraction of HELD days with positive return
    held_mask = position == 1
    win_rate  = float(np.mean(log_ret[held_mask] > 0)) if np.any(held_mask) else 0.0
    n_trades  = int(np.sum(held_mask))

    # Calmar ratio (annualised return / max drawdown)
    ann_return = (1 + total_return) ** (252 / max(n_days, 1)) - 1
    calmar     = ann_return / abs(max_drawdown) if max_drawdown < 0 else 0.0

    # ── Equity curve for chart ─────────────────────────────────────────────────
    index = close_test.index
    equity_curve = [
        {
            "date":      d.isoformat() if hasattr(d, "isoformat") else str(d),
            "strategy":  round(float(s), 4),
            "benchmark": round(float(b), 4),
        }
        for d, s, b in zip(index, strat_eq, bench_eq)
    ]

    return {
        "ticker": ticker,
        "test_period": {
            "start":   equity_curve[0]["date"]  if equity_curve else "",
            "end":     equity_curve[-1]["date"] if equity_curve else "",
            "n_days":  n_days,
        },
        "metrics": {
            "total_return":    round(total_return,  4),
            "benchmark_return":round(bench_return,  4),
            "alpha":           round(alpha,          4),
            "sharpe_ratio":    round(sharpe,         3),
            "sortino_ratio":   round(sortino,        3),
            "calmar_ratio":    round(calmar,         3),
            "max_drawdown":    round(max_drawdown,   4),
            "win_rate":        round(win_rate,       3),
            "n_trades":        n_trades,
            "annualised_return": round(ann_return,   4),
        },
        "equity_curve": equity_curve,
        "position_logic": "long-only: hold when P(UP) > 0.5, flat otherwise",
    }
