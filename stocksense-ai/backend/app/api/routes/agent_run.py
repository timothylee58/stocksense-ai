"""Agent run + journal endpoints (Phase 1–3 rollout surface)."""
from __future__ import annotations

import hmac
import logging
from datetime import date, datetime
from typing import Literal

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field

from app.agents.bindings import LocalBindings, PolicyViolation
from app.agents.journal import Journal, JournalUnavailable
from app.agents.reconciliation import reconciliation_snapshot
from app.agents.runtime import AgentRuntime
from app.core.config import get_settings

logger = logging.getLogger(__name__)
router = APIRouter()


class RunRequest(BaseModel):
    phase: Literal["shadow", "paper"] = "shadow"
    session_date: date | None = None
    symbols: list[str] | None = Field(default=None, max_length=10)


class PublicEvent(BaseModel):
    seq: int
    run_id: str
    strategy_version: str
    event_type: str
    recorded_at: datetime
    hash: str


class PublicNameStatus(BaseModel):
    symbol: str
    status: str


class PublicRun(BaseModel):
    run_id: str
    session_date: date
    strategy_version: str
    status: str
    per_name_status: list[PublicNameStatus] = Field(default_factory=list)


class PublicAudit(BaseModel):
    run_id: str
    decisions: int
    executions: int
    hash_chain_ok: bool
    break_count: int


def _authorize(token: str) -> None:
    settings = get_settings()
    expected = settings.admin_api_token
    if not expected and settings.demo_mode:
        return
    expected = expected or settings.secret_key
    if not expected or not hmac.compare_digest(token, expected):
        raise HTTPException(status_code=401, detail="Invalid admin token")


@router.post("/agents/run")
async def run_agent_session(
    body: RunRequest,
    x_admin_token: str = Header(default="", alias="X-Admin-Token"),
):
    """Run one paper session. Never places a live order; shadow places none at all."""
    _authorize(x_admin_token)
    if get_settings().read_only_mode:
        raise HTTPException(
            status_code=403,
            detail={"code": "READ_ONLY_MODE", "message": "sessions run on the local paper stack, not the demo deployment"},
        )
    runtime = AgentRuntime(phase=body.phase, symbols=body.symbols)
    try:
        return await runtime.run_session(session_date=body.session_date, phase=body.phase)
    except PolicyViolation as exc:
        raise HTTPException(status_code=403, detail={"code": exc.code, "message": str(exc)})
    except JournalUnavailable as exc:
        raise HTTPException(status_code=503, detail={"code": "JOURNAL_UNAVAILABLE", "message": str(exc)})
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/agents/runs")
async def list_agent_runs(limit: int = Query(default=20, ge=1, le=200)):
    return {"runs": Journal().runs(limit)}


@router.get("/agents/runs/{run_id}")
async def get_agent_run(run_id: str):
    journal = Journal()
    events = journal.read(run_id=run_id)
    if not events:
        raise HTTPException(status_code=404, detail=f"unknown run {run_id!r}")
    audit = next((e["payload"] for e in reversed(events) if e.get("event_type") == "audit"), None)
    final = next((e["payload"] for e in reversed(events) if e.get("event_type") == "run_finished"), None)
    record = (final or {}).get("run_record")
    return {
        "run_id": run_id,
        "projection": "metadata_only",
        "events": [PublicEvent.model_validate(event).model_dump(mode="json") for event in events],
        "audit": PublicAudit.model_validate({**audit, "break_count": len(audit.get("breaks", []))}).model_dump(mode="json") if audit else None,
        "run": PublicRun.model_validate(record).model_dump(mode="json") if record else None,
    }


@router.get("/agents/journal/verify")
async def verify_agent_journal():
    ok, breaks = Journal().verify()
    return {
        "hash_chain_ok": ok,
        "breaks": [f"Integrity failure {index + 1}; inspect the local journal" for index in range(len(breaks))],
    }


@router.get("/agents/reconciliation")
async def agent_reconciliation():
    """Compare ledger executions with the broker's paper order list."""
    try:
        return await reconciliation_snapshot(LocalBindings())
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail={"code": "RECONCILIATION_UNAVAILABLE", "message": str(exc)},
        )
