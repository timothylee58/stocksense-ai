"""Daily ingestion: fetch OHLCV + news + sentiment, store in Supabase."""
from __future__ import annotations
import logging
from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


async def ingest_ticker(ticker: str) -> None:
    """Ingest one ticker: fetch data, run anomaly detection, score sentiment, persist."""
    logger.info("Ingesting %s...", ticker)
    try:
        from app.data.fetcher import fetch_stock_data
        from app.services.isolation_forest import get_anomaly_history_from_df
        from app.services.finbert_service import get_finbert_score
        from app.core.database import insert_anomaly, insert_sentiment

        df = await fetch_stock_data(ticker, period_years=2)

        # Anomaly detection for recent days
        anomaly_records = get_anomaly_history_from_df(df, ticker, days=5)
        for record in anomaly_records:
            await insert_anomaly(record)

        # Sentiment
        finbert_score, headlines = get_finbert_score(ticker)
        await insert_sentiment({
            "ticker": ticker,
            "finbert_score": finbert_score,
            "news_count": len(headlines),
            "top_headlines": headlines[:10],
        })

        logger.info("Ingestion complete for %s", ticker)
    except Exception as e:
        logger.error("Ingestion failed for %s: %s", ticker, e)


async def run_daily_ingestion() -> None:
    """Ingest all configured tickers. Called by APScheduler at 9AM MYT."""
    logger.info("Daily ingestion started for %s", settings.default_tickers)
    for ticker in settings.default_tickers:
        await ingest_ticker(ticker)
    logger.info("Daily ingestion complete")
