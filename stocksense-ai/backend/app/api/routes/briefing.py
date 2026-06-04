"""GET /briefing/{ticker} — AI-generated structured stock briefing."""
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from app.core.redis_client import cache_get, cache_set
from app.ml.predictor import run_prediction

router = APIRouter()

_BRIEFING_TTL = 3600  # 1 hour — briefings are stable within a trading session


@router.get("/briefing/{ticker}")
async def get_briefing(ticker: str):
    ticker = ticker.upper()
    cache_key = f"briefing:{ticker}"

    cached = await cache_get(cache_key)
    if cached:
        return cached

    # Re-use prediction data (hits Redis cache if already computed)
    try:
        prediction = await run_prediction(ticker)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Prediction data unavailable: {e}")

    try:
        from app.services.briefing_service import generate_briefing
        briefing = generate_briefing(ticker, prediction)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Briefing generation failed: {e}")

    result = {
        "ticker": ticker,
        "company": prediction.get("name", ticker),
        "sector": prediction.get("sector", ""),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        **briefing,
    }

    await cache_set(cache_key, result, _BRIEFING_TTL)
    return result
