import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.core.config import get_settings
from app.api.router import api_router

settings = get_settings()
os.makedirs(settings.models_dir, exist_ok=True)

logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler(timezone="Asia/Kuala_Lumpur")


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        from app.services.scheduler_service import run_daily_ingestion
        scheduler.add_job(run_daily_ingestion, "cron", hour=9, minute=0)
        scheduler.start()
        logger.info("APScheduler started — daily ingestion at 9AM MYT")
    except Exception as e:
        logger.warning("Scheduler init failed (non-fatal): %s", e)
    yield
    if scheduler.running:
        scheduler.shutdown()


app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    description="ML-powered stock anomaly detection + directional prediction",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.api_prefix)


@app.get("/")
async def read_root():
    return {"status": "StockSense AI API is running", "version": "2.0.0"}


@app.get("/health")
async def health():
    return {"status": "ok", "version": "2.0.0"}
