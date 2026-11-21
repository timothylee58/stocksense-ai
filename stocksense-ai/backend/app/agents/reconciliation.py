"""Ledger ↔ broker reconciliation (Phase 3).

Compares the decision ledger's execution rows with the broker's paper order
list.  A filled/submitted ledger row whose order id never reached the broker,
or a broker order the ledger never recorded, is a blocking break.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from app.agents.bindings import AgentBindings
from app.services import decision_ledger

REAL_STATUSES = {"filled", "submitted", "partially_filled"}


def reconcile(ledger_rows: list[dict], broker_orders: list[dict]) -> dict:
    executions = [
        r for r in ledger_rows
        if r.get("event_type") == "execution" and r.get("order_id")
    ]
    broker_by_id = {
        str(o.get("order_id")): o for o in broker_orders if o.get("order_id")
    }
    ledger_ids = {str(r["order_id"]) for r in executions}
    broker_ids = set(broker_by_id)

    missing_at_broker = sorted(ledger_ids - broker_ids)
    untracked_at_ledger = sorted(broker_ids - ledger_ids)

    breaks: list[str] = []
    if missing_at_broker:
        breaks.append(f"ledger orders missing at broker: {missing_at_broker}")
    if untracked_at_ledger:
        breaks.append(f"broker orders missing from ledger: {untracked_at_ledger}")

    by_status: dict[str, int] = {}
    for row in executions:
        status = str(row.get("status", "unknown"))
        by_status[status] = by_status.get(status, 0) + 1

    return {
        "matched": len(ledger_ids & broker_ids),
        "ledger_executions": len(executions),
        "broker_orders": len(broker_ids),
        "by_status": by_status,
        "missing_at_broker": missing_at_broker,
        "untracked_at_ledger": untracked_at_ledger,
        "breaks": breaks,
        "ok": not breaks,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


def _parse_event_time(value) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        stamp = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    return stamp if stamp.tzinfo else stamp.replace(tzinfo=timezone.utc)


def drop_demo_order_rows(rows: list[dict]) -> list[dict]:
    """Demo-mode fills never reach a broker, so they can never reconcile."""
    return [r for r in rows if not str(r.get("order_id") or "").startswith("DEMO-")]


async def reconciliation_snapshot(bindings: AgentBindings) -> dict:
    rows, orders = await asyncio.gather(
        asyncio.to_thread(decision_ledger.list_decisions, 500),
        bindings.open_orders("auditor"),
    )
    from app.core.config import get_settings
    from app.services import paper_broker

    if get_settings().demo_mode:
        start = paper_broker.demo_started_at()
        rows = [
            r for r in rows
            if (stamp := _parse_event_time(r.get("event_time"))) is not None and stamp >= start
        ]
    else:
        rows = drop_demo_order_rows(rows)
    return reconcile(rows, orders)
