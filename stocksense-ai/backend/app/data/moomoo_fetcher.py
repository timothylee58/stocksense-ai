"""
Fetches real-time quotes and tick data from moomoo OpenD gateway.
Supports US and Malaysia stock markets with LV1/LV2 data.

Requirements:
1. Install moomoo-api: pip install moomoo-api
2. Start moomoo OpenD gateway client
3. Configure host/port in environment (default: 127.0.0.1:11111)
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional

import numpy as np
import pandas as pd

try:
    import moomoo as ft
    from moomoo import OpenQuoteContext, RET_OK, RET_ERROR, SubType
    _HAS_MOOMOO = True
except ImportError:
    _HAS_MOOMOO = False
    ft = None
    OpenQuoteContext = None
    RET_OK = None
    RET_ERROR = None
    SubType = None

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# Market code mapping for moomoo
MARKET_CODES = {
    "US": "US.",      # US stocks: US.AAPL, US.NVDA
    "MY": "MY.",      # Malaysia stocks: MY.MAYBANK, MY.TENAGA
    "HK": "HK.",      # Hong Kong stocks: HK.00700
    "SG": "SG.",      # Singapore stocks: SG.D05
}


def get_moomoo_code(ticker: str, market: str = "US") -> str:
    """Convert ticker symbol to moomoo market code format."""
    prefix = MARKET_CODES.get(market.upper(), "US.")
    return f"{prefix}{ticker}"


class MoomooClient:
    """Singleton moomoo quote context client."""

    _instance: Optional[OpenQuoteContext] = None
    _connected: bool = False

    @classmethod
    def get_client(cls) -> Optional[OpenQuoteContext]:
        """Get or create moomoo quote context."""
        if not _HAS_MOOMOO:
            logger.warning("moomoo-api not installed. Install with: pip install moomoo-api")
            return None

        if cls._instance is None:
            try:
                cls._instance = OpenQuoteContext(
                    host=settings.moomoo_host,
                    port=settings.moomoo_port
                )
                cls._instance.start()
                cls._connected = True
                logger.info(f"Connected to moomoo OpenD at {settings.moomoo_host}:{settings.moomoo_port}")
            except Exception as e:
                logger.error(f"Failed to connect to moomoo OpenD: {e}")
                return None

        return cls._instance

    @classmethod
    def is_connected(cls) -> bool:
        """Check if moomoo client is connected."""
        return cls._connected and cls._instance is not None


async def fetch_realtime_quote(ticker: str, market: str = "US") -> dict:
    """
    Fetch real-time quote for a stock from moomoo.

    Returns dict with:
    - last_price, open_price, high_price, low_price
    - volume, turnover, turnover_rate
    - bid_price, ask_price, price_spread
    - pre_price, after_price (US stocks)
    """
    if not _HAS_MOOMOO:
        logger.warning("moomoo-api not available, falling back to yfinance")
        return await _fallback_yfinance_quote(ticker)

    client = MoomooClient.get_client()
    if client is None:
        return await _fallback_yfinance_quote(ticker)

    code = get_moomoo_code(ticker, market)

    try:
        # Subscribe to quote data
        ret_sub, err = client.subscribe([code], [SubType.QUOTE], subscribe_push=False)
        if ret_sub != RET_OK:
            logger.error(f"Subscribe failed for {code}: {err}")
            return await _fallback_yfinance_quote(ticker)

        # Get quote data
        ret, data = client.get_stock_quote([code])
        if ret != RET_OK or data is None or len(data) == 0:
            logger.warning(f"No quote data for {code}")
            return await _fallback_yfinance_quote(ticker)

        row = data.iloc[0] if isinstance(data, pd.DataFrame) else data

        return {
            "ticker": ticker,
            "market": market,
            "last_price": float(row.get("last_price", 0)),
            "open_price": float(row.get("open_price", 0)),
            "high_price": float(row.get("high_price", 0)),
            "low_price": float(row.get("low_price", 0)),
            "prev_close_price": float(row.get("prev_close_price", 0)),
            "volume": float(row.get("volume", 0)),
            "turnover": float(row.get("turnover", 0)),
            "turnover_rate": float(row.get("turnover_rate", 0)),
            "bid_price": float(row.get("bid_price", 0)),
            "ask_price": float(row.get("ask_price", 0)),
            "bid_qty": float(row.get("bid_qty", 0)),
            "ask_qty": float(row.get("ask_qty", 0)),
            "price_spread": float(row.get("price_spread", 0)),
            "update_time": str(row.get("update_time", datetime.now())),
        }
    except Exception as e:
        logger.error(f"Error fetching quote for {code}: {e}")
        return await _fallback_yfinance_quote(ticker)


async def fetch_tick_data(ticker: str, market: str = "US", num_ticks: int = 100) -> pd.DataFrame:
    """
    Fetch recent tick-by-tick trades for a stock.

    Returns DataFrame with columns:
    - time, price, volume, turnover
    - ticker_direction (BUY/SELL/NEUTRAL)
    - type (AUTO_MATCH, ODD_LOT, AUCTION, etc.)
    """
    if not _HAS_MOOMOO:
        logger.warning("moomoo-api not available")
        return pd.DataFrame()

    client = MoomooClient.get_client()
    if client is None:
        return pd.DataFrame()

    code = get_moomoo_code(ticker, market)

    try:
        # Subscribe to ticker data
        ret_sub, err = client.subscribe([code], [SubType.TICKER], subscribe_push=False)
        if ret_sub != RET_OK:
            logger.error(f"Ticker subscribe failed for {code}: {err}")
            return pd.DataFrame()

        # Get recent ticks
        ret, data = client.get_rt_ticker(code, num=num_ticks)
        if ret != RET_OK or data is None or len(data) == 0:
            logger.warning(f"No tick data for {code}")
            return pd.DataFrame()

        if isinstance(data, pd.DataFrame):
            return data

        return pd.DataFrame([data])

    except Exception as e:
        logger.error(f"Error fetching tick data for {code}: {e}")
        return pd.DataFrame()


async def fetch_order_book(ticker: str, market: str = "US") -> dict:
    """
    Fetch order book (Level 2 market depth).

    Returns bid/ask prices and quantities for multiple levels.
    """
    if not _HAS_MOOMOO:
        return {}

    client = MoomooClient.get_client()
    if client is None:
        return {}

    code = get_moomoo_code(ticker, market)

    try:
        ret_sub, err = client.subscribe([code], [SubType.ORDER_BOOK], subscribe_push=False)
        if ret_sub != RET_OK:
            return {}

        ret, data = client.get_order_book(code)
        if ret != RET_OK or data is None:
            return {}

        # Parse order book
        order_book = {
            "ticker": ticker,
            "market": market,
            "bids": [],
            "asks": [],
            "update_time": datetime.now().isoformat(),
        }

        if isinstance(data, pd.DataFrame):
            for _, row in data.iterrows():
                if row.get("price", 0) > 0:
                    side = row.get("side", "")
                    if side == "B" or "bid" in str(side).lower():
                        order_book["bids"].append({
                            "price": float(row.get("price", 0)),
                            "qty": float(row.get("qty", 0)),
                        })
                    elif side == "A" or "ask" in str(side).lower():
                        order_book["asks"].append({
                            "price": float(row.get("price", 0)),
                            "qty": float(row.get("qty", 0)),
                        })

        return order_book

    except Exception as e:
        logger.error(f"Error fetching order book for {code}: {e}")
        return {}


async def fetch_market_snapshot(market: str = "US") -> pd.DataFrame:
    """
    Fetch market snapshot for all subscribed stocks.
    Useful for getting broad market overview.
    """
    if not _HAS_MOOMOO:
        return pd.DataFrame()

    client = MoomooClient.get_client()
    if client is None:
        return pd.DataFrame()

    try:
        ret, data = client.get_market_snapshot(market=market.upper())
        if ret != RET_OK or data is None:
            return pd.DataFrame()

        return data if isinstance(data, pd.DataFrame) else pd.DataFrame([data])

    except Exception as e:
        logger.error(f"Error fetching market snapshot: {e}")
        return pd.DataFrame()


async def _fallback_yfinance_quote(ticker: str) -> dict:
    """Fallback to yfinance when moomoo is unavailable."""
    try:
        import yfinance as yf
        data = yf.download(ticker, period="1d", progress=False, auto_adjust=True)
        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.get_level_values(0)

        if len(data) == 0:
            return {"ticker": ticker, "last_price": 0.0, "source": "yfinance_fallback"}

        last_row = data.iloc[-1]
        return {
            "ticker": ticker,
            "last_price": float(last_row.get("Close", 0)),
            "open_price": float(last_row.get("Open", 0)),
            "high_price": float(last_row.get("High", 0)),
            "low_price": float(last_row.get("Low", 0)),
            "volume": float(last_row.get("Volume", 0)),
            "source": "yfinance_fallback",
            "update_time": datetime.now().isoformat(),
        }
    except Exception as e:
        logger.error(f"yfinance fallback failed: {e}")
        return {"ticker": ticker, "last_price": 0.0, "source": "error"}


# For compatibility with existing fetcher.py
async def fetch_stock_data_moomoo(ticker: str, period_days: int = 60) -> pd.DataFrame:
    """
    Fetch historical data via moomoo K-line data.
    Note: moomoo is optimized for real-time data; for extensive historical analysis,
    yfinance may still be preferred.
    """
    if not _HAS_MOOMOO:
        from app.data.fetcher import fetch_stock_data
        return await fetch_stock_data(ticker, period_days // 30)

    client = MoomooClient.get_client()
    if client is None:
        from app.data.fetcher import fetch_stock_data
        return await fetch_stock_data(ticker, period_days // 30)

    code = get_moomoo_code(ticker, "US")

    try:
        # Fetch daily K-line data
        ret, data = client.get_cur_kline(
            code,
            ktype=ft.KLType.K_DAY,
            klnum=period_days,
            autype=ft.KLType.QFQ  # Adjusted for splits/dividends
        )

        if ret != RET_OK or data is None or len(data) == 0:
            logger.warning(f"No K-line data for {code}, falling back to yfinance")
            from app.data.fetcher import fetch_stock_data
            return await fetch_stock_data(ticker, period_days // 30)

        # Rename columns to match existing format
        df = data.rename(columns={
            "time": "Date",
            "open": "Open",
            "high": "High",
            "low": "Low",
            "close": "Close",
            "volume": "Volume",
        })

        df = df[["Date", "Open", "High", "Low", "Close", "Volume"]]
        df["Date"] = pd.to_datetime(df["Date"])
        df = df.set_index("Date")

        # Add technical indicators
        from app.data.fetcher import add_indicators
        df = add_indicators(df)

        return df

    except Exception as e:
        logger.error(f"Error fetching K-line data for {code}: {e}")
        from app.data.fetcher import fetch_stock_data
        return await fetch_stock_data(ticker, period_days // 30)
