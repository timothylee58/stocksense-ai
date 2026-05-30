from fastapi import APIRouter, HTTPException
import os, joblib, torch, numpy as np
from app.data.fetcher import get_full_dataset, get_chart_data
from app.ml.models.lstm_model import LSTMRegressor
from app.ml.models.xgb_model import load_xgb, predict_xgb
from app.core.cache import cache_get_json, cache_set_json

router = APIRouter()

PREDICTION_TTL = 5 * 60  # 5 minutes

MODEL_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../models"))
FEATURE_COLS = ['Close', 'RSI', 'SMA_20', 'SMA_50']
INPUT_DIM = len(FEATURE_COLS)

def _load_model(ticker: str):
    model_path = os.path.join(MODEL_DIR, f"{ticker}_lstm.pth")
    scaler_path = os.path.join(MODEL_DIR, f"{ticker}_scaler.pkl")
    if not os.path.exists(model_path) or not os.path.exists(scaler_path):
        return None, None
    model = LSTMRegressor(input_dim=INPUT_DIM, hidden_dim=64, num_layers=2)
    model.load_state_dict(torch.load(model_path, map_location="cpu"))
    model.eval()
    scaler = joblib.load(scaler_path)
    return model, scaler

def _run_inference(model, scaler, df):
    """Returns (signal, confidence, forecast_price)."""
    last_row = df[FEATURE_COLS].iloc[-1].values.reshape(1, -1)
    scaled = scaler.transform(last_row)
    x = torch.tensor(scaled, dtype=torch.float32).unsqueeze(1)
    with torch.no_grad():
        logit = model(x).item()
    prob = torch.sigmoid(torch.tensor(logit)).item()
    if prob > 0.6:
        signal = "BUY"
    elif prob < 0.4:
        signal = "SELL"
    else:
        signal = "HOLD"
    current_price = float(df['Close'].iloc[-1])
    # Simple forecast: price * (1 + scaled_delta)
    delta = (prob - 0.5) * 0.04
    forecast_price = round(current_price * (1 + delta), 2)
    return signal, round(prob, 4), forecast_price

@router.get("/predict/{ticker}")
async def get_prediction(ticker: str):
    ticker = ticker.upper()
    cache_key = f"cache:prediction:{ticker}"
    cached = cache_get_json(cache_key)
    if cached:
        return cached
    try:
        df = get_full_dataset(ticker)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to fetch data for {ticker}: {str(e)}")

    if df.empty:
        raise HTTPException(status_code=404, detail=f"No data found for ticker {ticker}")

    current_price = float(df['Close'].iloc[-1])
    chart_data = get_chart_data(df, ticker)

    # RSI/MACD from latest row
    rsi = round(float(df['RSI'].iloc[-1]), 2) if 'RSI' in df.columns else None
    macd = round(float(df['MACD'].iloc[-1]), 4) if 'MACD' in df.columns else None
    macd_signal_val = round(float(df['MACD_Signal'].iloc[-1]), 4) if 'MACD_Signal' in df.columns else None

    model, scaler = _load_model(ticker)
    xgb_model, xgb_scaler = load_xgb(ticker)
    if model is None:
        signal = "BUY" if rsi and rsi < 70 else "HOLD"
        confidence = 0.6
        forecast_price = round(current_price * 1.01, 2)
        model_used = "rule_based"
    else:
        lstm_signal, lstm_prob, forecast_price = _run_inference(model, scaler, df)
        if xgb_model is not None:
            xgb_prob = predict_xgb(xgb_model, xgb_scaler, df)
            ensemble_prob = 0.6 * lstm_prob + 0.4 * xgb_prob
            model_used = "lstm_xgb_ensemble"
        else:
            ensemble_prob = lstm_prob
            model_used = "lstm"
        confidence = round(ensemble_prob, 4)
        if ensemble_prob > 0.6:
            signal = "BUY"
        elif ensemble_prob < 0.4:
            signal = "SELL"
        else:
            signal = "HOLD"
        delta = (ensemble_prob - 0.5) * 0.04
        forecast_price = round(current_price * (1 + delta), 2)

    result = {
        "ticker": ticker,
        "current_price": current_price,
        "forecast_price": forecast_price,
        "signal": signal,
        "confidence": confidence,
        "model_used": model_used,
        "sentiment_score": 0.5,  # Placeholder until FinBERT integrated
        "rsi": rsi,
        "macd": macd,
        "macd_signal": macd_signal_val,
        "chart_data": chart_data,
    }
    cache_set_json(cache_key, result, PREDICTION_TTL)

    # Persist to DB (best-effort)
    try:
        from app.db.models import TickerModel, PredictionModel
        ticker_row, _ = TickerModel.get_or_create(symbol=ticker)
        PredictionModel.create(
            ticker=ticker_row,
            signal=result["signal"],
            confidence=result["confidence"],
            current_price=result["current_price"],
            forecast_price=result["forecast_price"],
            sentiment_score=result["sentiment_score"],
        )
    except Exception:
        pass  # Never let DB errors break the API

    return result
