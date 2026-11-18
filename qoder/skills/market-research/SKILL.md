---
name: market-research
description: Refresh news sentiment for the watchlist before a trading cycle. Use at the start of each cycle or when asked what the news says about a ticker.
---

# Market research

1. From `stocksense-ai/backend`, run `python -m scripts.ingest_news --dry-run` to preview
   Drop `--dry-run` to write scores to Redis. Needs `NEWS_API_KEY`. If it is missing, report
   that sentiment is unavailable; do **not** use `--demo`, which writes synthetic headlines
   and scores to the live cache.
2. Report the overall headline count and signed FinBERT score it prints. The script scores
   general market headlines; it does not attribute news to individual watchlist tickers.
3. Treat the result as market-wide context for the human operator. It is not an input to the
   signal or to `RiskManager` today; do not claim otherwise.

Rules
- Never fabricate headlines. If the fetch fails, say so and continue with sentiment missing.
- Research informs the signal; it never places orders.
