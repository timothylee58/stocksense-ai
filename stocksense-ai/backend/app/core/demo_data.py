"""Synthetic KLSE data for DEMO_MODE=true.

All prices are in MYR and are representative of typical Bursa Malaysia
trading ranges. No external API calls are made in demo mode.
"""
from __future__ import annotations

import math
import random
from datetime import datetime, timezone

# Seed for reproducibility within a session — daily seed makes data stable
_DAY_SEED = datetime.now(timezone.utc).toordinal()

DEMO_QUOTES: dict[str, dict] = {
    "MY.MAYBANK":  {"last_price": 9.25,  "open_price": 9.20,  "high_price": 9.32,  "low_price": 9.18,  "prev_close_price": 9.22,  "bid_price": 9.24,  "ask_price": 9.26,  "volume": 8_500_000},
    "MY.PBBANK":   {"last_price": 4.52,  "open_price": 4.50,  "high_price": 4.55,  "low_price": 4.49,  "prev_close_price": 4.48,  "bid_price": 4.51,  "ask_price": 4.53,  "volume": 5_200_000},
    "MY.CIMB":     {"last_price": 7.10,  "open_price": 7.05,  "high_price": 7.15,  "low_price": 7.02,  "prev_close_price": 7.08,  "bid_price": 7.09,  "ask_price": 7.11,  "volume": 12_000_000},
    "MY.RHBBANK":  {"last_price": 6.20,  "open_price": 6.18,  "high_price": 6.25,  "low_price": 6.15,  "prev_close_price": 6.22,  "bid_price": 6.19,  "ask_price": 6.21,  "volume": 3_800_000},
    "MY.HLBANK":   {"last_price": 20.80, "open_price": 20.70, "high_price": 20.90, "low_price": 20.65, "prev_close_price": 20.78, "bid_price": 20.79, "ask_price": 20.81, "volume": 1_200_000},
    "MY.TENAGA":   {"last_price": 12.40, "open_price": 12.35, "high_price": 12.48, "low_price": 12.30, "prev_close_price": 12.38, "bid_price": 12.39, "ask_price": 12.41, "volume": 6_500_000},
    "MY.PETGAS":   {"last_price": 17.20, "open_price": 17.15, "high_price": 17.28, "low_price": 17.10, "prev_close_price": 17.18, "bid_price": 17.19, "ask_price": 17.21, "volume": 2_100_000},
    "MY.YTLPOWR":  {"last_price": 3.55,  "open_price": 3.52,  "high_price": 3.58,  "low_price": 3.50,  "prev_close_price": 3.54,  "bid_price": 3.54,  "ask_price": 3.56,  "volume": 25_000_000},
    "MY.PETRONAS": {"last_price": 8.30,  "open_price": 8.28,  "high_price": 8.35,  "low_price": 8.25,  "prev_close_price": 8.32,  "bid_price": 8.29,  "ask_price": 8.31,  "volume": 4_500_000},
    "MY.HAPSENG":  {"last_price": 6.55,  "open_price": 6.52,  "high_price": 6.60,  "low_price": 6.50,  "prev_close_price": 6.58,  "bid_price": 6.54,  "ask_price": 6.56,  "volume": 1_800_000},
    "MY.GAMUDA":   {"last_price": 5.10,  "open_price": 5.08,  "high_price": 5.15,  "low_price": 5.05,  "prev_close_price": 5.12,  "bid_price": 5.09,  "ask_price": 5.11,  "volume": 8_200_000},
    "MY.AXIATA":   {"last_price": 2.82,  "open_price": 2.80,  "high_price": 2.85,  "low_price": 2.78,  "prev_close_price": 2.84,  "bid_price": 2.81,  "ask_price": 2.83,  "volume": 18_000_000},
    "MY.MAXIS":    {"last_price": 3.85,  "open_price": 3.83,  "high_price": 3.88,  "low_price": 3.81,  "prev_close_price": 3.82,  "bid_price": 3.84,  "ask_price": 3.86,  "volume": 7_500_000},
    "MY.DIGI":     {"last_price": 3.48,  "open_price": 3.46,  "high_price": 3.51,  "low_price": 3.44,  "prev_close_price": 3.50,  "bid_price": 3.47,  "ask_price": 3.49,  "volume": 9_200_000},
    "MY.IHH":      {"last_price": 7.05,  "open_price": 7.02,  "high_price": 7.10,  "low_price": 6.98,  "prev_close_price": 7.00,  "bid_price": 7.04,  "ask_price": 7.06,  "volume": 5_800_000},
    "MY.SIME":     {"last_price": 2.58,  "open_price": 2.56,  "high_price": 2.62,  "low_price": 2.54,  "prev_close_price": 2.60,  "bid_price": 2.57,  "ask_price": 2.59,  "volume": 14_000_000},
    "MY.GENTING":  {"last_price": 4.48,  "open_price": 4.45,  "high_price": 4.52,  "low_price": 4.43,  "prev_close_price": 4.46,  "bid_price": 4.47,  "ask_price": 4.49,  "volume": 6_800_000},
}

DEMO_PREDICTIONS: dict[str, dict] = {
    "MY.MAYBANK":  {"direction": "UP",   "confidence": 0.72, "score": 0.48,  "rsi": 52.3, "momentum_5d": 0.33, "signals": ["RSI 52.3 — neutral", "MACD above signal line — bullish crossover"]},
    "MY.PBBANK":   {"direction": "UP",   "confidence": 0.68, "score": 0.35,  "rsi": 48.1, "momentum_5d": 0.89, "signals": ["5-day momentum +0.9%", "Volume within normal range"]},
    "MY.CIMB":     {"direction": "DOWN", "confidence": 0.61, "score": -0.22, "rsi": 62.4, "momentum_5d": -0.28,"signals": ["RSI 62.4 — slightly elevated", "MACD below signal line — bearish pressure"]},
    "MY.RHBBANK":  {"direction": "DOWN", "confidence": 0.58, "score": -0.15, "rsi": 44.7, "momentum_5d": -0.32,"signals": ["RSI 44.7 — neutral-low momentum", "MACD below signal line — bearish pressure"]},
    "MY.HLBANK":   {"direction": "UP",   "confidence": 0.64, "score": 0.20,  "rsi": 55.8, "momentum_5d": 0.10, "signals": ["MACD above signal line — bullish crossover"]},
    "MY.TENAGA":   {"direction": "UP",   "confidence": 0.75, "score": 0.52,  "rsi": 38.2, "momentum_5d": 0.16, "signals": ["RSI 38.2 — neutral-low momentum", "MACD above signal line — bullish crossover"]},
    "MY.PETGAS":   {"direction": "UP",   "confidence": 0.69, "score": 0.38,  "rsi": 50.0, "momentum_5d": 0.12, "signals": ["RSI 50.0 — neutral", "Volume within normal range"]},
    "MY.YTLPOWR":  {"direction": "DOWN", "confidence": 0.66, "score": -0.30, "rsi": 71.5, "momentum_5d": -1.12,"signals": ["RSI 71.5 — overbought", "5-day momentum -1.1% — short-term weakness"]},
    "MY.PETRONAS": {"direction": "DOWN", "confidence": 0.57, "score": -0.08, "rsi": 47.9, "momentum_5d": -0.24,"signals": ["MACD below signal line — bearish pressure"]},
    "MY.HAPSENG":  {"direction": "DOWN", "confidence": 0.60, "score": -0.18, "rsi": 58.3, "momentum_5d": -0.46,"signals": ["RSI 58.3 — slightly elevated", "MACD below signal line — bearish pressure"]},
    "MY.GAMUDA":   {"direction": "DOWN", "confidence": 0.62, "score": -0.20, "rsi": 45.6, "momentum_5d": -0.39,"signals": ["MACD below signal line — bearish pressure"]},
    "MY.AXIATA":   {"direction": "UP",   "confidence": 0.71, "score": 0.44,  "rsi": 32.1, "momentum_5d": -0.71,"signals": ["RSI 32.1 — oversold, potential reversal", "MACD above signal line — bullish crossover"]},
    "MY.MAXIS":    {"direction": "UP",   "confidence": 0.65, "score": 0.25,  "rsi": 53.2, "momentum_5d": 0.78, "signals": ["5-day momentum +0.8%", "MACD above signal line — bullish crossover"]},
    "MY.DIGI":     {"direction": "DOWN", "confidence": 0.59, "score": -0.14, "rsi": 57.4, "momentum_5d": -0.57,"signals": ["RSI 57.4 — slightly elevated", "MACD below signal line — bearish pressure"]},
    "MY.IHH":      {"direction": "UP",   "confidence": 0.70, "score": 0.42,  "rsi": 41.3, "momentum_5d": 0.71, "signals": ["RSI 41.3 — neutral-low momentum", "5-day momentum +0.7%"]},
    "MY.SIME":     {"direction": "DOWN", "confidence": 0.63, "score": -0.23, "rsi": 66.2, "momentum_5d": -0.77,"signals": ["RSI 66.2 — overbought", "MACD below signal line — bearish pressure"]},
    "MY.GENTING":  {"direction": "UP",   "confidence": 0.67, "score": 0.32,  "rsi": 43.8, "momentum_5d": 0.45, "signals": ["RSI 43.8 — neutral-low momentum", "MACD above signal line — bullish crossover"]},
}


def get_demo_quote(full_code: str, meta: dict) -> dict:
    """Return a demo quote with a small intra-day random walk from the seed price."""
    rng = random.Random(_DAY_SEED ^ hash(full_code))
    base = DEMO_QUOTES.get(full_code, {"last_price": 1.0, "prev_close_price": 1.0, "volume": 100_000})
    jitter = rng.uniform(-0.008, 0.012)          # ±0.8–1.2% daily move
    lp  = round(base["last_price"] * (1 + jitter), 4)
    pc  = base["prev_close_price"]
    chg = round((lp - pc) / pc * 100, 2)
    ticker = full_code.split(".")[-1]
    return {
        "code":             full_code,
        "ticker":           ticker,
        "name":             meta.get("name", ticker),
        "sector":           meta.get("sector", "Unknown"),
        "market":           "MY",
        "last_price":       lp,
        "open_price":       round(base["open_price"] * (1 + rng.uniform(-0.003, 0.003)), 4),
        "high_price":       round(base["high_price"] * (1 + rng.uniform(0, 0.005)), 4),
        "low_price":        round(base["low_price"]  * (1 - rng.uniform(0, 0.005)), 4),
        "prev_close_price": round(pc, 4),
        "bid_price":        round(lp - 0.005, 4),
        "ask_price":        round(lp + 0.005, 4),
        "volume":           int(base["volume"] * rng.uniform(0.7, 1.3)),
        "change_pct":       chg,
        "change_abs":       round(lp - pc, 4),
        "source":           "demo",
        "update_time":      datetime.now(timezone.utc).isoformat(),
    }


def get_demo_prediction(full_code: str, ticker: str) -> dict:
    """Return a static demo prediction (deterministic per stock)."""
    base = DEMO_PREDICTIONS.get(full_code, {
        "direction": "HOLD", "confidence": 0.52, "score": 0.0,
        "rsi": 50.0, "momentum_5d": 0.0, "signals": ["Demo mode — no live data"],
    })
    lp = DEMO_QUOTES.get(full_code, {}).get("last_price", 0.0)
    return {
        "code":          full_code,
        "ticker":        ticker,
        "direction":     base["direction"],
        "confidence":    base["confidence"],
        "score":         base["score"],
        "rsi":           base["rsi"],
        "macd":          round(base["score"] * 0.08, 4),
        "macd_signal":   round(base["score"] * 0.04, 4),
        "bb_upper":      round(lp * 1.04, 4),
        "bb_lower":      round(lp * 0.96, 4),
        "current_price": lp,
        "momentum_5d":   base["momentum_5d"],
        "momentum_20d":  round(base["momentum_5d"] * 2.2, 2),
        "vol_ratio":     round(1.0 + abs(base["score"]) * 0.4, 2),
        "signals":       base["signals"],
    }
