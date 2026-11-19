"""Durable equity snapshots for the ops dashboard.

ClickHouse is the primary store; JSONL is the local fallback when ClickHouse is
disabled or unreachable. Snapshots are appended on every summary read so the
equity curve grows from real account data instead of synthetic points.
"""
from __future__ import annotations

import json
import logging
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from app.core.clickhouse_client import get_ch_client
from app.core.config import get_settings
from app.schemas.risk import KillSwitchState, PortfolioSnapshot

logger = logging.getLogger(__name__)

_jsonl_lock = threading.Lock()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _row(
    account: dict,
    portfolio: PortfolioSnapshot,
    kill_switch: KillSwitchState,
) -> dict:
    equity = float(account.get("equity") or portfolio.equity)
    cash = float(account.get("cash") or portfolio.cash)
    market_value = round(sum(float(p.market_value) for p in portfolio.positions), 2)
    return {
        "snapshot_id": str(uuid.uuid4()),
        "account_id": portfolio.account_id or str(account.get("account_id", "")),
        "source": str(account.get("source", "")),
        "equity": equity,
        "cash": cash,
        "market_value": market_value,
        "day_pnl": float(portfolio.day_pnl),
        "gross_exposure_pct": round(market_value / max(equity, 1e-9) * 100.0, 4),
        "position_count": len(portfolio.positions),
        "kill_switch_active": 1 if kill_switch.enabled else 0,
        "captured_at": _now(),
    }


def _write_jsonl(row: dict) -> None:
    path = Path(get_settings().portfolio_history_jsonl)
    path.parent.mkdir(parents=True, exist_ok=True)
    record = dict(row)
    record["captured_at"] = row["captured_at"].isoformat()
    with _jsonl_lock:
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def record_snapshot(
    account: dict,
    portfolio: PortfolioSnapshot,
    kill_switch: KillSwitchState,
) -> str:
    """Persist one snapshot. Returns the storage used, never raises."""
    row = _row(account, portfolio, kill_switch)
    client = get_ch_client()
    if client is not None:
        try:
            import pandas as pd
            ch_row = dict(row)
            ch_row["captured_at"] = row["captured_at"].replace(tzinfo=None)
            ch_row["ingested_at"] = _now().replace(tzinfo=None)
            client.insert_df("portfolio_snapshots", pd.DataFrame([ch_row]))
            return "clickhouse"
        except Exception as exc:
            logger.warning("Portfolio snapshot ClickHouse write failed, using JSONL: %s", exc)
    try:
        _write_jsonl(row)
        return "jsonl"
    except Exception as exc:
        logger.error("Portfolio snapshot unavailable: %s", exc)
        return "unavailable"


def _normalise(record: dict) -> dict:
    out = dict(record)
    if isinstance(out.get("captured_at"), datetime):
        out["captured_at"] = out["captured_at"].isoformat()
    if "kill_switch_active" in out:
        out["kill_switch_active"] = bool(out["kill_switch_active"])
    for key in ("equity", "cash", "market_value", "day_pnl", "gross_exposure_pct"):
        if key in out:
            out[key] = float(out[key])
    if "position_count" in out:
        out["position_count"] = int(out["position_count"])
    out.pop("ingested_at", None)
    return out


_SELECT = """
    SELECT snapshot_id, account_id, source, equity, cash, market_value,
           day_pnl, gross_exposure_pct, position_count, kill_switch_active,
           captured_at
    FROM portfolio_snapshots
"""


def list_snapshots(limit: int = 200) -> list[dict]:
    """Return snapshots oldest-first, ready for a time-series chart."""
    limit = max(1, min(int(limit), 2000))
    client = get_ch_client()
    if client is not None:
        try:
            result = client.query(
                _SELECT + " ORDER BY captured_at DESC LIMIT {limit:UInt32}",
                parameters={"limit": limit},
            )
            rows = result.df().to_dict("records") if result.row_count else []
            return [_normalise(r) for r in reversed(rows)]
        except Exception as exc:
            logger.warning("Portfolio history ClickHouse read failed, using JSONL: %s", exc)

    path = Path(get_settings().portfolio_history_jsonl)
    if not path.exists():
        return []
    with _jsonl_lock:
        lines = path.read_text(encoding="utf-8").splitlines()
    rows: list[dict] = []
    for line in reversed(lines):
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
        if len(rows) >= limit:
            break
    return [_normalise(r) for r in reversed(rows)]


def first_snapshot() -> dict | None:
    """Earliest snapshot, used as the P&L baseline."""
    client = get_ch_client()
    if client is not None:
        try:
            result = client.query(_SELECT + " ORDER BY captured_at ASC LIMIT 1")
            if result.row_count:
                return _normalise(result.df().to_dict("records")[0])
        except Exception as exc:
            logger.warning("Portfolio baseline ClickHouse read failed, using JSONL: %s", exc)

    path = Path(get_settings().portfolio_history_jsonl)
    if not path.exists():
        return None
    with _jsonl_lock:
        lines = path.read_text(encoding="utf-8").splitlines()
    for line in lines:
        try:
            return _normalise(json.loads(line))
        except json.JSONDecodeError:
            continue
    return None
