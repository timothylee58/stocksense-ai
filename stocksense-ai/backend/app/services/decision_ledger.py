"""Append-only decision ledger.

Every risk decision — approved or rejected — and every execution outcome is
persisted so the challenge judges can replay what the agent saw, what it chose,
and why.  ClickHouse is the primary store; a JSONL file is the local fallback
when ClickHouse is disabled or unreachable.
"""
from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path

from app.core.clickhouse_client import get_ch_client
from app.core.config import get_settings
from app.schemas.risk import OrderExecution, RiskDecision

logger = logging.getLogger(__name__)

_jsonl_lock = threading.Lock()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _row_from_decision(
    decision: RiskDecision,
    event_type: str,
    status: str,
    actor: str,
    order_id: str = "",
    message: str = "",
) -> dict:
    order = decision.order
    return {
        "decision_id": decision.decision_id,
        "idempotency_key": order.idempotency_key or decision.decision_id,
        "event_type": event_type,
        "status": status,
        "account_id": decision.account_id,
        "ticker": order.ticker,
        "side": order.side.value,
        "quantity": float(order.quantity),
        "price": float(order.price),
        "notional": float(decision.notional),
        "dry_run": 1 if order.dry_run else 0,
        "reason_codes": list(decision.reason_codes),
        "checks": json.dumps([c.model_dump() for c in decision.checks], ensure_ascii=False),
        "strategy_id": order.strategy_id,
        "model_version": order.model_version,
        # Column kept for schema compatibility; raw feature vectors are never stored.
        "feature_snapshot": "",
        "order_id": order_id,
        "message": message,
        "actor": actor,
        "event_time": _now(),
    }


def _write_jsonl(row: dict) -> None:
    settings = get_settings()
    path = Path(settings.decision_ledger_jsonl)
    path.parent.mkdir(parents=True, exist_ok=True)
    record = dict(row)
    record.pop("feature_snapshot", None)
    record["event_time"] = row["event_time"].isoformat()
    with _jsonl_lock:
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def _insert_row(row: dict) -> str:
    """Insert one ledger row. Returns the storage actually used."""
    client = get_ch_client()
    if client is not None:
        try:
            import pandas as pd
            ch_row = dict(row)
            ch_row["event_time"] = row["event_time"].replace(tzinfo=None)
            ch_row["ingested_at"] = _now().replace(tzinfo=None)
            client.insert_df("decision_ledger", pd.DataFrame([ch_row]))
            return "clickhouse"
        except Exception as exc:
            logger.warning("Decision ledger ClickHouse write failed, using JSONL: %s", exc)
    try:
        _write_jsonl(row)
        return "jsonl"
    except Exception as exc:
        logger.error("Decision ledger unavailable: %s", exc)
        return "unavailable"


def record_decision(decision: RiskDecision, actor: str) -> str:
    status = "approved" if decision.approved else "rejected"
    return _insert_row(_row_from_decision(decision, "decision", status, actor))


def record_execution(decision: RiskDecision, execution: OrderExecution, actor: str) -> str:
    return _insert_row(_row_from_decision(
        decision,
        event_type="execution",
        status=execution.status,
        actor=actor,
        order_id=execution.order_id,
        message=execution.message,
    ))


def _normalise(record: dict) -> dict:
    out = dict(record)
    # Older JSONL rows may carry a feature snapshot; never surface it.
    out.pop("feature_snapshot", None)
    if isinstance(out.get("event_time"), datetime):
        out["event_time"] = out["event_time"].isoformat()
    if "dry_run" in out:
        out["dry_run"] = bool(out["dry_run"])
    return out


def list_decisions(
    limit: int = 50,
    ticker: str | None = None,
    status: str | None = None,
) -> list[dict]:
    limit = max(1, min(int(limit), 500))
    clauses: list[str] = []
    params: dict = {"limit": limit}
    if ticker:
        clauses.append("ticker = {ticker:String}")
        params["ticker"] = ticker.upper()
    if status:
        clauses.append("status = {status:String}")
        params["status"] = status.lower()
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""

    client = get_ch_client()
    if client is not None:
        try:
            result = client.query(
                f"""
                SELECT decision_id, idempotency_key, event_type, status, account_id,
                       ticker, side, quantity, price, notional, dry_run,
                       reason_codes, checks, strategy_id, model_version,
                       order_id, message, actor, event_time
                FROM decision_ledger {where}
                ORDER BY event_time DESC
                LIMIT {{limit:UInt32}}
                """,
                parameters=params,
            )
            return [_normalise(r) for r in result.df().to_dict("records")] if result.row_count else []
        except Exception as exc:
            logger.warning("Decision ledger ClickHouse read failed, using JSONL: %s", exc)

    settings = get_settings()
    path = Path(settings.decision_ledger_jsonl)
    if not path.exists():
        return []
    with _jsonl_lock:
        lines = path.read_text(encoding="utf-8").splitlines()
    records: list[dict] = []
    for line in reversed(lines):
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if ticker and str(record.get("ticker", "")).upper() != ticker.upper():
            continue
        if status and str(record.get("status", "")).lower() != status.lower():
            continue
        records.append(_normalise(record))
        if len(records) >= limit:
            break
    return records


def ledger_stats() -> dict:
    """Aggregate counts for the ops dashboard."""
    zero = {
        "total_events": 0,
        "decisions": 0,
        "approved": 0,
        "rejected": 0,
        "executions": 0,
        "filled": 0,
        "dry_run": 0,
        "failed": 0,
        "duplicate_blocked": 0,
    }
    client = get_ch_client()
    if client is not None:
        try:
            result = client.query(
                """
                SELECT count() AS total_events,
                       countIf(event_type = 'decision') AS decisions,
                       countIf(status = 'approved') AS approved,
                       countIf(status = 'rejected') AS rejected,
                       countIf(event_type = 'execution') AS executions,
                       countIf(status = 'filled') AS filled,
                       countIf(status = 'dry_run') AS dry_run,
                       countIf(status = 'failed') AS failed,
                       countIf(status = 'duplicate_blocked') AS duplicate_blocked
                FROM decision_ledger
                """
            )
            if result.row_count:
                row = result.df().to_dict("records")[0]
                return {k: int(row.get(k, 0)) for k in zero}
            return zero
        except Exception as exc:
            logger.warning("Decision ledger ClickHouse stats failed, using JSONL: %s", exc)

    path = Path(get_settings().decision_ledger_jsonl)
    if not path.exists():
        return zero
    with _jsonl_lock:
        lines = path.read_text(encoding="utf-8").splitlines()
    stats = dict(zero)
    for line in lines:
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        stats["total_events"] += 1
        event_type = str(record.get("event_type", ""))
        status = str(record.get("status", ""))
        event_key = {"decision": "decisions", "execution": "executions"}.get(event_type)
        if event_key:
            stats[event_key] += 1
        if status in stats:
            stats[status] += 1
    return stats
