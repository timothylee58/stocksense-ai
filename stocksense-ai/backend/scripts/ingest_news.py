#!/usr/bin/env python3
"""Scheduled news ingestion for BursaSense FinBERT sentiment pipeline.

Fetches KLSE-related headlines from NewsAPI, scores them with FinBERT,
and stores results in Redis for the /sentiment endpoint to serve.

Usage:
    # One-shot (runs once and exits):
    python -m scripts.ingest_news

    # Continuous loop (10-minute interval, for production scheduling):
    python -m scripts.ingest_news --loop

    # Dry-run (prints articles, skips Redis write):
    python -m scripts.ingest_news --dry-run

Environment variables required:
    NEWS_API_KEY   — from newsapi.org (free tier: 100 req/day)
    REDIS_URL      — cache target (default: redis://localhost:6379)

Optional:
    DEMO_MODE=true — generates synthetic headlines, no NewsAPI key needed
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import time
from datetime import datetime, timezone

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("ingest_news")

KLSE_QUERIES = [
    "Bursa Malaysia stock",
    "KLSE market",
    "Malaysia economy ringgit",
    "Bank Negara Malaysia",
    "Petronas earnings",
]

DEMO_HEADLINES = [
    {"title": "Maybank reports record Q2 net profit, dividend raised to 58 sen", "source": "The Edge Markets", "sentiment": "positive", "score": 0.91},
    {"title": "KLCI falls 12 points as global risk aversion hits emerging markets", "source": "The Star Business", "sentiment": "negative", "score": -0.74},
    {"title": "Tenaga Nasional secures RM2.4bn solar contract under NEM programme", "source": "Bernama", "sentiment": "positive", "score": 0.85},
    {"title": "Ringgit holds steady at 4.47 ahead of US Fed decision", "source": "Reuters", "sentiment": "neutral", "score": 0.12},
    {"title": "Gamuda wins RM5.8bn Penang LRT package, shares surge 6%", "source": "The Edge Markets", "sentiment": "positive", "score": 0.93},
    {"title": "IHH Healthcare earnings miss estimates on higher staff costs", "source": "Bloomberg", "sentiment": "negative", "score": -0.61},
    {"title": "Bank Negara holds OPR at 3.00%, growth outlook revised upward", "source": "Bernama", "sentiment": "positive", "score": 0.55},
    {"title": "Axiata Group to divest Indonesia tower assets, shares rise", "source": "Reuters", "sentiment": "positive", "score": 0.78},
]


async def _fetch_newsapi(query: str, api_key: str, page_size: int = 10) -> list[dict]:
    """Fetch headlines from NewsAPI for a given query string."""
    try:
        import httpx
        url = "https://newsapi.org/v2/everything"
        params = {
            "q": query,
            "language": "en",
            "sortBy": "publishedAt",
            "pageSize": page_size,
            "apiKey": api_key,
        }
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(url, params=params)
            r.raise_for_status()
            return r.json().get("articles", [])
    except Exception as exc:
        logger.warning("NewsAPI request failed for %r: %s", query, exc)
        return []


def _score_with_finbert(texts: list[str]) -> list[dict]:
    """Run FinBERT inference on a batch of headline texts."""
    try:
        from transformers import pipeline
        pipe = pipeline(
            "text-classification",
            model="ProsusAI/finbert",
            device=-1,          # CPU; set 0 for CUDA
            truncation=True,
            max_length=512,
        )
        results = []
        for text, out in zip(texts, pipe(texts)):
            label = out["label"].lower()     # positive / negative / neutral
            score_raw = out["score"]
            signed = score_raw if label == "positive" else (-score_raw if label == "negative" else 0.0)
            results.append({"text": text, "sentiment": label, "score": round(signed, 4)})
        return results
    except Exception as exc:
        logger.error("FinBERT inference failed: %s", exc)
        return [{"text": t, "sentiment": "neutral", "score": 0.0} for t in texts]


async def run_once(dry_run: bool = False, demo_mode: bool = False) -> None:
    """Fetch, score, and cache one round of news."""
    from app.core.config import get_settings
    settings = get_settings()

    if demo_mode or settings.demo_mode:
        logger.info("Demo mode — using synthetic headlines")
        articles = DEMO_HEADLINES
    else:
        if not settings.news_api_key:
            logger.error("NEWS_API_KEY not set. Set it in .env or use DEMO_MODE=true.")
            sys.exit(1)

        logger.info("Fetching headlines from NewsAPI (%d queries)…", len(KLSE_QUERIES))
        all_articles: list[dict] = []
        for q in KLSE_QUERIES:
            fetched = await _fetch_newsapi(q, settings.news_api_key)
            all_articles.extend(fetched)
            await asyncio.sleep(0.5)    # respect rate limit

        seen: set[str] = set()
        unique = []
        for a in all_articles:
            title = a.get("title", "")
            if title and title not in seen:
                seen.add(title)
                unique.append({"title": title, "source": a.get("source", {}).get("name", ""), "url": a.get("url", "")})
        logger.info("Fetched %d unique headlines", len(unique))

        texts = [a["title"] for a in unique]
        logger.info("Running FinBERT on %d texts…", len(texts))
        scored = _score_with_finbert(texts)
        articles = [
            {**u, "sentiment": s["sentiment"], "score": s["score"]}
            for u, s in zip(unique, scored)
        ]

    payload = {
        "articles": articles,
        "ingested_at": datetime.now(timezone.utc).isoformat(),
        "count": len(articles),
    }

    if dry_run:
        print(json.dumps(payload, indent=2))
        return

    from app.core.redis_client import cache_set
    await cache_set("bursa:sentiment:headlines", payload, ttl=3600)
    logger.info("Stored %d scored articles in Redis (TTL 1h)", len(articles))


async def main() -> None:
    parser = argparse.ArgumentParser(description="BursaSense news ingestion")
    parser.add_argument("--loop", action="store_true", help="Run continuously every 10 minutes")
    parser.add_argument("--dry-run", action="store_true", help="Print output, skip Redis write")
    parser.add_argument("--demo", action="store_true", help="Use synthetic headlines (no API key needed)")
    args = parser.parse_args()

    if args.loop:
        logger.info("Starting continuous ingestion loop (10-min interval)")
        while True:
            await run_once(dry_run=args.dry_run, demo_mode=args.demo)
            logger.info("Sleeping 10 minutes…")
            await asyncio.sleep(600)
    else:
        await run_once(dry_run=args.dry_run, demo_mode=args.demo)


if __name__ == "__main__":
    asyncio.run(main())
