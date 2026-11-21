"""Append-only, hash-chained agent journal.

Every agent event is written with ``seq``, ``prev_hash`` and ``hash`` so the
Auditor can prove the run was not rewritten after the fact.  Each row also
stamps ``strategy_version`` and the SHA-256 of the artifacts it carries.

ClickHouse is an optional mirror; the local JSONL is the audit source of
truth.  If the JSONL cannot be written the journal raises
``JournalUnavailable`` and the runtime halts (fail-closed).
"""
from __future__ import annotations

import hashlib
import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.config import get_settings

logger = logging.getLogger(__name__)

GENESIS: str = "0" * 64
_write_lock = threading.Lock()


class JournalUnavailable(RuntimeError):
    pass


def _canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def artifact_sha256(artifact: Any) -> str:
    """SHA-256 of a pydantic model or plain dict, stable across key order."""
    if hasattr(artifact, "model_dump"):
        payload = artifact.model_dump(mode="json")
    else:
        payload = artifact
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def _row_hash(row: dict) -> str:
    body = {k: v for k, v in row.items() if k != "hash"}
    return hashlib.sha256(_canonical(body).encode("utf-8")).hexdigest()


class Journal:
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path or get_settings().agent_journal_jsonl)

    # ── write ────────────────────────────────────────────────────────────────
    def append(
        self,
        *,
        run_id: str,
        strategy_version: str,
        event_type: str,
        payload: dict,
        artifact_hashes: dict[str, str] | None = None,
    ) -> dict:
        with _write_lock:
            seq, prev = self._tail()
            row = {
                "seq": seq + 1,
                "prev_hash": prev,
                "run_id": run_id,
                "strategy_version": strategy_version,
                "event_type": event_type,
                "artifact_hashes": dict(artifact_hashes or {}),
                "payload": payload,
                "recorded_at": datetime.now(timezone.utc).isoformat(),
            }
            row["hash"] = _row_hash(row)
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                with self.path.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
            except Exception as exc:
                raise JournalUnavailable(f"cannot append to {self.path}: {exc}") from exc
        self._mirror_clickhouse(row)
        return row

    def _mirror_clickhouse(self, row: dict) -> None:
        """Best-effort mirror; the JSONL above is already the source of truth."""
        try:
            from app.core.clickhouse_client import get_ch_client

            client = get_ch_client()
            if client is None:
                return
            import pandas as pd

            client.insert_df("agent_journal", pd.DataFrame([{
                "seq": row["seq"],
                "run_id": row["run_id"],
                "strategy_version": row["strategy_version"],
                "event_type": row["event_type"],
                "hash": row["hash"],
                "prev_hash": row["prev_hash"],
                "artifact_hashes": _canonical(row["artifact_hashes"]),
                "payload": _canonical(row["payload"]),
                "recorded_at": row["recorded_at"],
            }]))
        except Exception as exc:
            logger.debug("agent_journal ClickHouse mirror skipped: %s", exc)

    def _tail(self) -> tuple[int, str]:
        if not self.path.exists():
            return 0, GENESIS
        last: dict | None = None
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                last = json.loads(line)
        if last is None:
            return 0, GENESIS
        return int(last.get("seq", 0)), str(last.get("hash", GENESIS))

    # ── read ─────────────────────────────────────────────────────────────────
    def read(self, run_id: str | None = None, limit: int | None = None) -> list[dict]:
        rows = self._load()
        if run_id:
            rows = [r for r in rows if r.get("run_id") == run_id]
        if limit is not None:
            rows = rows[-max(1, int(limit)):]
        return rows

    def _load(self) -> list[dict]:
        if not self.path.exists():
            return []
        rows: list[dict] = []
        with _write_lock:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        for line in lines:
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                rows.append({"__corrupt__": line[:120]})
        return rows

    def verify(self, run_id: str | None = None) -> tuple[bool, list[str]]:
        breaks: list[str] = []
        prev = GENESIS
        expected_seq = 1
        for row in self._load():
            if "__corrupt__" in row:
                breaks.append(f"unparseable journal row at expected seq {expected_seq}")
                continue
            seq = row.get("seq")
            if seq != expected_seq:
                breaks.append(f"seq gap at {seq!r}: expected {expected_seq}")
            if row.get("prev_hash") != prev:
                breaks.append(f"prev_hash mismatch at seq {seq}")
            if _row_hash(row) != row.get("hash"):
                breaks.append(f"hash mismatch at seq {seq}")
            prev = row.get("hash", "")
            expected_seq = (seq if isinstance(seq, int) else expected_seq) + 1
        if run_id:
            in_run = [r for r in self._load() if r.get("run_id") == run_id and "__corrupt__" not in r]
            if not in_run:
                breaks.append(f"no journal rows for run {run_id}")
        return (not breaks, breaks)

    def runs(self, limit: int = 20) -> list[dict]:
        """Latest run record per run_id, newest first."""
        latest: dict[str, dict] = {}
        for row in self._load():
            if "__corrupt__" in row:
                continue
            latest[row.get("run_id", "")] = row
        runs = []
        for run_id, row in latest.items():
            runs.append({
                "run_id": run_id,
                "strategy_version": row.get("strategy_version"),
                "event_type": row.get("event_type"),
                "recorded_at": row.get("recorded_at"),
                "status": (row.get("payload") or {}).get("status", ""),
                "phase": (row.get("payload") or {}).get("phase", ""),
            })
        runs.sort(key=lambda r: r["recorded_at"] or "", reverse=True)
        return runs[: max(1, int(limit))]

    def find_run(self, session_date: str, strategy_version: str, phase: str) -> dict | None:
        """Idempotency lookup for (session_date, strategy_version, phase)."""
        for row in self._load():
            if row.get("event_type") != "run_started":
                continue
            payload = row.get("payload") or {}
            if (
                str(payload.get("session_date")) == session_date
                and payload.get("strategy_version") == strategy_version
                and payload.get("phase") == phase
            ):
                return row
        return None
