"""Ops dashboard endpoints: P&L summary, equity curve, rejected orders."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Query

from app.core.config import get_settings
from app.data.moomoo_trade_client import PaperTradeError
from app.services import decision_ledger, paper_broker, portfolio_history
from app.services.risk_gate import get_kill_switch

logger = logging.getLogger(__name__)
router = APIRouter()
settings = get_settings()


async def _stale_summary(code: str, message: str) -> dict:
    try:
        points, baseline = await asyncio.gather(
            asyncio.to_thread(portfolio_history.list_snapshots, 1),
            asyncio.to_thread(portfolio_history.first_snapshot),
        )
    except Exception as exc:
        logger.warning("Portfolio history unavailable: %s", exc)
        points, baseline = [], None
    kill_payload = {"enabled": None, "reason": "Current risk state unavailable", "actor": "", "updated_at": None}
    if not get_settings().read_only_mode:
        try:
            kill = await get_kill_switch()
            kill_payload = kill.model_dump(mode="json")
        except Exception as exc:
            logger.warning("Current risk state unavailable: %s", exc)
    stats = await asyncio.to_thread(decision_ledger.ledger_stats)
    point = points[-1] if points else None
    equity = float(point["equity"]) if point else None
    cash = float(point["cash"]) if point else None
    market_value = float(point["market_value"]) if point else None
    day_pnl = float(point["day_pnl"]) if point else None
    baseline_equity = float(baseline["equity"]) if baseline else None
    total_pnl = equity - baseline_equity if equity is not None and baseline_equity is not None else None
    prior = equity - day_pnl if point else None
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "demo": settings.demo_mode,
        "stale": True,
        "stale_reason": {"code": code, "message": message},
        "account": {
            "verified": False,
            "source": "snapshot" if point else "unavailable",
            "trd_env": "SIMULATE",
            "account_id": "unknown",
            "currency": "USD",
        },
        "summary": {
            "equity": round(equity, 2) if equity is not None else None,
            "cash": round(cash, 2) if cash is not None else None,
            "market_value": round(market_value, 2) if market_value is not None else None,
            "day_pnl": round(day_pnl, 2) if day_pnl is not None else None,
            "day_pnl_pct": round(day_pnl / prior * 100.0, 4) if prior and prior > 0 else None,
            "baseline_equity": round(baseline_equity, 2) if baseline_equity is not None else None,
            "total_pnl": round(total_pnl, 2) if total_pnl is not None else None,
            "total_return_pct": round(total_pnl / baseline_equity * 100.0, 4) if total_pnl is not None and baseline_equity and baseline_equity > 0 else None,
            "gross_exposure_pct": round(market_value / equity * 100.0, 4) if equity and equity > 0 else None,
            "position_count": int(point["position_count"]) if point else None,
            "kill_switch_active": bool(point["kill_switch_active"]) if point else None,
            "snapshot_storage": "none",
            "captured_at": point["captured_at"] if point else None,
        },
        "positions": None,
        "kill_switch": kill_payload,
        "ledger": stats,
    }


@router.get("/portfolio/summary")
async def portfolio_summary():
    if get_settings().read_only_mode:
        return await _stale_summary("READ_ONLY_MODE", "Showing the last locally recorded paper snapshot")
    try:
        account, portfolio, kill = await asyncio.gather(
            asyncio.to_thread(paper_broker.account_status),
            asyncio.to_thread(paper_broker.get_portfolio),
            get_kill_switch(),
        )
    except PaperTradeError as exc:
        return await _stale_summary(exc.code, exc.message)
    except Exception as exc:
        logger.warning("Portfolio summary failed: %s", exc)
        return await _stale_summary("ACCOUNT_UNAVAILABLE", str(exc))

    storage = await asyncio.to_thread(portfolio_history.record_snapshot, account, portfolio, kill)
    baseline, stats = await asyncio.gather(
        asyncio.to_thread(portfolio_history.first_snapshot),
        asyncio.to_thread(decision_ledger.ledger_stats),
    )

    equity = float(account.get("equity") or portfolio.equity)
    cash = float(account.get("cash") or portfolio.cash)
    market_value = round(sum(float(p.market_value) for p in portfolio.positions), 2)
    baseline_equity = float(baseline["equity"]) if baseline else equity
    total_pnl = round(equity - baseline_equity, 2)
    day_pnl = float(portfolio.day_pnl)
    prior_equity = max(equity - day_pnl, 1e-9)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "demo": settings.demo_mode,
        "account": account,
        "summary": {
            "equity": round(equity, 2),
            "cash": round(cash, 2),
            "market_value": market_value,
            "day_pnl": round(day_pnl, 2),
            "day_pnl_pct": round(day_pnl / prior_equity * 100.0, 4),
            "baseline_equity": round(baseline_equity, 2),
            "total_pnl": total_pnl,
            "total_return_pct": round(total_pnl / max(baseline_equity, 1e-9) * 100.0, 4),
            "gross_exposure_pct": round(market_value / max(equity, 1e-9) * 100.0, 4),
            "position_count": len(portfolio.positions),
            "kill_switch_active": kill.enabled,
            "snapshot_storage": storage,
        },
        "positions": [
            {
                **p.model_dump(mode="json"),
                "allocation_pct": round(float(p.market_value) / max(equity, 1e-9) * 100.0, 4),
            }
            for p in portfolio.positions
        ],
        "kill_switch": kill.model_dump(mode="json"),
        "ledger": stats,
    }


@router.get("/portfolio/equity-curve")
async def equity_curve(limit: int = Query(default=500, ge=1, le=2000)):
    points = await asyncio.to_thread(portfolio_history.list_snapshots, limit)
    return {"count": len(points), "points": points}


@router.get("/portfolio/rejected")
async def rejected_orders(limit: int = Query(default=50, ge=1, le=500)):
    records = await asyncio.to_thread(decision_ledger.list_decisions, limit, None, "rejected")
    return {"count": len(records), "rejections": records}
