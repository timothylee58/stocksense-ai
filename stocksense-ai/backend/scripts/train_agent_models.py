#!/usr/bin/env python3
"""Offline provisioning of the artefacts the agent loaders expect.

Writes ``{TICKER}_xgb.pkl`` (joblib dict: model + label encoder) and
``{TICKER}_lstm.pt`` / ``{TICKER}_lstm_scaler.pkl`` using the trainer
functions in ``app.ml.models``.  ``scripts/train_model.py`` is a different
pipeline (binary target, Optuna, ``xgb_{TICKER}.json``) that these loaders
cannot read.

Run from ``stocksense-ai/backend`` so ``models_dir`` resolves to ``./models``:

    .venv/bin/python -m scripts.train_agent_models --tickers AAPL,NVDA
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import pandas as pd
import yfinance as yf

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import get_settings
from app.data.fetcher import add_indicators
from app.ml.models.lstm import predict_lstm, train_lstm
from app.ml.models.xgb_model import predict_xgb, train_xgb

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("train_agent_models")


def fetch_history(ticker: str, years: int = 2) -> pd.DataFrame:
    raw = yf.download(ticker, period=f"{years}y", progress=False, auto_adjust=True)
    if raw.empty:
        raise ValueError(f"no yfinance data for {ticker}")
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)
    df = raw[["Open", "High", "Low", "Close", "Volume"]].copy()
    df = add_indicators(df)
    return df.dropna(subset=["Close"])


def probe(df: pd.DataFrame, ticker: str, threshold: float) -> dict:
    """Same blend the runtime uses, with FinBERT at 0 (no news key)."""
    signal, xgb_conf = predict_xgb(df, ticker)
    prices, lstm_conf = predict_lstm(df, ticker, n_days=10)
    last = float(df["Close"].squeeze().iloc[-1])
    ret_7d = (float(prices[6]) - last) / last if len(prices) >= 7 else 0.0
    lstm_dir = "UP" if ret_7d > 0.005 else "DOWN" if ret_7d < -0.005 else "NEUTRAL"

    xgb_score = {"BUY": 1.0, "SELL": -1.0}.get(signal.upper(), 0.0) * xgb_conf
    lstm_score = {"UP": 1.0, "DOWN": -1.0}.get(lstm_dir, 0.0) * lstm_conf
    net = 0.5 * xgb_score + 0.2 * lstm_score
    return {
        "xgb_signal": signal,
        "xgb_conf": round(xgb_conf, 4),
        "lstm_dir": lstm_dir,
        "lstm_conf": round(lstm_conf, 4),
        "forecast_7d_return": round(ret_7d, 4),
        "net_no_news": round(net, 4),
        "crosses_gate": abs(net) >= threshold,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tickers", default=",".join(get_settings().challenge_universe))
    parser.add_argument("--years", type=int, default=2)
    parser.add_argument("--probe-only", action="store_true")
    args = parser.parse_args()

    settings = get_settings()
    models_dir = Path(settings.models_dir)
    models_dir.mkdir(parents=True, exist_ok=True)

    report = {}
    for ticker in [t.strip().upper() for t in args.tickers.split(",") if t.strip()]:
        df = fetch_history(ticker, args.years)
        entry: dict = {"rows": int(len(df))}
        if not args.probe_only:
            entry["xgb_train"] = train_xgb(df, ticker)
            entry["lstm_train"] = train_lstm(df, ticker)
        entry["probe"] = probe(df, ticker, settings.challenge_signal_threshold)
        report[ticker] = entry
        log.info("%s → %s", ticker, json.dumps(entry["probe"]))

    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    main()
