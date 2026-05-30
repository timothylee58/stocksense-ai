import os
import time
import torch
import torch.nn as nn
import joblib
import numpy as np
from sklearn.preprocessing import StandardScaler
from app.data.fetcher import get_full_dataset
from app.ml.models.lstm_model import LSTMRegressor
from app.ml.models.xgb_model import train_xgb, save_xgb

MODEL_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../models"))
os.makedirs(MODEL_DIR, exist_ok=True)

FEATURE_COLS = ['Close', 'RSI', 'SMA_20', 'SMA_50']


def train_model(ticker: str = "AAPL", epochs: int = 100) -> dict:
    """
    Train LSTM for ticker, save versioned artifacts, return metadata dict.
    Saves:
      {ticker}_lstm_v{ts}.pth  — versioned model weights
      {ticker}_scaler_v{ts}.pkl — versioned scaler
      {ticker}_lstm.pth         — always points to latest (overwritten)
      {ticker}_scaler.pkl       — always points to latest (overwritten)
    Returns:
      {"ticker": ..., "version": ..., "model_path": ..., "scaler_path": ...}
    """
    print(f"[train] Fetching data for {ticker}...")
    df = get_full_dataset(ticker)

    X = df[FEATURE_COLS].values
    y = df['Target'].values

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    X_tensor = torch.tensor(X_scaled, dtype=torch.float32).unsqueeze(1)
    y_tensor = torch.tensor(y, dtype=torch.float32).unsqueeze(1)

    model = LSTMRegressor(input_dim=len(FEATURE_COLS), hidden_dim=64, num_layers=2)
    criterion = nn.BCEWithLogitsLoss()
    optimizer = torch.optim.Adam(model.parameters(), lr=0.001)

    print(f"[train] Training LSTM for {ticker} over {epochs} epochs...")
    for epoch in range(epochs):
        model.train()
        optimizer.zero_grad()
        outputs = model(X_tensor)
        loss = criterion(outputs, y_tensor)
        loss.backward()
        optimizer.step()
        if (epoch + 1) % 10 == 0:
            print(f"  Epoch [{epoch+1}/{epochs}], Loss: {loss.item():.4f}")

    ts = int(time.time())
    version = f"v{ts}"

    # Versioned artifacts
    versioned_model = os.path.join(MODEL_DIR, f"{ticker}_lstm_{version}.pth")
    versioned_scaler = os.path.join(MODEL_DIR, f"{ticker}_scaler_{version}.pkl")
    torch.save(model.state_dict(), versioned_model)
    joblib.dump(scaler, versioned_scaler)

    # Latest aliases (overwrite)
    latest_model = os.path.join(MODEL_DIR, f"{ticker}_lstm.pth")
    latest_scaler = os.path.join(MODEL_DIR, f"{ticker}_scaler.pkl")
    torch.save(model.state_dict(), latest_model)
    joblib.dump(scaler, latest_scaler)

    print(f"[train] Done. version={version}, model={latest_model}")

    # Also train XGBoost
    print(f"[train] Training XGBoost for {ticker}...")
    xgb_model, xgb_scaler = train_xgb(df)
    save_xgb(xgb_model, xgb_scaler, ticker, version)
    print(f"[train] XGBoost done.")

    return {
        "ticker": ticker,
        "version": version,
        "model_path": latest_model,
        "scaler_path": latest_scaler,
        "xgb_trained": True,
    }


if __name__ == "__main__":
    train_model("AAPL")
