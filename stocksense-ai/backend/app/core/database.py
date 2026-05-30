"""Supabase async client singleton."""
from __future__ import annotations
import logging
from functools import lru_cache
from app.core.config import get_settings

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_supabase_client():
    settings = get_settings()
    if not settings.supabase_url or not settings.supabase_service_key:
        logger.warning("Supabase not configured — persistence disabled")
        return None
    try:
        from supabase import create_client
        return create_client(settings.supabase_url, settings.supabase_service_key)
    except Exception as e:
        logger.error("Supabase init failed: %s", e)
        return None


async def insert_prediction(record: dict) -> None:
    client = get_supabase_client()
    if client is None:
        return
    try:
        client.table("predictions").insert(record).execute()
    except Exception as e:
        logger.error("Supabase insert_prediction failed: %s", e)


async def insert_anomaly(record: dict) -> None:
    client = get_supabase_client()
    if client is None:
        return
    try:
        client.table("anomalies").insert(record).execute()
    except Exception as e:
        logger.error("Supabase insert_anomaly failed: %s", e)


async def insert_sentiment(record: dict) -> None:
    client = get_supabase_client()
    if client is None:
        return
    try:
        client.table("sentiment_scores").insert(record).execute()
    except Exception as e:
        logger.error("Supabase insert_sentiment failed: %s", e)


async def get_anomaly_history(ticker: str, days: int = 30) -> list[dict]:
    client = get_supabase_client()
    if client is None:
        return []
    try:
        from datetime import datetime, timedelta
        cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
        result = (
            client.table("anomalies")
            .select("*")
            .eq("ticker", ticker.upper())
            .gte("trading_date", cutoff[:10])
            .order("trading_date", desc=True)
            .limit(100)
            .execute()
        )
        return result.data or []
    except Exception as e:
        logger.error("Supabase get_anomaly_history failed: %s", e)
        return []


async def get_sentiment_history(ticker: str, hours: int = 24) -> list[dict]:
    client = get_supabase_client()
    if client is None:
        return []
    try:
        from datetime import datetime, timedelta
        cutoff = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
        result = (
            client.table("sentiment_scores")
            .select("*")
            .eq("ticker", ticker.upper())
            .gte("scored_at", cutoff)
            .order("scored_at", desc=True)
            .limit(10)
            .execute()
        )
        return result.data or []
    except Exception as e:
        logger.error("Supabase get_sentiment_history failed: %s", e)
        return []
