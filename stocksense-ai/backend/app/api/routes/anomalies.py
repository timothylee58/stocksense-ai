"""GET /anomalies/{ticker} — Isolation Forest anomaly history."""
from fastapi import APIRouter, HTTPException, Query
from app.data.fetcher import fetch_stock_data
from app.services.isolation_forest import get_anomaly_history_from_df
from app.core.database import get_anomaly_history
from app.core.redis_client import cache_get, cache_set

router = APIRouter()


@router.get("/anomalies/{ticker}")
async def get_anomalies(
    ticker: str,
    days: int = Query(default=30, ge=7, le=365),
):
    """
    Return Isolation Forest anomaly history for a ticker.
    Tries Supabase first, falls back to computing from live data.
    """
    ticker = ticker.upper()
    cache_key = f"anomalies:{ticker}:{days}"

    cached = await cache_get(cache_key)
    if cached:
        return cached

    # Try Supabase first
    db_records = await get_anomaly_history(ticker, days)
    if db_records:
        result = {"ticker": ticker, "days": days, "records": db_records, "source": "database"}
        await cache_set(cache_key, result, ttl=300)
        return result

    # Fallback: compute live
    try:
        df = await fetch_stock_data(ticker)
        records = get_anomaly_history_from_df(df, ticker, days=days)
        result = {"ticker": ticker, "days": days, "records": records, "source": "computed"}
        await cache_set(cache_key, result, ttl=300)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Anomaly detection failed: {e}")
