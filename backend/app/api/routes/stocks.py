from fastapi import APIRouter

from app.core.stocks import STOCK_UNIVERSE
from app.core.redis_client import cache_get, cache_set
from app.data.moomoo_fetcher import fetch_realtime_quote, fetch_tick_data, fetch_order_book

router = APIRouter()


@router.get("/stocks")
async def list_stocks():
    """Return all supported tickers with metadata."""
    return [
        {"ticker": t, **info}
        for t, info in STOCK_UNIVERSE.items()
    ]


@router.get("/stocks/{ticker}")
async def get_stock(ticker: str):
    t = ticker.upper()

    if t in STOCK_UNIVERSE:
        return {"ticker": t, **STOCK_UNIVERSE[t]}

    for market in ["US", "MY", "HK", "SG"]:
        prefixed = f"{market}.{t}"
        if prefixed in STOCK_UNIVERSE:
            return {"ticker": prefixed, **STOCK_UNIVERSE[prefixed]}

    return {"ticker": t, "name": t, "sector": "Unknown", "market": "Unknown"}


@router.get("/stocks/{ticker}/realtime")
async def get_realtime_quote(ticker: str):
    """
    Get real-time quote from moomoo API.
    Returns last_price, bid/ask, volume, and other market data.
    Falls back to yfinance if moomoo is unavailable.
    """
    t = ticker.upper()

    market = "US"
    if t.startswith("MY."):
        market = "MY"
        symbol = t[3:]
    elif t.startswith("US."):
        market = "US"
        symbol = t[3:]
    elif t.startswith("HK."):
        market = "HK"
        symbol = t[3:]
    elif t.startswith("SG."):
        market = "SG"
        symbol = t[3:]
    else:
        symbol = t

    cache_key = f"realtime:{market}:{symbol}"
    cached = await cache_get(cache_key)
    if cached:
        cached["_cached"] = True
        return cached

    data = await fetch_realtime_quote(symbol, market)

    await cache_set(cache_key, data, 10)

    return data


@router.get("/stocks/{ticker}/ticks")
async def get_tick_data(ticker: str, num_ticks: int = 50):
    """
    Get recent tick-by-tick trade data from moomoo.
    Returns up to 500 recent trades with price, volume, and direction.
    """
    t = ticker.upper()

    market = "US"
    if t.startswith("MY."):
        market = "MY"
        symbol = t[3:]
    elif t.startswith("US."):
        market = "US"
        symbol = t[3:]
    else:
        symbol = t

    ticks_df = await fetch_tick_data(symbol, market, num_ticks)

    if ticks_df.empty:
        return {"ticker": ticker, "ticks": [], "count": 0}

    ticks = ticks_df.to_dict(orient="records")

    return {"ticker": ticker, "ticks": ticks, "count": len(ticks)}


@router.get("/stocks/{ticker}/orderbook")
async def get_order_book(ticker: str):
    """
    Get Level 2 order book (market depth) from moomoo.
    Returns bid/ask prices and quantities at multiple levels.
    """
    t = ticker.upper()

    market = "US"
    if t.startswith("MY."):
        market = "MY"
        symbol = t[3:]
    elif t.startswith("US."):
        market = "US"
        symbol = t[3:]
    else:
        symbol = t

    order_book = await fetch_order_book(symbol, market)

    if not order_book:
        return {"ticker": ticker, "bids": [], "asks": [], "error": "No data available"}

    return order_book
