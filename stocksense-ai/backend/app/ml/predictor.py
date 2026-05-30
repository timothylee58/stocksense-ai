"""
Ensemble predictor: LSTM (60 %) + XGBoost (40 %).
Produces a rich PredictionResult with 30-day forecast, timing analysis,
buy/sell zones, stop loss, and risk scoring.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from typing import Literal

import numpy as np
import pandas as pd

from app.data.fetcher import fetch_stock_data
from app.ml.models.lstm import predict_lstm
from app.ml.models.xgb_model import predict_xgb
from app.core.config import get_settings
from app.core.redis_client import cache_get, cache_set
from app.core.stocks import get_stock_info

logger = logging.getLogger(__name__)
settings = get_settings()

Signal = Literal["BUY", "SELL", "HOLD"]
Trend = Literal["BULLISH", "BEARISH", "SIDEWAYS"]
Risk = Literal["LOW", "MEDIUM", "HIGH"]
Action = Literal["BUY_NOW", "WAIT_FOR_DIP", "HOLD", "SELL_NOW", "AVOID"]


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class ForecastPoint:
    date: str
    price: float
    lower: float
    upper: float


@dataclass
class TimingAnalysis:
    timing_score: float          # 0–10  (10 = perfect entry)
    action: Action
    buy_zone_low: float
    buy_zone_high: float
    stop_loss: float
    risk_level: Risk
    days_to_opportunity: int | None
    rationale: list[str]


@dataclass
class PredictionResult:
    ticker: str
    name: str
    sector: str
    current_price: float
    forecast_price: float        # 7-day target
    signal: Signal
    confidence: float
    sentiment_score: float
    trend: Trend
    price_target_7d: float
    price_target_14d: float
    price_target_30d: float
    price_change_pct: float      # 7d vs current
    timing: TimingAnalysis
    rsi: float | None
    macd: float | None
    macd_signal: float | None
    bollinger_upper: float | None
    bollinger_lower: float | None
    sma_20: float | None
    sma_50: float | None
    chart_data: list[dict]       # 90 days history
    forecast_data: list[dict]    # 30-day forecast


# ── Helpers ───────────────────────────────────────────────────────────────────

def _safe(val) -> float | None:
    try:
        f = float(val)
        return None if (np.isnan(f) or np.isinf(f)) else round(f, 4)
    except (TypeError, ValueError):
        return None


def _trend_from_forecast(current: float, forecast_7d: float, forecast_30d: float) -> Trend:
    pct_7 = (forecast_7d - current) / current if current else 0
    pct_30 = (forecast_30d - current) / current if current else 0
    avg = (pct_7 + pct_30) / 2
    if avg > 0.02:
        return "BULLISH"
    if avg < -0.02:
        return "BEARISH"
    return "SIDEWAYS"


def _sentiment_from_rsi(rsi: float | None, macd: float | None, macd_sig: float | None) -> float:
    score = 0.5
    if rsi is not None:
        if rsi < 30:   score += 0.25
        elif rsi < 45: score += 0.10
        elif rsi > 70: score -= 0.25
        elif rsi > 55: score -= 0.10
    if macd is not None and macd_sig is not None:
        if macd > macd_sig: score += 0.12
        else:               score -= 0.12
    return round(min(1.0, max(0.0, score)), 3)


def _timing_analysis(
    df: pd.DataFrame,
    current_price: float,
    forecast_prices: list[float],
    xgb_signal: Signal,
    confidence: float,
) -> TimingAnalysis:
    last = df.iloc[-1]
    prev = df.iloc[-2] if len(df) > 1 else last

    rsi = _safe(last.get("rsi") if hasattr(last, "get") else getattr(last, "rsi", None))
    macd = _safe(last.get("macd") if hasattr(last, "get") else getattr(last, "macd", None))
    macd_sig = _safe(last.get("macd_signal") if hasattr(last, "get") else getattr(last, "macd_signal", None))
    prev_macd = _safe(prev.get("macd") if hasattr(prev, "get") else getattr(prev, "macd", None))
    prev_macd_sig = _safe(prev.get("macd_signal") if hasattr(prev, "get") else getattr(prev, "macd_signal", None))
    bb_lower = _safe(last.get("bb_lower") if hasattr(last, "get") else getattr(last, "bb_lower", None))
    bb_upper = _safe(last.get("bb_upper") if hasattr(last, "get") else getattr(last, "bb_upper", None))
    sma_50 = _safe(last.get("sma_50") if hasattr(last, "get") else getattr(last, "sma_50", None))

    score = 5.0   # neutral baseline
    rationale: list[str] = []

    # ── RSI ──
    if rsi is not None:
        if rsi < 25:
            score += 2.5; rationale.append(f"RSI {rsi:.1f} — strongly oversold (excellent buy zone)")
        elif rsi < 35:
            score += 1.5; rationale.append(f"RSI {rsi:.1f} — oversold")
        elif rsi < 45:
            score += 0.5; rationale.append(f"RSI {rsi:.1f} — approaching oversold")
        elif rsi > 75:
            score -= 2.5; rationale.append(f"RSI {rsi:.1f} — strongly overbought (consider selling)")
        elif rsi > 65:
            score -= 1.5; rationale.append(f"RSI {rsi:.1f} — overbought")
        else:
            rationale.append(f"RSI {rsi:.1f} — neutral")

    # ── MACD crossover ──
    if all(v is not None for v in [macd, macd_sig, prev_macd, prev_macd_sig]):
        bullish_cross = prev_macd < prev_macd_sig and macd > macd_sig
        bearish_cross = prev_macd > prev_macd_sig and macd < macd_sig
        if bullish_cross:
            score += 2.0; rationale.append("MACD bullish crossover — momentum turning up")
        elif bearish_cross:
            score -= 2.0; rationale.append("MACD bearish crossover — momentum turning down")
        elif macd > macd_sig:
            score += 0.5; rationale.append("MACD above signal line — bullish momentum")
        else:
            score -= 0.5; rationale.append("MACD below signal line — bearish momentum")

    # ── Bollinger Band position ──
    if bb_lower is not None and bb_upper is not None and bb_upper > bb_lower:
        bb_range = bb_upper - bb_lower
        bb_pos = (current_price - bb_lower) / bb_range
        if bb_pos < 0.10:
            score += 2.0; rationale.append("Price at lower Bollinger Band — potential bounce zone")
        elif bb_pos < 0.25:
            score += 1.0; rationale.append("Price near lower Bollinger Band — discount zone")
        elif bb_pos > 0.90:
            score -= 2.0; rationale.append("Price at upper Bollinger Band — overbought extension")
        elif bb_pos > 0.75:
            score -= 1.0; rationale.append("Price near upper Bollinger Band — stretched")

    # ── Trend alignment ──
    if sma_50 is not None:
        if current_price < sma_50 * 0.97:
            score += 1.0; rationale.append("Price below 50-day SMA — potential value entry")
        elif current_price > sma_50 * 1.05:
            score -= 0.5; rationale.append("Price extended above 50-day SMA")

    # ── Forecast momentum ──
    if len(forecast_prices) >= 7:
        fwd_7 = forecast_prices[6]
        fwd_pct = (fwd_7 - current_price) / current_price
        if fwd_pct > 0.03:
            score += 1.0; rationale.append(f"Model forecasts +{fwd_pct*100:.1f}% over 7 days")
        elif fwd_pct < -0.03:
            score -= 1.0; rationale.append(f"Model forecasts {fwd_pct*100:.1f}% over 7 days")

    # ── Clamp score ──
    score = round(min(10.0, max(0.0, score)), 2)

    # ── Derive action ──
    if xgb_signal == "BUY" and score >= 6:
        action: Action = "BUY_NOW"
    elif xgb_signal == "BUY" and score >= 4:
        action = "WAIT_FOR_DIP"
    elif xgb_signal == "SELL" and score <= 4:
        action = "SELL_NOW"
    elif xgb_signal == "SELL" and score <= 6:
        action = "AVOID"
    else:
        action = "HOLD"

    # ── Zones ──
    if bb_lower is not None:
        buy_low = round(bb_lower * 0.99, 2)
        buy_high = round(bb_lower * 1.02, 2)
    else:
        buy_low = round(current_price * 0.97, 2)
        buy_high = round(current_price * 1.00, 2)

    volatility = float(df["Close"].squeeze().pct_change().std()) if len(df) > 5 else 0.015
    stop_loss = round(current_price * (1 - max(0.04, volatility * 2)), 2)

    # ── Risk level ──
    if volatility > 0.03:
        risk: Risk = "HIGH"
    elif volatility > 0.015:
        risk = "MEDIUM"
    else:
        risk = "LOW"

    # ── Days to opportunity ──
    days_to_opp: int | None = None
    if action in ("WAIT_FOR_DIP", "AVOID") and bb_lower is not None:
        # Estimate days until price might reach buy zone
        recent_trend = float(df["Close"].squeeze().pct_change(5).iloc[-1]) or 0
        if recent_trend < 0:
            pct_gap = (current_price - buy_high) / current_price
            if abs(recent_trend) > 0:
                days_to_opp = max(1, int(pct_gap / abs(recent_trend / 5)))

    return TimingAnalysis(
        timing_score=score,
        action=action,
        buy_zone_low=buy_low,
        buy_zone_high=buy_high,
        stop_loss=stop_loss,
        risk_level=risk,
        days_to_opportunity=days_to_opp,
        rationale=rationale,
    )


def _build_forecast_data(current_price: float, prices: list[float], confidence: float) -> list[ForecastPoint]:
    """Build forecast data with confidence-interval bands (uncertainty widens over time)."""
    points = []
    today = datetime.today()
    # uncertainty grows with each day
    for i, price in enumerate(prices):
        day = today + timedelta(days=i + 1)
        # Skip weekends in labelling
        spread_pct = 0.01 + (i / len(prices)) * (1 - confidence) * 0.08
        lower = round(price * (1 - spread_pct), 2)
        upper = round(price * (1 + spread_pct), 2)
        points.append(ForecastPoint(
            date=day.strftime("%b %d"),
            price=round(price, 2),
            lower=lower,
            upper=upper,
        ))
    return points


def _build_chart_data(df: pd.DataFrame, n: int = 90) -> list[dict]:
    recent = df.tail(n)
    result = []
    for idx, row in recent.iterrows():
        date_str = idx.strftime("%b %d") if hasattr(idx, "strftime") else str(idx)[:10]
        result.append({"time": date_str, "price": round(float(row["Close"]), 2)})
    return result


# ── Main entry point ──────────────────────────────────────────────────────────

async def run_prediction(ticker: str) -> dict:
    """
    Full prediction pipeline. Returns a JSON-serialisable dict.
    Cached in Redis for 5 minutes.
    """
    cache_key = f"prediction:{ticker.upper()}"
    cached = await cache_get(cache_key)
    if cached:
        return cached

    df = await fetch_stock_data(ticker.upper())
    info = get_stock_info(ticker)

    current_price = float(df["Close"].squeeze().iloc[-1])
    last = df.iloc[-1]

    # ── ML ──
    forecast_prices, lstm_conf = predict_lstm(df, ticker)
    xgb_signal, xgb_conf = predict_xgb(df, ticker)

    # ── Ensemble signal & confidence ──
    # Weight: 60% LSTM forecast direction, 40% XGBoost classification
    if len(forecast_prices) >= 7:
        lstm_7d_return = (forecast_prices[6] - current_price) / current_price
        if lstm_7d_return > 0.01:   lstm_signal: Signal = "BUY"
        elif lstm_7d_return < -0.01: lstm_signal = "SELL"
        else:                        lstm_signal = "HOLD"
    else:
        lstm_signal = "HOLD"

    signal_votes = {"BUY": 0.0, "SELL": 0.0, "HOLD": 0.0}
    signal_votes[lstm_signal] += 0.60 * lstm_conf
    signal_votes[xgb_signal]  += 0.40 * xgb_conf
    final_signal: Signal = max(signal_votes, key=signal_votes.__getitem__)
    confidence = round(min(0.99, signal_votes[final_signal] + 0.1), 3)

    # ── Targets ──
    pt7  = round(forecast_prices[6],  2) if len(forecast_prices) >= 7  else current_price
    pt14 = round(forecast_prices[13], 2) if len(forecast_prices) >= 14 else pt7
    pt30 = round(forecast_prices[-1], 2) if forecast_prices            else current_price
    price_change_pct = round((pt7 - current_price) / current_price * 100, 2)

    # ── Technical values ──
    def _get(col):
        v = last.get(col) if hasattr(last, "get") else getattr(last, col, None)
        return _safe(v)

    rsi = _get("rsi");   macd_ = _get("macd"); macd_sig = _get("macd_signal")
    bb_upper = _get("bb_upper"); bb_lower = _get("bb_lower")
    sma_20 = _get("sma_20"); sma_50 = _get("sma_50")

    trend = _trend_from_forecast(current_price, pt7, pt30)
    sentiment = _sentiment_from_rsi(rsi, macd_, macd_sig)

    timing = _timing_analysis(df, current_price, forecast_prices, final_signal, confidence)
    forecast_data = _build_forecast_data(current_price, forecast_prices, lstm_conf)
    chart_data = _build_chart_data(df)

    result = PredictionResult(
        ticker=ticker.upper(),
        name=info["name"],
        sector=info["sector"],
        current_price=round(current_price, 2),
        forecast_price=pt7,
        signal=final_signal,
        confidence=confidence,
        sentiment_score=sentiment,
        trend=trend,
        price_target_7d=pt7,
        price_target_14d=pt14,
        price_target_30d=pt30,
        price_change_pct=price_change_pct,
        timing=timing,
        rsi=rsi,
        macd=macd_,
        macd_signal=macd_sig,
        bollinger_upper=bb_upper,
        bollinger_lower=bb_lower,
        sma_20=sma_20,
        sma_50=sma_50,
        chart_data=chart_data,
        forecast_data=[asdict(fp) for fp in forecast_data],
    )

    payload = {
        **asdict(result),
        "timing": asdict(timing),
    }

    await cache_set(cache_key, payload, settings.cache_predict_ttl)
    return payload
