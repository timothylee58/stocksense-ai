"""SHAP feature-contribution endpoint.

GET /api/explain/{ticker}
    Returns the top-N SHAP feature contributions for the latest prediction.
    Requires a trained XGBoost model (run `make train --ticker TICKER` first).
    Results are cached 5 minutes in Redis (same TTL as predictions).
"""
from __future__ import annotations

import logging
from asyncio import get_event_loop

from fastapi import APIRouter, HTTPException

from app.core.config import get_settings
from app.core.redis_client import cache_get, cache_set

logger = logging.getLogger(__name__)
router = APIRouter()
settings = get_settings()


async def _run_shap(ticker: str) -> dict:
    """Fetch data + compute SHAP in a thread (CPU-bound)."""
    import asyncio

    from app.data.fetcher import fetch_stock_data
    from app.services.xgboost_service import shap_explain
    from app.core.demo_data import get_demo_prediction

    if settings.demo_mode:
        pred = get_demo_prediction(ticker.upper(), ticker.split(".")[-1])
        return {
            "ticker":         ticker.upper(),
            "prediction":     pred["direction"],
            "probability":    pred["confidence"],
            "expected_value": 0.5,
            "top_features": [
                {"feature": sig.split(" —")[0].lower().replace("-", "_"), "value": 0.0, "contribution": round(pred["score"] * 0.2, 4)}
                for sig in pred["signals"]
            ],
            "demo": True,
        }

    df = await fetch_stock_data(ticker, period_years=1)
    if df is None or df.empty:
        raise ValueError(f"No data for {ticker}")

    return await asyncio.to_thread(shap_explain, df, ticker)


@router.get("/explain/{ticker}")
async def explain_prediction(ticker: str):
    """SHAP feature contributions for the latest XGBoost prediction."""
    cache_key = f"explain:{ticker.upper()}"
    cached = await cache_get(cache_key)
    if cached:
        return cached

    try:
        result = await _run_shap(ticker.upper())
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error("SHAP explain failed for %s: %s", ticker, e)
        raise HTTPException(status_code=500, detail=f"SHAP computation failed: {e}")

    await cache_set(cache_key, result, ttl=settings.cache_predict_ttl)
    return result
