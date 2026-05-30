"""XGBoost wrapper for StockSense AI."""
import os
import joblib
import numpy as np
import xgboost as xgb
from sklearn.preprocessing import StandardScaler

MODEL_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../models"))
FEATURE_COLS = ['Close', 'RSI', 'SMA_20', 'SMA_50']


def train_xgb(df) -> tuple:
    """Train XGBoost classifier and return (model, scaler)."""
    X = df[FEATURE_COLS].values
    y = df['Target'].values
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    model = xgb.XGBClassifier(
        n_estimators=100,
        max_depth=4,
        learning_rate=0.1,
        use_label_encoder=False,
        eval_metric='logloss',
        verbosity=0,
    )
    model.fit(X_scaled, y)
    return model, scaler


def save_xgb(model, scaler, ticker: str, version: str = "latest") -> tuple[str, str]:
    os.makedirs(MODEL_DIR, exist_ok=True)
    model_path = os.path.join(MODEL_DIR, f"{ticker}_xgb.pkl")
    scaler_path = os.path.join(MODEL_DIR, f"{ticker}_xgb_scaler.pkl")
    joblib.dump(model, model_path)
    joblib.dump(scaler, scaler_path)
    return model_path, scaler_path


def load_xgb(ticker: str):
    """Return (model, scaler) or (None, None) if not found."""
    model_path = os.path.join(MODEL_DIR, f"{ticker}_xgb.pkl")
    scaler_path = os.path.join(MODEL_DIR, f"{ticker}_xgb_scaler.pkl")
    if not os.path.exists(model_path) or not os.path.exists(scaler_path):
        return None, None
    return joblib.load(model_path), joblib.load(scaler_path)


def predict_xgb(model, scaler, df) -> float:
    """Return probability of price going up (0-1)."""
    last_row = df[FEATURE_COLS].iloc[-1].values.reshape(1, -1)
    scaled = scaler.transform(last_row)
    prob = model.predict_proba(scaled)[0][1]
    return float(prob)
