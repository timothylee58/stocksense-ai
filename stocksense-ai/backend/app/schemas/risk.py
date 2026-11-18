"""Order intent, portfolio snapshot, and risk-decision models.

All money math is float64 (Python float), per project invariant.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"


class PortfolioPosition(BaseModel):
    ticker: str
    quantity: float = 0.0
    market_value: float = 0.0


class PortfolioSnapshot(BaseModel):
    account_id: str = ""
    equity: float = Field(gt=0)
    cash: float = Field(ge=0)
    day_pnl: float = 0.0
    peak_equity: float = 0.0
    positions: list[PortfolioPosition] = Field(default_factory=list)

    def position_for(self, ticker: str) -> PortfolioPosition:
        for p in self.positions:
            if p.ticker.upper() == ticker.upper():
                return p
        return PortfolioPosition(ticker=ticker.upper())


class OrderIntent(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    ticker: str = Field(min_length=1, max_length=20)
    side: OrderSide
    quantity: float = Field(gt=0)
    price: float = Field(gt=0)
    order_type: OrderType = OrderType.MARKET
    dry_run: bool = True
    strategy_id: str = "manual"
    rationale: str = ""
    idempotency_key: str = ""
    model_version: str = ""
    feature_snapshot: dict[str, Any] = Field(default_factory=dict)

    @field_validator("ticker")
    @classmethod
    def _upper_ticker(cls, v: str) -> str:
        return v.strip().upper()

    @field_validator("strategy_id", "rationale")
    @classmethod
    def _strip_text(cls, v: str) -> str:
        return v.strip()


class RiskLimits(BaseModel):
    max_position_pct: float = 0.25
    max_gross_exposure_pct: float = 0.90
    max_order_notional: float = 50_000.0
    max_daily_loss_pct: float = 0.03
    max_drawdown_pct: float = 0.15
    min_cash_buffer_pct: float = 0.10

    @classmethod
    def from_settings(cls) -> "RiskLimits":
        from app.core.config import get_settings
        s = get_settings()
        return cls(
            max_position_pct=s.risk_max_position_pct,
            max_gross_exposure_pct=s.risk_max_gross_exposure_pct,
            max_order_notional=s.risk_max_order_notional,
            max_daily_loss_pct=s.risk_max_daily_loss_pct,
            max_drawdown_pct=s.risk_max_drawdown_pct,
            min_cash_buffer_pct=s.risk_min_cash_buffer_pct,
        )


class RiskCheck(BaseModel):
    name: str
    passed: bool
    code: str = ""
    detail: str = ""


class RiskDecision(BaseModel):
    decision_id: str
    approved: bool
    reason_codes: list[str] = Field(default_factory=list)
    checks: list[RiskCheck] = Field(default_factory=list)
    order: OrderIntent
    account_id: str = ""
    kill_switch_active: bool = False
    notional: float = 0.0
    projected_position_pct: float = 0.0
    projected_gross_pct: float = 0.0
    cash_after: float = 0.0
    day_pnl_pct: float = 0.0
    drawdown_pct: float = 0.0
    evaluated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class KillSwitchState(BaseModel):
    enabled: bool = False
    reason: str = ""
    actor: str = ""
    updated_at: datetime | None = None


class KillSwitchRequest(BaseModel):
    enabled: bool
    reason: str = Field(min_length=1, max_length=200)


class OrderExecution(BaseModel):
    status: str
    order_id: str = ""
    message: str = ""
    dry_run: bool = True
    executed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
