"""GET /stream/{ticker} — Server-Sent Events live prediction stream."""
from __future__ import annotations
import asyncio
import json
import logging
from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.services.pipeline_service import run_full_pipeline

logger = logging.getLogger(__name__)
router = APIRouter()


async def _prediction_generator(ticker: str):
    """Yield SSE events every 30 seconds."""
    ticker = ticker.upper()
    while True:
        try:
            result = await run_full_pipeline(ticker)
            payload = json.dumps(result)
            yield f"data: {payload}\n\n"
        except Exception as e:
            logger.error("SSE stream error for %s: %s", ticker, e)
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
        await asyncio.sleep(30)


@router.get("/stream/{ticker}")
async def stream_prediction(ticker: str):
    """
    SSE endpoint — streams prediction updates every 30 seconds.
    Client: const es = new EventSource('/api/stream/NVDA');
    """
    return StreamingResponse(
        _prediction_generator(ticker),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )
