from fastapi import APIRouter, BackgroundTasks, HTTPException
from app.ml.train import train_model

router = APIRouter()

_running: set[str] = set()


@router.post("/train/{ticker}")
async def trigger_training(ticker: str, background_tasks: BackgroundTasks):
    """Trigger background model training for a ticker."""
    ticker = ticker.upper()
    if ticker in _running:
        raise HTTPException(status_code=409, detail=f"Training already in progress for {ticker}")

    def _run():
        _running.add(ticker)
        try:
            train_model(ticker)
        finally:
            _running.discard(ticker)

    background_tasks.add_task(_run)
    return {"status": "training_started", "ticker": ticker}


@router.get("/train/status")
async def training_status():
    """Return set of tickers currently being trained."""
    return {"training": list(_running)}
