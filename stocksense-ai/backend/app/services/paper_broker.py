"""Paper broker facade: local demo simulation or moomoo SIMULATE account."""
from __future__ import annotations

import threading
import uuid
from datetime import datetime, timezone

from app.core.config import get_settings
from app.data import moomoo_trade_client as moomoo
from app.schemas.risk import OrderExecution, OrderIntent, OrderSide, PortfolioPosition, PortfolioSnapshot

_DEMO_ACCOUNT_ID = "DEMO-PAPER"
_DEMO_START_EQUITY = 100_000.0
# The demo order book lives only as long as this process; reconciliation needs
# this floor so orders from an earlier process are not reported as missing.
_DEMO_STARTED_AT = datetime.now(timezone.utc)

_demo_lock = threading.Lock()
_demo_cash = _DEMO_START_EQUITY
_demo_positions: dict[str, PortfolioPosition] = {}
_demo_orders: list[dict] = []


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
    global _demo_cash, _demo_positions, _demo_orders
    with _demo_lock:
        _demo_cash = _DEMO_START_EQUITY
        _demo_positions = {}
        _demo_orders = []


def list_demo_orders(limit: int = 200) -> list[dict]:
    with _demo_lock:
        return [dict(o) for o in _demo_orders[-limit:]]


def demo_started_at() -> datetime:
    return _DEMO_STARTED_AT


def list_orders(limit: int = 200) -> list[dict]:
    """Broker-side order view used for ledger↔broker reconciliation."""
    if get_settings().demo_mode:
        return list_demo_orders(limit)
    return moomoo.list_paper_orders(limit)


def _demo_execute(intent: OrderIntent) -> OrderExecution:
    global _demo_cash
    notional = intent.quantity * intent.price
    order_id = f"DEMO-{uuid.uuid4().hex[:12].upper()}"
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
        _demo_orders.append({
            "order_id": order_id,
            "ticker": intent.ticker,
            "side": intent.side.value,
            "quantity": float(intent.quantity),
            "price": float(intent.price),
            "status": "filled",
            "remark": f"stocksense:{(intent.idempotency_key or intent.strategy_id or 'manual')[:48]}",
            "ts": datetime.now(timezone.utc).isoformat(),
        })
    return OrderExecution(
        status="filled",
        order_id=order_id,
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
