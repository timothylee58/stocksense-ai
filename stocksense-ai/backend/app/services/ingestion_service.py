"""Daily ingestion: fetch OHLCV + news + sentiment, store in Supabase + ClickHouse."""
from __future__ import annotations
import asyncio
import logging
from datetime import datetime, timezone

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


def _sentiment_label(score: float) -> str:
    if score > 0.1:
        return "positive"
    if score < -0.1:
        return "negative"
    return "neutral"


async def ingest_ticker(ticker: str) -> None:
    """Ingest one ticker: fetch data, run anomaly detection, score sentiment, persist."""
    logger.info("Ingesting %s...", ticker)
    try:
        from app.data.fetcher import fetch_stock_data
        from app.services.isolation_forest import get_anomaly_history_from_df
        from app.services.finbert_service import get_finbert_score
        from app.core.database import insert_anomaly, insert_sentiment
        from app.core.ch_store import ch_write_sentiment

        # fetch_stock_data already writes OHLCV to ClickHouse after yfinance call
        df = await fetch_stock_data(ticker, period_years=2)

        # Anomaly detection → Supabase
        anomaly_records = get_anomaly_history_from_df(df, ticker, days=5)
        for record in anomaly_records:
            await insert_anomaly(record)

        # Sentiment → Supabase (aggregate) + ClickHouse (per-headline)
        finbert_score, headlines = get_finbert_score(ticker)
        await insert_sentiment({
            "ticker": ticker,
            "finbert_score": finbert_score,
            "news_count": len(headlines),
            "top_headlines": headlines[:10],
        })

        if headlines:
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            label = _sentiment_label(finbert_score)
            ch_records = [
                {
                    "published_at": now,
                    "headline": h,
                    "source": "finbert",
                    "sentiment": label,
                    "score": finbert_score,
                }
                for h in headlines[:10]
            ]
            await asyncio.to_thread(ch_write_sentiment, ticker, ch_records)

        logger.info("Ingestion complete for %s", ticker)
    except Exception as e:
        logger.error("Ingestion failed for %s: %s", ticker, e)


async def run_daily_ingestion() -> None:
    """Ingest all configured tickers. Called by APScheduler at 9AM MYT."""
    logger.info("Daily ingestion started for %s", settings.default_tickers)
    for ticker in settings.default_tickers:
        await ingest_ticker(ticker)
    logger.info("Daily ingestion complete")
