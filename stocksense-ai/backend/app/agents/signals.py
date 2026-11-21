"""Pure signal and sizing helpers for the agent run loop.

No I/O here, so the same functions are used by the runtime, the tests and any
replay of the journal.  Weights follow PRD v0.2: XGBoost 0.5 / FinBERT 0.3 /
LSTM 0.2.
"""
from __future__ import annotations

import hashlib
import json
import math
from typing import Iterable

import pandas as pd

from app.agents.artifacts import (
    Bar,
    Direction,
    ProvenanceRef,
    SentimentSignal,
    TechnicalSignal,
)
from app.data.fetcher import add_indicators
from app.schemas.risk import OrderIntent

# Documented PRD v0.2 ensemble weights.  Changing them changes behaviour and
# must be recorded in docs/ROLLOUT.md.
ENSEMBLE_WEIGHTS = {"xgboost": 0.5, "finbert": 0.3, "lstm": 0.2}
MIN_BARS = 60


def _finite(value) -> float | None:
    try:
        f = float(value)
        return f if math.isfinite(f) else None
    except (TypeError, ValueError):
        return None


def bars_to_frame(bars: Iterable[Bar]) -> pd.DataFrame:
    items = list(bars)
    rows = [
        {
            "Open": b.open,
            "High": b.high,
            "Low": b.low,
            "Close": b.close,
            "Volume": b.volume,
        }
        for b in items
    ]
    index = pd.DatetimeIndex([b.ts for b in items])
    return pd.DataFrame(rows, index=index)


def technical_signal(
    symbol: str,
    xgb_signal: str,
    xgb_confidence: float,
    bars: list[Bar],
    dataset_ref: str,
    dataset_sha256: str = "",
) -> TechnicalSignal:
    provenance = [ProvenanceRef(kind="dataset", ref=dataset_ref, sha256=dataset_sha256)]
    if len(bars) < MIN_BARS:
        return TechnicalSignal(
            symbol=symbol,
            direction=Direction.NEUTRAL,
            confidence=0.0,
            status="insufficient_data",
            provenance=provenance,
        )

    df = add_indicators(bars_to_frame(bars))
    last = df.iloc[-1]
    features = {
        k: v
        for k in ("rsi", "macd", "macd_signal", "sma_20", "sma_50", "bb_upper", "bb_lower", "atr_14")
        if (v := _finite(last.get(k))) is not None
    }
    direction = {
        "BUY": Direction.UP,
        "SELL": Direction.DOWN,
    }.get(str(xgb_signal).upper(), Direction.NEUTRAL)
    return TechnicalSignal(
        symbol=symbol,
        features=features,
        direction=direction,
        confidence=round(max(0.0, min(1.0, float(xgb_confidence))), 4),
        provenance=provenance,
    )


def sentiment_signal(
    symbol: str,
    score: float,
    headlines: list[str],
    news_ref: str = "news_search",
) -> SentimentSignal:
    provenance = [ProvenanceRef(kind="sentiment", ref=news_ref)]
    if not headlines:
        return SentimentSignal(
            symbol=symbol,
            score=0.0,
            n_headlines=0,
            direction=Direction.NEUTRAL,
            confidence=0.0,
            provenance=provenance,
        )
    score = round(max(-1.0, min(1.0, float(score))), 4)
    direction = Direction.UP if score > 0.05 else Direction.DOWN if score < -0.05 else Direction.NEUTRAL
    return SentimentSignal(
        symbol=symbol,
        score=score,
        n_headlines=len(headlines),
        direction=direction,
        confidence=round(min(1.0, abs(score)), 4),
        provenance=provenance,
    )


def ensemble(
    xgb_signal: str,
    xgb_confidence: float,
    sentiment: SentimentSignal,
    lstm_direction: Direction,
    lstm_confidence: float,
    threshold: float,
) -> tuple[Direction, float, dict]:
    """Weighted blend of the three PRD models. Returns (direction, confidence, parts)."""
    xgb_score = {"BUY": 1.0, "SELL": -1.0}.get(str(xgb_signal).upper(), 0.0) * float(xgb_confidence)
    finbert_score = sentiment.score
    lstm_score = (
        1.0 if lstm_direction == Direction.UP else -1.0 if lstm_direction == Direction.DOWN else 0.0
    ) * float(lstm_confidence)

    net = (
        ENSEMBLE_WEIGHTS["xgboost"] * xgb_score
        + ENSEMBLE_WEIGHTS["finbert"] * finbert_score
        + ENSEMBLE_WEIGHTS["lstm"] * lstm_score
    )
    direction = Direction.UP if net >= threshold else Direction.DOWN if net <= -threshold else Direction.NEUTRAL
    parts = {
        "xgboost": round(xgb_score, 4),
        "finbert": round(finbert_score, 4),
        "lstm": round(lstm_score, 4),
        "net": round(net, 4),
        "weights": dict(ENSEMBLE_WEIGHTS),
        "threshold": threshold,
    }
    return direction, round(min(1.0, abs(net)), 4), parts


def propose_quantity(
    *,
    equity: float,
    cash: float,
    price: float,
    atr: float | None,
    held_qty: float,
    held_value: float,
    risk_per_trade_pct: float,
    max_position_pct: float,
    max_order_notional: float,
    min_cash_buffer_pct: float,
) -> int:
    """Stop-distance sizing at 0.5 % risk, clamped by every pre-trade cap."""
    if price <= 0 or equity <= 0:
        return 0
    per_share_risk = max(price * 0.04, 2.0 * (atr or 0.0), 0.01)
    by_risk = (equity * risk_per_trade_pct) / per_share_risk
    by_notional = max_order_notional / price
    by_position = max(0.0, max_position_pct * equity - held_value) / price
    by_cash = max(0.0, cash - min_cash_buffer_pct * equity) / price
    qty = math.floor(min(by_risk, by_notional, by_position, by_cash))
    return max(0, int(qty))


def intent_hash(intent: OrderIntent) -> str:
    payload = intent.model_dump(mode="json")
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
