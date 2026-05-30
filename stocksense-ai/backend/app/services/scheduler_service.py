"""APScheduler jobs — daily 9AM MYT ingestion."""
from __future__ import annotations
import logging

logger = logging.getLogger(__name__)


async def run_daily_ingestion() -> None:
    """Entry point for APScheduler. Imports ingestion_service to avoid circular imports."""
    from app.services.ingestion_service import run_daily_ingestion as _run
    logger.info("APScheduler: triggering daily ingestion")
    await _run()
