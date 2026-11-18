---
name: market-research
description: Refresh news sentiment for the watchlist before a trading cycle. Use at the start of each cycle or when asked what the news says about a ticker.
---

# Market research

1. From `stocksense-ai/backend`, run `python -m scripts.ingest_news --dry-run` to preview
   (add `--demo` if no `NEWS_API_KEY`). Drop `--dry-run` to write scores to Redis.
2. Report per ticker: headline count and the signed FinBERT score (positive minus negative).
3. Flag any ticker with strongly negative sentiment (score below -0.3) to the risk officer.

Rules
- Never fabricate headlines. If the fetch fails, say so and continue with sentiment missing.
- Research informs the signal; it never places orders.
