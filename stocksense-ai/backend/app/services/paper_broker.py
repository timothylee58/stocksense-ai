"""Paper broker facade: local demo simulation or moomoo SIMULATE account."""
from __future__ import annotations

import threading
import uuid

from app.core.config import get_settings
from app.data import moomoo_trade_client as moomoo
from app.schemas.risk import OrderExecution, OrderIntent, OrderSide, PortfolioPosition, PortfolioSnapshot

_DEMO_ACCOUNT_ID = "DEMO-PAPER"
_DEMO_START_EQUITY = 100_000.0

_demo_lock = threading.Lock()
_demo_cash = _DEMO_START_EQUITY
_demo_positions: dict[str, PortfolioPosition] = {}


def _demo_snapshot() -> PortfolioSnapshot:
    with _demo_lock:
        positions = [p.model_copy() for p in _demo_positions.values()]
        cash = _demo_cash
    return PortfolioSnapshot(
        account_id=_DEMO_ACCOUNT_ID,
        equity=_DEMO_START_EQUITY,
        cash=cash,
        day_pnl=0.0,
        peak_equity=_DEMO_START_EQUITY,
        positions=positions,
    )


def reset_demo() -> None:
    global _demo_cash, _demo_positions
    with _demo_lock:
        _demo_cash = _DEMO_START_EQUITY
        _demo_positions = {}


def _demo_execute(intent: OrderIntent) -> OrderExecution:
    global _demo_cash
    notional = intent.quantity * intent.price
    with _demo_lock:
        pos = _demo_positions.get(intent.ticker)
        if intent.side == OrderSide.BUY:
            _demo_cash -= notional
            qty = (pos.quantity if pos else 0.0) + intent.quantity
        else:
            _demo_cash += notional
            qty = (pos.quantity if pos else 0.0) - intent.quantity
        if qty <= 1e-9:
            _demo_positions.pop(intent.ticker, None)
        else:
            _demo_positions[intent.ticker] = PortfolioPosition(
                ticker=intent.ticker,
                quantity=qty,
                market_value=qty * intent.price,
            )
    return OrderExecution(
        status="filled",
        order_id=f"DEMO-{uuid.uuid4().hex[:12].upper()}",
        message="local simulation fill at requested price; no broker order sent",
        dry_run=False,
    )


def account_status() -> dict:
    settings = get_settings()
    if settings.demo_mode:
        snap = _demo_snapshot()
        return {
            "verified": True,
            "source": "demo",
            "mode": "local-simulation",
            "trd_env": "SIMULATE",
            "account_id": snap.account_id,
            "currency": "USD",
            "equity": snap.equity,
            "cash": snap.cash,
            "market_value": round(sum(p.market_value for p in snap.positions), 2),
        }
    return moomoo.verify_paper_guard()


def get_portfolio() -> PortfolioSnapshot:
    if get_settings().demo_mode:
        return _demo_snapshot()
    return moomoo.get_paper_portfolio()


def execute_order(intent: OrderIntent) -> OrderExecution:
    if get_settings().demo_mode:
        return _demo_execute(intent)
    return moomoo.place_paper_order(intent)
