"""
Orchestrates the full 3-stage ML pipeline:
  Stage 1: Isolation Forest → anomaly_score, is_anomaly
  Stage 2: XGBoost → prob_up, prob_down
  Stage 3: LR meta-learner → signal, confidence
"""
from __future__ import annotations
import logging

from app.data.fetcher import fetch_stock_data
from app.services.isolation_forest import predict_anomalies
from app.services.xgboost_service import predict_xgboost
from app.services.lr_meta_service import predict_lr_meta
from app.services.finbert_service import get_finbert_score
from app.core.redis_client import cache_get, cache_set
from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


async def run_full_pipeline(ticker: str, force_refresh: bool = False) -> dict:
    """
    Full 3-stage inference pipeline.
    Returns a dict with all prediction fields + anomaly + sentiment.
    Cached in Redis (TTL from settings).
    """
    cache_key = f"pipeline:{ticker.upper()}"

    if not force_refresh:
        cached = await cache_get(cache_key)
        if cached:
            return cached

    ticker = ticker.upper()

    # Fetch enriched OHLCV
    df = await fetch_stock_data(ticker)
    current_price = float(df["Close"].squeeze().iloc[-1])

    # ── Stage 1: Isolation Forest ──────────────────────────────────────────
    df_with_anomaly = predict_anomalies(df, ticker)
    last = df_with_anomaly.iloc[-1]
    anomaly_score = float(last.get("anomaly_score", 0) if hasattr(last, "get") else getattr(last, "anomaly_score", 0))
    is_anomaly = bool(last.get("is_anomaly", False) if hasattr(last, "get") else getattr(last, "is_anomaly", False))

    # ── Stage 2: XGBoost ──────────────────────────────────────────────────
    # Inject anomaly_score as feature into df before XGBoost
    df_with_anomaly["anomaly_score"] = df_with_anomaly.get("anomaly_score", 0)
    prob_up, prob_down = predict_xgboost(df_with_anomaly, ticker)

    # ── FinBERT Sentiment ─────────────────────────────────────────────────
    finbert_score, headlines = get_finbert_score(ticker)
    reddit_sentiment = 0.0   # Placeholder — PRAW integration in ingestion_service
    news_volume_norm = min(1.0, len(headlines) / 20.0)

    # ── Stage 3: LR Meta-learner ──────────────────────────────────────────
    signal, confidence = predict_lr_meta(
        xgb_prob_up=prob_up,
        xgb_prob_down=prob_down,
        anomaly_score=anomaly_score,
        is_anomaly=is_anomaly,
        finbert_score=finbert_score,
        reddit_sentiment=reddit_sentiment,
        news_volume_norm=news_volume_norm,
        ticker=ticker,
    )

    result = {
        "ticker": ticker,
        "current_price": round(current_price, 2),
        "signal": signal,
        "confidence": confidence,
        "xgb_prob_up": round(prob_up, 4),
        "xgb_prob_down": round(prob_down, 4),
        "is_anomaly": is_anomaly,
        "anomaly_score": round(anomaly_score, 4),
        "finbert_score": finbert_score,
        "reddit_sentiment": reddit_sentiment,
        "news_volume": len(headlines),
        "top_headlines": headlines[:5],
    }

    await cache_set(cache_key, result, settings.cache_predict_ttl)

    # Persist to Supabase (non-blocking, best-effort)
    try:
        from app.core.database import insert_prediction
        await insert_prediction({
            "ticker": ticker,
            "signal": signal,
            "confidence": confidence,
            "direction": "UP" if signal == "BUY" else ("DOWN" if signal == "SELL" else "NEUTRAL"),
            "xgb_prob_up": prob_up,
            "lr_prob_up": prob_up,  # simplified until LR trained
            "is_anomaly": is_anomaly,
            "anomaly_score": anomaly_score,
        })
    except Exception as e:
        logger.debug("Prediction persistence failed (non-fatal): %s", e)

    return result
