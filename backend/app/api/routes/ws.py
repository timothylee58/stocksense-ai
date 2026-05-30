import asyncio
import json
import datetime
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import yfinance as yf

router = APIRouter()

def _is_market_hours() -> bool:
    """Return True during approximate US market hours (Mon-Fri 9:30-16:00 ET)."""
    now = datetime.datetime.utcnow()
    # UTC offset for ET: -4 (EDT) or -5 (EST) — use -4 as approx
    et_hour = (now.hour - 4) % 24
    return now.weekday() < 5 and 9 <= et_hour < 16

def _fetch_price(ticker: str) -> float | None:
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period="1d", interval="1m")
        if hist.empty:
            return None
        return float(hist['Close'].iloc[-1])
    except Exception:
        return None

@router.websocket("/ws/ticker/{ticker}")
async def ticker_ws(websocket: WebSocket, ticker: str):
    """
    WebSocket that pushes price updates every 60s during market hours,
    every 300s outside market hours.
    """
    await websocket.accept()
    ticker = ticker.upper()
    try:
        while True:
            price = _fetch_price(ticker)
            msg = {
                "ticker": ticker,
                "price": price,
                "market_open": _is_market_hours(),
                "timestamp": datetime.datetime.utcnow().isoformat(),
            }
            await websocket.send_text(json.dumps(msg))
            interval = 60 if _is_market_hours() else 300
            await asyncio.sleep(interval)
    except WebSocketDisconnect:
        pass
