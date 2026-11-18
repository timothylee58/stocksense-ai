"""Paper trading endpoints: guard, risk gate, ledger, execution."""
from __future__ import annotations

import asyncio
import hmac
import logging
import uuid

from fastapi import APIRouter, Header, HTTPException, Query

from app.core.config import get_settings
from app.core.redis_client import get_redis
from app.data.moomoo_trade_client import PaperTradeError
from app.schemas.risk import (
    KillSwitchRequest,
    OrderExecution,
    OrderIntent,
    PortfolioSnapshot,
    RiskCheck,
    RiskDecision,
    RiskLimits,
)
from app.services import decision_ledger, paper_broker
from app.services.risk_gate import evaluate_order, get_kill_switch, set_kill_switch

logger = logging.getLogger(__name__)
router = APIRouter()
settings = get_settings()


def _require_admin(x_admin_token: str = Header(default="", alias="X-Admin-Token")) -> str:
    expected = settings.admin_api_token or settings.secret_key
    if not expected or not hmac.compare_digest(x_admin_token, expected):
        raise HTTPException(status_code=401, detail="Invalid admin token")
    return "admin"


async def _claim_idempotency(key: str) -> bool:
    try:
        r = get_redis()
        return bool(await r.set(f"order:idem:{key}", "1", nx=True, ex=86_400))
    except Exception:
        return True


def _rejected_guard_decision(intent: OrderIntent, code: str, message: str) -> RiskDecision:
    return RiskDecision(
        decision_id=str(uuid.uuid4()),
        approved=False,
        reason_codes=[code],
        checks=[RiskCheck(name="account_guard", passed=False, code=code, detail=message)],
        order=intent,
        notional=round(intent.quantity * intent.price, 2),
    )


@router.get("/trading/account")
async def trading_account():
    """Paper account snapshot + guard status. Never returns live account data."""
    try:
        status, portfolio, kill = await asyncio.gather(
            asyncio.to_thread(paper_broker.account_status),
            asyncio.to_thread(paper_broker.get_portfolio),
            get_kill_switch(),
        )
    except PaperTradeError as exc:
        raise HTTPException(status_code=503, detail={"code": exc.code, "message": exc.message})
    except Exception as exc:
        logger.warning("Account snapshot failed: %s", exc)
        raise HTTPException(status_code=503, detail={"code": "ACCOUNT_UNAVAILABLE", "message": str(exc)})
    return {
        "account": status,
        "portfolio": portfolio.model_dump(mode="json"),
        "kill_switch": kill.model_dump(mode="json"),
    }


@router.get("/trading/positions")
async def trading_positions():
    try:
        portfolio: PortfolioSnapshot = await asyncio.to_thread(paper_broker.get_portfolio)
    except PaperTradeError as exc:
        raise HTTPException(status_code=503, detail={"code": exc.code, "message": exc.message})
    return portfolio.model_dump(mode="json")


@router.get("/trading/decisions")
async def trading_decisions(
    limit: int = Query(default=50, ge=1, le=500),
    ticker: str | None = Query(default=None),
):
    records = await asyncio.to_thread(decision_ledger.list_decisions, limit, ticker)
    return {"count": len(records), "decisions": records}


@router.post("/trading/orders")
async def submit_order(intent: OrderIntent, x_agent_id: str = Header(default="agent", alias="X-Agent-Id")):
    """Evaluate, ledger, then (only if approved and not dry-run) submit.

    Returns a structured decision even when blocked, so the agent can explain
    every rejection from the same payload.
    """
    actor = x_agent_id.strip() or "agent"
    if not intent.idempotency_key:
        intent.idempotency_key = f"auto-{uuid.uuid4()}"

    try:
        portfolio = await asyncio.to_thread(paper_broker.get_portfolio)
    except PaperTradeError as exc:
        return await _guard_rejection(intent, exc.code, exc.message, actor)
    except Exception as exc:
        logger.warning("Account guard failed: %s", exc)
        return await _guard_rejection(intent, "ACCOUNT_UNAVAILABLE", str(exc), actor)

    kill = await get_kill_switch()
    decision = evaluate_order(
        decision_id=str(uuid.uuid4()),
        intent=intent,
        portfolio=portfolio,
        limits=RiskLimits.from_settings(),
        kill_switch=kill,
    )
    ledger_store = await asyncio.to_thread(decision_ledger.record_decision, decision, actor)
    payload = {"decision": decision.model_dump(mode="json"), "execution": None, "ledger": ledger_store}

    if not decision.approved:
        return payload

    if ledger_store == "unavailable":
        payload["execution"] = OrderExecution(
            status="failed",
            message="decision ledger unavailable; order not sent (fail-closed)",
            dry_run=False,
        ).model_dump(mode="json")
        return payload

    if intent.dry_run:
        payload["execution"] = OrderExecution(
            status="dry_run",
            message="approved; no order sent (dry_run=true)",
        ).model_dump(mode="json")
        return payload

    if not await _claim_idempotency(intent.idempotency_key):
        execution = OrderExecution(
            status="duplicate_blocked",
            message=f"idempotency_key {intent.idempotency_key} was already used",
            dry_run=False,
        )
        payload["execution"] = execution.model_dump(mode="json")
        payload["ledger_execution"] = await asyncio.to_thread(
            decision_ledger.record_execution, decision, execution, actor
        )
        return payload

    try:
        execution = await asyncio.to_thread(paper_broker.execute_order, intent)
    except PaperTradeError as exc:
        execution = OrderExecution(
            status="failed",
            message=f"{exc.code}: {exc.message}",
            dry_run=False,
        )
    except Exception as exc:
        logger.error("Paper execution failed: %s", exc)
        execution = OrderExecution(status="failed", message=str(exc), dry_run=False)

    payload["execution"] = execution.model_dump(mode="json")
    payload["ledger_execution"] = await asyncio.to_thread(
        decision_ledger.record_execution, decision, execution, actor
    )
    return payload


async def _guard_rejection(intent: OrderIntent, code: str, message: str, actor: str) -> dict:
    decision = _rejected_guard_decision(intent, code, message)
    store = await asyncio.to_thread(decision_ledger.record_decision, decision, actor)
    return {"decision": decision.model_dump(mode="json"), "execution": None, "ledger": store}


@router.get("/risk/kill-switch")
async def read_kill_switch():
    return (await get_kill_switch()).model_dump(mode="json")


@router.post("/risk/kill-switch")
async def write_kill_switch(
    body: KillSwitchRequest,
    x_admin_token: str = Header(default="", alias="X-Admin-Token"),
    x_agent_id: str = Header(default="admin", alias="X-Agent-Id"),
):
    _require_admin(x_admin_token)
    state = await set_kill_switch(body.enabled, body.reason, x_agent_id)
    logger.warning("Kill switch set to %s by %s: %s", body.enabled, x_agent_id, body.reason)
    return state.model_dump(mode="json")
