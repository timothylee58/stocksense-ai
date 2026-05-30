"""FinBERT sentiment analysis — ProsusAI/finbert, loaded once at startup."""
from __future__ import annotations
import logging
import threading
from typing import Optional

logger = logging.getLogger(__name__)
_lock = threading.Lock()
_model = None
_tokenizer = None


def _load_finbert():
    global _model, _tokenizer
    with _lock:
        if _model is not None:
            return
        try:
            from transformers import BertTokenizer, BertForSequenceClassification
            import torch
            logger.info("Loading ProsusAI/finbert...")
            _tokenizer = BertTokenizer.from_pretrained("ProsusAI/finbert")
            _model = BertForSequenceClassification.from_pretrained("ProsusAI/finbert")
            _model.eval()
            logger.info("FinBERT loaded successfully")
        except Exception as e:
            logger.error("FinBERT load failed: %s", e)


def score_headlines(texts: list[str]) -> float:
    """
    Score a list of headlines.
    Returns aggregated sentiment score in [-1, 1].
    positive - negative = net sentiment.
    Falls back to 0.0 if FinBERT unavailable.
    """
    if not texts:
        return 0.0

    _load_finbert()
    if _model is None or _tokenizer is None:
        return 0.0

    try:
        import torch
        scores = []
        for text in texts[:20]:  # cap at 20 headlines per call
            inputs = _tokenizer(
                text,
                return_tensors="pt",
                truncation=True,
                max_length=512,
                padding=True,
            )
            with torch.no_grad():
                outputs = _model(**inputs)
            probs = torch.softmax(outputs.logits, dim=1)[0]
            # ProsusAI/finbert label order: positive=0, negative=1, neutral=2
            pos = probs[0].item()
            neg = probs[1].item()
            score = pos - neg  # in [-1, 1]
            scores.append(score)
        return round(float(sum(scores) / len(scores)), 4) if scores else 0.0
    except Exception as e:
        logger.error("FinBERT inference failed: %s", e)
        return 0.0


def get_finbert_score(ticker: str) -> tuple[float, list[dict]]:
    """
    Fetch recent news for ticker and return (finbert_score, headlines).
    Uses NewsAPI if configured, else returns (0.0, []).
    """
    from app.core.config import get_settings
    settings = get_settings()

    headlines = []
    if settings.news_api_key:
        try:
            from newsapi import NewsApiClient
            newsapi = NewsApiClient(api_key=settings.news_api_key)
            articles = newsapi.get_everything(
                q=ticker,
                language="en",
                sort_by="publishedAt",
                page_size=20,
            )
            headlines = [
                {
                    "title": a["title"],
                    "source": a["source"]["name"],
                    "url": a["url"],
                }
                for a in articles.get("articles", [])
                if a.get("title")
            ]
        except Exception as e:
            logger.warning("NewsAPI fetch failed for %s: %s", ticker, e)

    texts = [h["title"] for h in headlines]
    score = score_headlines(texts)

    # Add aggregated score to each headline dict
    for h in headlines:
        h["score"] = score

    return score, headlines
