"""Broker interface + an in-memory simulator for dry runs and tests.

Implement `Broker` for the Moomoo paper account (MCP or OpenAPI
TrdEnv.SIMULATE); the agent never touches broker specifics directly.
"""
from __future__ import annotations

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
        if qty <= 0 or price <= 0:
            return None
        if side == "BUY":
            px = price * (1 + self.slip)
            cost = qty * px + self.commission
            if cost > a.cash:
                return None
            a.cash -= cost
            pos = a.positions.get(ticker)
            if pos:
                total = pos.qty + qty
                pos.avg_price = (pos.avg_price * pos.qty + px * qty) / total
                pos.qty = total
            else:
                a.positions[ticker] = Position(ticker, qty, px, stop_loss)
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
