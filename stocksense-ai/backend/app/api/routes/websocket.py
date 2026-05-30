"""
WebSocket endpoint: streams live price updates for a ticker.
60s during market hours, 300s otherwise.
"""

import asyncio
import logging
from datetime import datetime

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.data.fetcher import get_latest_price

logger = logging.getLogger(__name__)
router = APIRouter()


def _is_market_hours() -> bool:
    now = datetime.utcnow()
    # NYSE: Mon-Fri 13:30-20:00 UTC
    if now.weekday() >= 5:
        return False
    return 13 * 60 + 30 <= now.hour * 60 + now.minute <= 20 * 60


@router.websocket("/ws/ticker/{ticker}")
async def ws_ticker(websocket: WebSocket, ticker: str):
    await websocket.accept()
    t = ticker.upper()
    try:
        while True:
            price = await get_latest_price(t)
            await websocket.send_json({"ticker": t, "price": round(price, 2), "ts": datetime.utcnow().isoformat()})
            interval = 60 if _is_market_hours() else 300
            await asyncio.sleep(interval)
    except WebSocketDisconnect:
        logger.info("WS disconnected: %s", t)
    except Exception as exc:
        logger.warning("WS error for %s: %s", t, exc)
