---
name: market-research
description: Refresh market-wide news sentiment context before a trading cycle. Use at the start of each cycle or when asked what the news says.
---

# Market research

1. From `stocksense-ai/backend`, preview with `python -m scripts.ingest_news --dry-run`. It prints
   a JSON payload: every headline with its own `sentiment` label and signed `score`, plus a count.
   It prints no overall score; summarise from the per-headline values if asked.
   Drop `--dry-run` to write the scored headlines to Redis.
2. It needs `NEWS_API_KEY`. If the key is missing, report that sentiment is unavailable.
   Do **not** use `--demo`. Also check `DEMO_MODE`: when it is true the script uses
   synthetic headlines even without `--demo`, so label any such output as synthetic and
   never write it to the live cache.
   If FinBERT fails to load, every headline gets the same placeholder (all neutral, 0.0): treat
   that as sentiment unavailable, not as a neutral market.
3. The headlines are market-wide (KLSE-oriented queries) and are not attributed to individual
   watchlist tickers.

Rules
- Never fabricate headlines. If the fetch fails, say so and continue with sentiment missing.
- Output is context for the human operator. It is not an input to the signal or to
  `RiskManager` today; do not claim otherwise.
- This skill never places orders.
