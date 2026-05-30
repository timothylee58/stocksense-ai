import asyncio
import logging
from fastapi import APIRouter, BackgroundTasks, HTTPException

from app.data.fetcher import fetch_stock_data
from app.ml.models.lstm import train_lstm
from app.ml.models.xgb_model import train_xgb
from app.core.redis_client import cache_delete
from app.core.stocks import get_all_tickers

logger = logging.getLogger(__name__)
router = APIRouter()

_training_status: dict[str, str] = {}   # ticker -> "training" | "done" | "error: ..."


async def _train_all_models(ticker: str):
    _training_status[ticker] = "training"
    try:
        df = await fetch_stock_data(ticker)
        loop = asyncio.get_event_loop()

        lstm_meta = await loop.run_in_executor(None, train_lstm, df, ticker)
        xgb_meta  = await loop.run_in_executor(None, train_xgb, df, ticker)

        # Bust the prediction cache so next /predict returns fresh results
        await cache_delete(f"prediction:{ticker}")
        _training_status[ticker] = "done"
        logger.info("Training complete for %s — %s | %s", ticker, lstm_meta, xgb_meta)
    except Exception as exc:
        _training_status[ticker] = f"error: {exc}"
        logger.error("Training failed for %s: %s", ticker, exc)


@router.post("/train/{ticker}")
async def train(ticker: str, background_tasks: BackgroundTasks):
    t = ticker.upper()
    if _training_status.get(t) == "training":
        return {"status": "already_training", "ticker": t}
    background_tasks.add_task(_train_all_models, t)
    return {"status": "started", "ticker": t, "message": "Training LSTM + XGBoost in background"}


@router.post("/train/all/batch")
async def train_all(background_tasks: BackgroundTasks):
    """Train all 15 stocks in the universe (runs in background)."""
    tickers = get_all_tickers()
    for t in tickers:
        if _training_status.get(t) != "training":
            background_tasks.add_task(_train_all_models, t)
    return {"status": "started", "tickers": tickers}


@router.get("/train/status/{ticker}")
async def training_status(ticker: str):
    t = ticker.upper()
    status = _training_status.get(t, "not_started")
    return {"ticker": t, "status": status}
