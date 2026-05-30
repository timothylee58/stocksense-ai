#!/usr/bin/env python
"""
Backfill historical data for a ticker into Supabase.
python backfill.py --ticker NVDA --days 365
"""
import argparse
import asyncio
import logging
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


async def backfill(ticker: str, days: int) -> None:
    from app.data.fetcher import fetch_stock_data
    from app.services.isolation_forest import get_anomaly_history_from_df
    from app.core.database import insert_anomaly

    logger.info("Backfilling %s for %d days", ticker, days)
    df = await fetch_stock_data(ticker, period_years=max(2, days // 365))
    records = get_anomaly_history_from_df(df, ticker, days=days)

    for record in records:
        await insert_anomaly(record)

    logger.info("Backfilled %d anomaly records for %s", len(records), ticker)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--days", type=int, default=365)
    args = parser.parse_args()
    asyncio.run(backfill(args.ticker.upper(), args.days))


if __name__ == "__main__":
    main()
