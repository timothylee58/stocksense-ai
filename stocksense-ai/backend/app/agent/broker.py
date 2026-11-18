"""Broker interface + an in-memory simulator for dry runs and tests.

Implement `Broker` for the Moomoo paper account (MCP or OpenAPI
TrdEnv.SIMULATE); the agent never touches broker specifics directly.
"""
from __future__ import annotations

import math
from typing import Protocol

from app.agent.models import Account, Fill, Position, Side


class Broker(Protocol):
    def get_account(self) -> Account: ...
    def update_prices(self, prices: dict[str, float]) -> None: ...
    def place_order(self, ticker: str, side: Side, qty: float, price: float,
                    stop_loss: float | None = None) -> Fill | None: ...


class SimBroker:
    """Fills instantly at price +/- slippage. Starts with $100k like the challenge."""

    def __init__(self, cash: float = 100_000.0, slippage_bps: float = 5.0,
                 commission_per_order: float = 1.0):
        self._acct = Account(cash=cash)
        self.slip = slippage_bps / 10_000
        self.commission = commission_per_order

    def get_account(self) -> Account:
        return self._acct

    def update_prices(self, prices: dict[str, float]) -> None:
        self._acct.prices.update(prices)

    def place_order(self, ticker: str, side: Side, qty: float, price: float,
                    stop_loss: float | None = None) -> Fill | None:
        a = self._acct
        if not (0 < qty < float("inf") and 0 < price < float("inf")):   # rejects NaN/inf too
            return None
        if side == "BUY":
            px = price * (1 + self.slip)
            cost = qty * px + self.commission
            if cost > a.cash:
                return None
            a.cash -= cost
            pos = a.positions.get(ticker)
            # entry commission is folded into the cost basis so sell PnL reconciles with cash
            if pos:
                total = pos.qty + qty
                pos.avg_price = (pos.avg_price * pos.qty + px * qty + self.commission) / total
                pos.qty = total
                if stop_loss and math.isfinite(stop_loss) and stop_loss > 0:
                    pos.stop_loss = max(pos.stop_loss or 0.0, stop_loss)   # ratchet up only
            else:
                a.positions[ticker] = Position(ticker, qty, (px * qty + self.commission) / qty, stop_loss)
            a.prices[ticker] = price
            return Fill(ticker, "BUY", qty, px, self.commission, None)
        pos = a.positions.get(ticker)
        if not pos:
            return None
        qty = min(qty, pos.qty)
        px = price * (1 - self.slip)
        pnl = (px - pos.avg_price) * qty - self.commission
        a.cash += qty * px - self.commission
        pos.qty -= qty
        if pos.qty <= 1e-9:
            del a.positions[ticker]
        a.prices[ticker] = price
        return Fill(ticker, "SELL", qty, px, self.commission, pnl)
