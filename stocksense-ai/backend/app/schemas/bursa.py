"""Pydantic response schemas for Bursa Malaysia endpoints.

Using these as response_model= gives automatic OpenAPI docs + validation.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class BursaStockSchema(BaseModel):
    code: str
    ticker: str
    name: str
    sector: str
    market: str = "MY"
    last_price: float
    open_price: float
    high_price: float
    low_price: float
    prev_close_price: float
    bid_price: float
    ask_price: float
    volume: float
    change_pct: float
    change_abs: float
    source: str | None = None
    update_time: str | None = None


class SectorSnapshotSchema(BaseModel):
    sector: str
    color: str
    count: int
    avg_change: float
    stocks: list[str]


class MarketSnapshotSchema(BaseModel):
    quotes: list[BursaStockSchema]
    gainers: list[BursaStockSchema]
    losers: list[BursaStockSchema]
    sectors: list[SectorSnapshotSchema]
    total: int
    active: int
    timestamp: str
    demo: bool = False


class ScreenerResultSchema(BaseModel):
    results: list[BursaStockSchema]
    count: int


class BursaPredictionSchema(BaseModel):
    code: str
    ticker: str
    direction: str = Field(..., pattern="^(UP|DOWN|HOLD)$")
    confidence: float = Field(..., ge=0.0, le=1.0)
    score: float
    rsi: float | None = None
    macd: float | None = None
    macd_signal: float | None = None
    bb_upper: float | None = None
    bb_lower: float | None = None
    current_price: float | None = None
    momentum_5d: float | None = None
    momentum_20d: float | None = None
    vol_ratio: float | None = None
    signals: list[str] = []
    error: str | None = None
    demo: bool = False
