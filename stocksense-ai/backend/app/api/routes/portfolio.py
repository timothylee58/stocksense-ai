"""Ops dashboard endpoints: P&L summary, equity curve, rejected orders."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query

from app.core.config import get_settings
from app.data.moomoo_trade_client import PaperTradeError
from app.services import decision_ledger, paper_broker, portfolio_history
from app.services.risk_gate import get_kill_switch

logger = logging.getLogger(__name__)
router = APIRouter()
settings = get_settings()


@router.get("/portfolio/summary")
async def portfolio_summary():
    """Live account P&L plus ledger counts. Records an equity snapshot."""
    try:
        account, portfolio, kill = await asyncio.gather(
            asyncio.to_thread(paper_broker.account_status),
            asyncio.to_thread(paper_broker.get_portfolio),
            get_kill_switch(),
        )
    except PaperTradeError as exc:
        raise HTTPException(status_code=503, detail={"code": exc.code, "message": exc.message})
    except Exception as exc:
        logger.warning("Portfolio summary failed: %s", exc)
        raise HTTPException(status_code=503, detail={"code": "ACCOUNT_UNAVAILABLE", "message": str(exc)})

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
