"""Plain data types shared by the agent modules (no heavy imports)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal

Action = Literal["BUY", "SELL", "HOLD"]
Side = Literal["BUY", "SELL"]


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class TradeSignal:
    ticker: str
    action: Action
    confidence: float            # 0.0-1.0
    price: float                 # latest price
    stop_loss: float | None = None
    source: str | None = None    # "xgb_binary" | "rule_based" | None (unknown)


@dataclass
class Position:
    ticker: str
    qty: float
    avg_price: float
    stop_loss: float | None = None


@dataclass
class Account:
    cash: float
    positions: dict[str, Position] = field(default_factory=dict)
    prices: dict[str, float] = field(default_factory=dict)

    @property
    def equity(self) -> float:
        return self.cash + sum(
            p.qty * self.prices.get(t, p.avg_price) for t, p in self.positions.items()
        )

    @property
    def gross_exposure(self) -> float:
        return sum(p.qty * self.prices.get(t, p.avg_price) for t, p in self.positions.items())


@dataclass(frozen=True)
class Fill:
    ticker: str
    side: Side
    qty: float
    price: float
    commission: float
    realized_pnl: float | None   # set on sells only
    filled_at: datetime = field(default_factory=utcnow)
