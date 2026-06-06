"""
LSTM sequence-to-price model (PyTorch).
Trained per ticker; handles iterated 30-day forward forecasting.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from sklearn.preprocessing import MinMaxScaler

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

FEATURE_COLS = [
    "Close", "Volume",
    "rsi", "macd", "macd_signal", "macd_hist",
    "sma_20", "sma_50", "bb_upper", "bb_mid", "bb_lower",
]


# ── Model definition ──────────────────────────────────────────────────────────

class _LSTMNet(nn.Module):
    def __init__(self, n_features: int, hidden: int = 64, layers: int = 2, dropout: float = 0.2):
        super().__init__()
        self.lstm = nn.LSTM(
            n_features, hidden, layers,
            batch_first=True,
            dropout=dropout if layers > 1 else 0.0,
        )
        self.fc = nn.Sequential(
            nn.Linear(hidden, 32),
            nn.ReLU(),
            nn.Linear(32, 1),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        out, _ = self.lstm(x)
        return self.fc(out[:, -1, :]).squeeze(-1)


# ── Public helpers ────────────────────────────────────────────────────────────

def _model_path(ticker: str) -> Path:
    return Path(settings.models_dir) / f"{ticker.upper()}_lstm.pt"


def _scaler_path(ticker: str) -> Path:
    return Path(settings.models_dir) / f"{ticker.upper()}_lstm_scaler.pkl"


def _build_sequences(features: np.ndarray, seq_len: int):
    X, y = [], []
    for i in range(len(features) - seq_len):
        X.append(features[i : i + seq_len])
        y.append(features[i + seq_len, 0])   # predict normalised Close
    return np.array(X, dtype=np.float32), np.array(y, dtype=np.float32)


def train_lstm(df: pd.DataFrame, ticker: str) -> dict:
    """Train LSTM on `df`, save weights + scaler. Returns training metadata."""
    cols = [c for c in FEATURE_COLS if c in df.columns]
    data = df[cols].ffill().bfill().values.astype(np.float32)

    scaler = MinMaxScaler()
    data_scaled = scaler.fit_transform(data)

    seq_len = settings.seq_len
    X, y = _build_sequences(data_scaled, seq_len)
    if len(X) < 10:
        raise ValueError(f"Not enough data to train LSTM for {ticker}")

    split = int(len(X) * 0.85)
    X_tr, y_tr = torch.tensor(X[:split]), torch.tensor(y[:split])
    X_va, y_va = torch.tensor(X[split:]), torch.tensor(y[split:])

    model = _LSTMNet(
        n_features=len(cols),
        hidden=settings.lstm_hidden,
        layers=settings.lstm_layers,
    )
    optimiser = torch.optim.Adam(model.parameters(), lr=settings.lstm_lr)
    # HuberLoss (delta=1.0) down-weights extreme earnings-surprise candles
    # compared to MSE, making the LSTM more robust to outlier price spikes.
    criterion = nn.HuberLoss(delta=1.0)

    best_val, patience, patience_left = float("inf"), 10, 10
    best_state = None

    for epoch in range(settings.lstm_epochs):
        model.train()
        optimiser.zero_grad()
        loss = criterion(model(X_tr), y_tr)
        loss.backward()
        nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        optimiser.step()

        model.eval()
        with torch.no_grad():
            val_loss = criterion(model(X_va), y_va).item()
        if val_loss < best_val:
            best_val = val_loss
            best_state = {k: v.clone() for k, v in model.state_dict().items()}
            patience_left = patience
        else:
            patience_left -= 1
            if patience_left == 0:
                break

    if best_state:
        model.load_state_dict(best_state)

    # Persist
    os.makedirs(settings.models_dir, exist_ok=True)
    torch.save({"state": model.state_dict(), "n_features": len(cols), "cols": cols}, _model_path(ticker))

    import joblib
    joblib.dump(scaler, _scaler_path(ticker))

    logger.info("LSTM trained for %s — best val_loss=%.5f", ticker, best_val)
    return {"epochs_run": epoch + 1, "val_loss": round(best_val, 6)}


def predict_lstm(df: pd.DataFrame, ticker: str, n_days: int = 30) -> tuple[list[float], float]:
    """
    Returns (forecast_prices, confidence).
    forecast_prices: list of n_days future daily closing prices.
    confidence: 0-1 based on recent in-sample accuracy.
    Falls back to momentum model if no trained weights exist.
    """
    path = _model_path(ticker)
    scaler_path = _scaler_path(ticker)

    if not path.exists() or not scaler_path.exists():
        return _momentum_forecast(df, n_days)

    import joblib
    checkpoint = torch.load(path, map_location="cpu", weights_only=False)
    cols = checkpoint["cols"]
    n_feat = checkpoint["n_features"]

    model = _LSTMNet(n_features=n_feat, hidden=settings.lstm_hidden, layers=settings.lstm_layers)
    model.load_state_dict(checkpoint["state"])
    model.eval()

    scaler: MinMaxScaler = joblib.load(scaler_path)

    available = [c for c in cols if c in df.columns]
    if len(available) < n_feat:
        return _momentum_forecast(df, n_days)

    data = df[available].ffill().bfill().values.astype(np.float32)
    data_scaled = scaler.transform(data)

    seq_len = settings.seq_len
    if len(data_scaled) < seq_len:
        return _momentum_forecast(df, n_days)

    # ── iterated forecasting ──
    window = data_scaled[-seq_len:].copy()   # (seq_len, n_features)
    forecasts_scaled = []

    with torch.no_grad():
        for _ in range(n_days):
            x = torch.tensor(window[np.newaxis]).float()
            pred_norm = model(x).item()
            forecasts_scaled.append(pred_norm)

            # Build next row: shift window, set Close to prediction, keep others as last row
            new_row = window[-1].copy()
            new_row[0] = pred_norm          # index 0 = Close (after scaling)
            window = np.vstack([window[1:], new_row])

    # Denormalise Close column only
    dummy = np.zeros((len(forecasts_scaled), n_feat))
    dummy[:, 0] = forecasts_scaled
    prices = scaler.inverse_transform(dummy)[:, 0].tolist()

    # Confidence: inverse of recent normalised RMSE
    seq = torch.tensor(data_scaled[-(seq_len + 30) : -n_days][np.newaxis]).float()
    if seq.shape[1] >= seq_len:
        with torch.no_grad():
            in_sample = model(seq).item()
        actual_norm = data_scaled[-n_days, 0]
        err = abs(in_sample - actual_norm)
        confidence = float(max(0.4, min(0.98, 1.0 - err * 5)))
    else:
        confidence = 0.70

    return prices, confidence


def _momentum_forecast(df: pd.DataFrame, n_days: int) -> tuple[list[float], float]:
    """Fallback: linear extrapolation on 30-day momentum + mean-reversion."""
    close = df["Close"].squeeze().values.astype(float)
    last = close[-1]

    # 30-day trend slope (normalised)
    window = close[-30:]
    xs = np.arange(len(window))
    slope, _ = np.polyfit(xs, window, 1)

    prices = []
    price = last
    for i in range(1, n_days + 1):
        # Decay slope over time (mean reversion)
        decay = max(0.3, 1.0 - i * 0.02)
        price = price + slope * decay + np.random.normal(0, last * 0.003)
        prices.append(float(price))

    return prices, 0.55
