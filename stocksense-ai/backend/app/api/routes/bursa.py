"""Bursa Malaysia (KLSE) intelligence endpoints.

Routes:
  GET  /bursa/stocks               — list all tracked MY stocks
  GET  /bursa/market               — snapshot: gainers / losers / sectors
  GET  /bursa/screener             — filtered + sorted stock list
  GET  /bursa/predict/{code}       — XGBoost-style direction prediction
  GET  /bursa/stream?code=MY.XXX   — SSE live quote stream

Set DEMO_MODE=true in .env to run without moomoo / yfinance (serves
synthetic KLSE data — useful for development and CI).
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.core.config import get_settings
from app.core.demo_data import get_demo_prediction, get_demo_quote
from app.core.redis_client import cache_get, cache_set
from app.core.stocks import MY_YF_TICKERS, STOCK_UNIVERSE
from app.data.moomoo_fetcher import fetch_realtime_quote
from app.schemas.bursa import (
    BursaPredictionSchema,
    BursaStockSchema,
    MarketSnapshotSchema,
    ScreenerResultSchema,
)

logger = logging.getLogger(__name__)
router = APIRouter()
settings = get_settings()

MY_STOCKS = {k: v for k, v in STOCK_UNIVERSE.items() if v.get("market") == "MY"}

SECTOR_COLORS = {
    "Financials":          "#0099ff",
    "Utilities":           "#a78bfa",
    "Materials":           "#f5a623",
    "Communication":       "#00ffcc",
    "Consumer Defensive":  "#ff6b35",
    "Consumer Cyclical":   "#fbbf24",
    "Healthcare":          "#34d399",
    "Energy":              "#fb923c",
    "Industrials":         "#94a3b8",
    "Technology":          "#60a5fa",
}


def _parse_code(code: str) -> tuple[str, str]:
    """'MY.MAYBANK' → ('MAYBANK', 'MY')."""
    parts = code.upper().split(".", 1)
    return (parts[1], parts[0]) if len(parts) == 2 else (code.upper(), "MY")


async def _yf_quote_my(full_code: str) -> dict | None:
    """Try yfinance with the .KL suffix as a secondary fallback."""
    yf_ticker = MY_YF_TICKERS.get(full_code)
    if not yf_ticker:
        return None
    try:
        import pandas as pd
        import yfinance as yf

        data = await asyncio.to_thread(
            yf.download, yf_ticker, period="2d", progress=False, auto_adjust=True
        )
        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.get_level_values(0)
        if len(data) < 1:
            return None

        last = data.iloc[-1]
        prev = data.iloc[-2] if len(data) >= 2 else last
        last_price = float(last.get("Close", 0))
        prev_close = float(prev.get("Close", last_price))
        return {
            "last_price":       last_price,
            "open_price":       float(last.get("Open", 0)),
            "high_price":       float(last.get("High", 0)),
            "low_price":        float(last.get("Low", 0)),
            "prev_close_price": prev_close,
            "volume":           float(last.get("Volume", 0)),
            "bid_price":        0.0,
            "ask_price":        0.0,
            "source":           "yfinance_kl",
        }
    except Exception as exc:
        logger.warning("yfinance KL fallback failed for %s: %s", full_code, exc)
        return None


async def _fetch_quote(full_code: str) -> dict:
    """Fetch real-time quote: moomoo → yfinance → demo stub."""
    if settings.demo_mode:
        meta = MY_STOCKS.get(full_code, {})
        return get_demo_quote(full_code, meta)

    ticker, market = _parse_code(full_code)
    meta = MY_STOCKS.get(full_code, {})

    try:
        q = await fetch_realtime_quote(ticker, market)
        raw = q if q.get("last_price", 0) > 0 else (await _yf_quote_my(full_code)) or q
    except Exception as exc:
        logger.warning("moomoo fetch failed for %s: %s", full_code, exc)
        raw = (await _yf_quote_my(full_code)) or {"last_price": 0.0, "source": "error"}

    lp = raw.get("last_price", 0.0)
    pc = raw.get("prev_close_price", 0.0)
    change_pct = round(((lp - pc) / pc * 100) if pc else 0.0, 2)
    ticker_short = full_code.split(".")[-1]

    return {
        "code":             full_code,
        "ticker":           ticker_short,
        "name":             meta.get("name", ticker_short),
        "sector":           meta.get("sector", "Unknown"),
        "market":           "MY",
        "last_price":       round(lp, 4),
        "open_price":       round(raw.get("open_price", 0.0), 4),
        "high_price":       round(raw.get("high_price", 0.0), 4),
        "low_price":        round(raw.get("low_price", 0.0), 4),
        "prev_close_price": round(pc, 4),
        "bid_price":        round(raw.get("bid_price", 0.0), 4),
        "ask_price":        round(raw.get("ask_price", 0.0), 4),
        "volume":           raw.get("volume", 0),
        "change_pct":       change_pct,
        "change_abs":       round(lp - pc, 4),
        "source":           raw.get("source", "moomoo"),
        "update_time":      raw.get("update_time", datetime.now(timezone.utc).isoformat()),
    }


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/bursa/stocks", response_model=list[BursaStockSchema])
async def list_bursa_stocks():
    """List all tracked Malaysian stocks."""
    if settings.demo_mode:
        meta = MY_STOCKS
        return [get_demo_quote(k, v) for k, v in meta.items()]
    return [{"code": k, "ticker": k.split(".")[-1], **v} for k, v in MY_STOCKS.items()]


@router.get("/bursa/market", response_model=MarketSnapshotSchema)
async def bursa_market():
    """Parallel-fetch all MY stocks, return gainers/losers/sectors."""
    cache_key = "bursa:market:demo" if settings.demo_mode else "bursa:market"
    cached = await cache_get(cache_key)
    if cached:
        logger.debug("bursa_market: cache hit (%s)", cache_key)
        return cached

    logger.info("bursa_market: fetching %d stocks (demo=%s)", len(MY_STOCKS), settings.demo_mode)
    quotes: list[dict] = list(
        await asyncio.gather(*[_fetch_quote(c) for c in MY_STOCKS])
    )
    active = [q for q in quotes if q["last_price"] > 0]

    by_change = sorted(active, key=lambda q: q["change_pct"], reverse=True)
    gainers = [q for q in by_change if q["change_pct"] > 0][:5]
    losers  = [q for q in reversed(by_change) if q["change_pct"] < 0][:5]

    sector_map: dict[str, dict] = {}
    for q in active:
        s = q["sector"]
        if s not in sector_map:
            sector_map[s] = {
                "sector": s,
                "color": SECTOR_COLORS.get(s, "#4a7090"),
                "count": 0,
                "total_change": 0.0,
                "stocks": [],
            }
        sector_map[s]["count"] += 1
        sector_map[s]["total_change"] += q["change_pct"]
        sector_map[s]["stocks"].append(q["code"])

    sectors = [
        {**v, "avg_change": round(v["total_change"] / v["count"], 2)}
        for v in sector_map.values()
    ]
    for s in sectors:
        del s["total_change"]

    result = {
        "quotes":    quotes,
        "gainers":   gainers,
        "losers":    losers,
        "sectors":   sorted(sectors, key=lambda s: s["avg_change"], reverse=True),
        "total":     len(quotes),
        "active":    len(active),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "demo":      settings.demo_mode,
    }
    await cache_set(cache_key, result, ttl=30)
    logger.info("bursa_market: returned %d quotes, %d active", len(quotes), len(active))
    return result


@router.get("/bursa/screener", response_model=ScreenerResultSchema)
async def bursa_screener(
    sector:     str   = Query(default=""),
    min_change: float = Query(default=-100.0),
    max_change: float = Query(default=100.0),
    sort_by: Literal["change_pct", "volume", "last_price"] = Query(default="change_pct"),
):
    """Filter and sort tracked MY stocks."""
    try:
        cache_key = "bursa:market:demo" if settings.demo_mode else "bursa:market"
        cached = await cache_get(cache_key)
        quotes: list[dict] = cached["quotes"] if cached else list(
            await asyncio.gather(*[_fetch_quote(c) for c in MY_STOCKS])
        )

        results = [
            q for q in quotes
            if (not sector or q["sector"].lower() == sector.lower())
            and min_change <= q["change_pct"] <= max_change
        ]
        results.sort(key=lambda q: q.get(sort_by, 0), reverse=(sort_by != "last_price"))
        logger.debug("bursa_screener: sector=%r sort=%r → %d results", sector, sort_by, len(results))
        return {"results": results, "count": len(results)}
    except Exception as exc:
        logger.error("bursa_screener error: %s", exc)
        raise HTTPException(status_code=500, detail="Screener temporarily unavailable")


@router.get("/bursa/predict/{code}", response_model=BursaPredictionSchema)
async def bursa_predict(code: str):
    """Technical-indicator direction signal for a MY stock."""
    full_code = code.upper()
    cache_key = f"bursa:predict:demo:{full_code}" if settings.demo_mode else f"bursa:predict:{full_code}"

    cached = await cache_get(cache_key)
    if cached:
        return cached

    ticker, _ = _parse_code(full_code)

    if settings.demo_mode:
        result = get_demo_prediction(full_code, ticker)
        result["demo"] = True
        await cache_set(cache_key, result, ttl=300)
        return result

    yf_ticker = MY_YF_TICKERS.get(full_code, f"{ticker}.KL")

    try:
        import pandas as pd
        import yfinance as yf

        df = await asyncio.to_thread(
            yf.download, yf_ticker, period="6mo", progress=False, auto_adjust=True
        )
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        close = df["Close"].squeeze().dropna()
        if len(close) < 20:
            raise ValueError("Insufficient history after removing missing values")

        # RSI-14
        delta = close.diff()
        gain = delta.clip(lower=0).rolling(14).mean()
        loss = (-delta.clip(upper=0)).rolling(14).mean()
        last_gain = float(gain.iloc[-1])
        last_loss = float(loss.iloc[-1])
        if last_loss == 0:
            rsi = 100.0 if last_gain > 0 else 50.0
        else:
            rsi = 100.0 - (100.0 / (1.0 + last_gain / last_loss))

        # MACD (12/26)
        macd = float((close.ewm(span=12).mean() - close.ewm(span=26).mean()).iloc[-1])
        macd_sig = float(
            pd.Series(close.ewm(span=12).mean() - close.ewm(span=26).mean())
            .ewm(span=9).mean().iloc[-1]
        )

        # Bollinger Bands (20/2)
        sma20   = close.rolling(20).mean()
        std20   = close.rolling(20).std()
        bb_up   = float((sma20 + 2 * std20).iloc[-1])
        bb_lo   = float((sma20 - 2 * std20).iloc[-1])
        current = float(close.iloc[-1])

        # Momentum
        mom5  = float(close.pct_change(5).iloc[-1] * 100)
        mom20 = float(close.pct_change(20).iloc[-1] * 100)

        # Volume trend
        vol_ratio = 1.0
        if "Volume" in df and len(df) >= 20:
            vol_20_mean = float(df["Volume"].iloc[-20:].mean())
            if vol_20_mean > 0:
                vol_ratio = float(df["Volume"].iloc[-5:].mean()) / vol_20_mean

        score: float = 0.0
        signals: list[str] = []

        if rsi < 30:    score += 0.35; signals.append(f"RSI {rsi:.1f} — oversold, potential reversal")
        elif rsi < 45:  score += 0.12; signals.append(f"RSI {rsi:.1f} — neutral-low momentum")
        elif rsi > 70:  score -= 0.35; signals.append(f"RSI {rsi:.1f} — overbought")
        elif rsi > 55:  score -= 0.10; signals.append(f"RSI {rsi:.1f} — slightly elevated")

        if macd > macd_sig: score += 0.25; signals.append("MACD above signal line — bullish crossover")
        else:               score -= 0.25; signals.append("MACD below signal line — bearish pressure")

        if current < bb_lo:   score += 0.20; signals.append("Price below lower Bollinger Band — oversold zone")
        elif current > bb_up: score -= 0.20; signals.append("Price above upper Bollinger Band — overbought zone")

        if mom5 > 2.0:    score += 0.15; signals.append(f"5-day momentum +{mom5:.1f}%")
        elif mom5 < -2.0: score -= 0.15; signals.append(f"5-day momentum {mom5:.1f}% — short-term weakness")

        if vol_ratio > 1.5: score += 0.05; signals.append(f"Volume surge {vol_ratio:.1f}× 20-day avg")

        confidence = round(min(0.92, 0.52 + abs(score) * 0.38), 3)
        direction  = "UP" if score > 0 else "DOWN"

        result = {
            "code": full_code, "ticker": ticker,
            "direction": direction, "confidence": confidence, "score": round(score, 3),
            "rsi": round(rsi, 1), "macd": round(macd, 4), "macd_signal": round(macd_sig, 4),
            "bb_upper": round(bb_up, 4), "bb_lower": round(bb_lo, 4),
            "current_price": round(current, 4),
            "momentum_5d": round(mom5, 2), "momentum_20d": round(mom20, 2),
            "vol_ratio": round(vol_ratio, 2),
            "signals": signals,
            "demo": False,
        }
        await cache_set(cache_key, result, ttl=300)
        logger.info("bursa_predict: %s → %s (conf=%.2f)", full_code, direction, confidence)
        return result

    except Exception as exc:
        logger.error("bursa_predict failed for %s: %s", full_code, exc)
        return {
            "code": full_code, "ticker": ticker,
            "direction": "HOLD", "confidence": 0.5, "score": 0.0,
            "signals": ["Insufficient data — prediction unavailable"],
            "error": str(exc),
            "demo": False,
        }


async def _sse_quote_generator(code: str):
    while True:
        try:
            q = await _fetch_quote(code)
            yield f"data: {json.dumps(q)}\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'error': str(exc), 'code': code})}\n\n"
        await asyncio.sleep(10)


@router.get("/bursa/stream")
async def bursa_stream(code: str = Query(...)):
    """SSE endpoint — streams live MY stock quote every 10 seconds."""
    return StreamingResponse(
        _sse_quote_generator(code.upper()),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
