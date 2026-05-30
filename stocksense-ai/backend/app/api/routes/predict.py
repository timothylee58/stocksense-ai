from fastapi import APIRouter, HTTPException
from app.ml.predictor import run_prediction

router = APIRouter()


@router.get("/predict/{ticker}")
async def predict(ticker: str):
    try:
        return await run_prediction(ticker.upper())
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Prediction failed: {e}")


@router.get("/predict/batch/{tickers}")
async def predict_batch(tickers: str):
    """Comma-separated list of tickers, e.g. AAPL,NVDA,MSFT"""
    ticker_list = [t.strip().upper() for t in tickers.split(",") if t.strip()][:10]
    results = {}
    for ticker in ticker_list:
        try:
            results[ticker] = await run_prediction(ticker)
        except Exception as e:
            results[ticker] = {"error": str(e)}
    return results
