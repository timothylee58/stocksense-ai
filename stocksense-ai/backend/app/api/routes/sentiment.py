"""GET /sentiment/{ticker} — FinBERT sentiment score + headlines."""
from fastapi import APIRouter, HTTPException, Query
from app.services.finbert_service import get_finbert_score
from app.core.database import get_sentiment_history
from app.core.redis_client import cache_get, cache_set

router = APIRouter()


@router.get("/sentiment/{ticker}")
async def get_sentiment(
    ticker: str,
    hours: int = Query(default=24, ge=1, le=168),
):
    ticker = ticker.upper()
    cache_key = f"sentiment:{ticker}:{hours}"

    cached = await cache_get(cache_key)
    if cached:
        return cached

    # Try Supabase first
    db_records = await get_sentiment_history(ticker, hours)
    if db_records:
        latest = db_records[0]
        result = {
            "ticker": ticker,
            "finbert_score": latest.get("finbert_score"),
            "reddit_score": latest.get("reddit_score"),
            "news_count": latest.get("news_count"),
            "top_headlines": latest.get("top_headlines", []),
            "scored_at": latest.get("scored_at"),
            "source": "database",
        }
        await cache_set(cache_key, result, ttl=300)
        return result

    # Fallback: compute live
    try:
        finbert_score, headlines = get_finbert_score(ticker)
        result = {
            "ticker": ticker,
            "finbert_score": finbert_score,
            "reddit_score": 0.0,
            "news_count": len(headlines),
            "top_headlines": headlines[:10],
            "scored_at": None,
            "source": "computed",
        }
        await cache_set(cache_key, result, ttl=300)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Sentiment analysis failed: {e}")
