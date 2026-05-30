"""
Fetches OHLCV data from yfinance or moomoo API and computes all technical indicators.
Results are cached in Redis for 15 minutes.

Priority: moomoo (if enabled and available) -> yfinance (fallback)
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import yfinance as yf

try:
    from app.data.moomoo_fetcher import fetch_stock_data_moomoo, MoomooClient
    _HAS_MOOMOO_IMPORT = True
except ImportError:
    _HAS_MOOMOO_IMPORT = False
    fetch_stock_data_moomoo = None
    MoomooClient = None

try:
    import pandas_ta as ta
    _HAS_TA = True
except ImportError:
    _HAS_TA = False

from app.core.config import get_settings
from app.core.redis_client import cache_get, cache_set

logger = logging.getLogger(__name__)
settings = get_settings()


# ── helpers ──────────────────────────────────────────────────────────────────

def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def _macd(close: pd.Series, fast=12, slow=26, signal=9):
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def _bollinger(close: pd.Series, period: int = 20, std: float = 2.0):
    sma = close.rolling(period).mean()
    std_dev = close.rolling(period).std()
    upper = sma + std * std_dev
    lower = sma - std * std_dev
    return upper, sma, lower


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Add RSI, MACD, SMA-20/50, Bollinger Bands + extended indicators to a price DataFrame."""
    close = df["Close"].squeeze()
    high = df["High"].squeeze()
    low = df["Low"].squeeze()
    volume = df["Volume"].squeeze()

    if _HAS_TA:
        df.ta.rsi(length=14, append=True)
        df.ta.macd(fast=12, slow=26, signal=9, append=True)
        df.ta.sma(length=20, append=True)
        df.ta.sma(length=50, append=True)
        df.ta.bbands(length=20, std=2.0, append=True)

        # Normalise column names
        rename = {}
        for col in df.columns:
            cl = col.upper()
            if cl.startswith("RSI_"):    rename[col] = "rsi"
            elif "MACD_12_26_9" == cl:   rename[col] = "macd"
            elif "MACDS_12_26_9" == cl:  rename[col] = "macd_signal"
            elif "MACDH_12_26_9" == cl:  rename[col] = "macd_hist"
            elif cl == "SMA_20":         rename[col] = "sma_20"
            elif cl == "SMA_50":         rename[col] = "sma_50"
            elif cl.startswith("BBU_"):  rename[col] = "bb_upper"
            elif cl.startswith("BBM_"):  rename[col] = "bb_mid"
            elif cl.startswith("BBL_"):  rename[col] = "bb_lower"
        df = df.rename(columns=rename)
    else:
        df["rsi"] = _rsi(close)
        df["macd"], df["macd_signal"], df["macd_hist"] = _macd(close)
        df["sma_20"] = close.rolling(20).mean()
        df["sma_50"] = close.rolling(50).mean()
        df["bb_upper"], df["bb_mid"], df["bb_lower"] = _bollinger(close)

    # Ensure expected base columns exist
    for col in ["rsi", "macd", "macd_signal", "macd_hist",
                "sma_20", "sma_50", "bb_upper", "bb_mid", "bb_lower"]:
        if col not in df.columns:
            df[col] = np.nan

    # ── Extended indicators ───────────────────────────────────────────────────

    # EMAs
    df["ema_12"] = close.ewm(span=12, adjust=False).mean()
    df["ema_26"] = close.ewm(span=26, adjust=False).mean()
    df["ema_9"]  = close.ewm(span=9, adjust=False).mean()

    # ATR-14 (Average True Range)
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    df["atr_14"] = tr.ewm(span=14, adjust=False).mean()

    # Rate of Change
    df["roc_5"]  = close.pct_change(5)
    df["roc_20"] = close.pct_change(20)

    # Volume z-score (20-day rolling)
    vol_mean = volume.rolling(20).mean()
    vol_std  = volume.rolling(20).std()
    df["volume_zscore"] = (volume - vol_mean) / vol_std.replace(0, np.nan)

    # Bollinger Band derived features (require bb columns)
    bb_upper = df["bb_upper"]
    bb_lower = df["bb_lower"]
    bb_mid   = df["bb_mid"]
    bb_range = (bb_upper - bb_lower).replace(0, np.nan)
    df["bb_width"] = bb_range / bb_mid.replace(0, np.nan)
    df["bb_pct_b"] = (close - bb_lower) / bb_range

    # Price vs SMA-20
    sma20 = df["sma_20"].replace(0, np.nan)
    df["price_vs_sma20"] = (close - sma20) / sma20

    # Golden cross signal: EMA-12 > EMA-26
    df["golden_cross"] = (df["ema_12"] > df["ema_26"]).astype(int)

    # Daily return and 5-day return
    df["daily_return"] = close.pct_change()
    df["return_5d"]    = close.pct_change(5)

    # Ensure all new columns exist
    for col in [
        "ema_12", "ema_26", "ema_9", "atr_14",
        "roc_5", "roc_20", "volume_zscore",
        "bb_width", "bb_pct_b", "price_vs_sma20",
        "golden_cross", "daily_return", "return_5d",
    ]:
        if col not in df.columns:
            df[col] = np.nan

    return df


# ── main fetcher ──────────────────────────────────────────────────────────────

async def fetch_stock_data(ticker: str, period_years: int = 2) -> pd.DataFrame:
    """
    Returns a DataFrame with OHLCV + technical indicators.
    Cached in Redis for 15 minutes (raw JSON, then re-parsed).

    Tries moomoo API first (if enabled), falls back to yfinance.
    """
    cache_key = f"dataset:{ticker.upper()}:{period_years}y"
    cached = await cache_get(cache_key)
    if cached:
        df = pd.DataFrame(cached)
        df.index = pd.to_datetime(df.index)
        return df

    # Try moomoo first for historical K-line data
    if _HAS_MOOMOO_IMPORT and MoomooClient and MoomooClient.is_connected():
        try:
            from app.core.config import get_settings
            settings = get_settings()
            if settings.moomoo_enabled:
                period_days = period_years * 365
                df = await fetch_stock_data_moomoo(ticker, period_days)
                if not df.empty:
                    # Cache and return
                    serialisable = df.copy()
                    serialisable.index = serialisable.index.strftime("%Y-%m-%d")
                    await cache_set(cache_key, serialisable.to_dict(), settings.cache_dataset_ttl)
                    return df
        except Exception as e:
            logger.warning("moomoo historical fetch failed for %s, falling back to yfinance: %s", ticker, e)

    # Fallback to yfinance
    end = datetime.today()
    start = end - timedelta(days=365 * period_years + 30)

    try:
        raw = yf.download(
            ticker,
            start=start.strftime("%Y-%m-%d"),
            end=end.strftime("%Y-%m-%d"),
            progress=False,
            auto_adjust=True,
        )
        if raw.empty:
            raise ValueError(f"No data returned for {ticker}")
    except Exception as exc:
        logger.error("yfinance fetch failed for %s: %s", ticker, exc)
        raise

    # Flatten MultiIndex columns if present
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)

    df = raw[["Open", "High", "Low", "Close", "Volume"]].copy()
    df = add_indicators(df)
    df = df.dropna(subset=["Close"])

    # Store in Redis (convert index to string)
    serialisable = df.copy()
    serialisable.index = serialisable.index.strftime("%Y-%m-%d")
    await cache_set(cache_key, serialisable.to_dict(), settings.cache_dataset_ttl)

    return df


async def get_latest_price(ticker: str) -> float:
    """Quick fetch of the most recent close price."""
    try:
        data = yf.download(ticker, period="2d", progress=False, auto_adjust=True)
        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.get_level_values(0)
        return float(data["Close"].iloc[-1])
    except Exception:
        return 0.0
