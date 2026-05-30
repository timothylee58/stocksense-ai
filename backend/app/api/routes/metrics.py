from fastapi import APIRouter
from app.db.models import PredictionModel, TickerModel

router = APIRouter()


@router.get("/metrics/{ticker}")
def get_ticker_metrics(ticker: str, limit: int = 30):
    """Return last N predictions for a ticker with accuracy summary."""
    ticker = ticker.upper()
    try:
        ticker_row = TickerModel.get(TickerModel.symbol == ticker)
    except TickerModel.DoesNotExist:
        return {"ticker": ticker, "predictions": [], "accuracy": None}

    rows = (
        PredictionModel
        .select()
        .where(PredictionModel.ticker == ticker_row)
        .order_by(PredictionModel.timestamp.desc())
        .limit(limit)
    )
    predictions = [
        {
            "timestamp": str(r.timestamp),
            "signal": r.signal,
            "confidence": r.confidence,
            "current_price": r.current_price,
            "forecast_price": r.forecast_price,
            "model_version": r.model_version,
        }
        for r in rows
    ]
    return {"ticker": ticker, "count": len(predictions), "predictions": predictions}


@router.get("/metrics")
def get_global_metrics():
    """Return total prediction count and list of covered tickers."""
    total = PredictionModel.select().count()
    tickers = [t.symbol for t in TickerModel.select()]
    return {"total_predictions": total, "tickers": tickers}
