"""Append-only JSONL ledger: every signal, decision, fill, risk event and equity mark.

This is the 'log of trading decisions, fills and results' the challenge
submission requires, and the audit trail for the risk gate. Each Ledger
instance stamps its records with a `run_id` so reports can separate runs.
"""
from __future__ import annotations

import json
import math
import os
import uuid
from datetime import datetime, timezone
from typing import Any


def _clean(v: Any) -> Any:
    """Make values strict-JSON safe: non-finite floats become null."""
    if isinstance(v, float):
        return v if math.isfinite(v) else None
    if isinstance(v, dict):
        return {k: _clean(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_clean(x) for x in v]
    return v


class Ledger:
    def __init__(self, path: str = "logs/agent_ledger.jsonl", run_id: str | None = None,
                 broker: str | None = None):
        self.path = path
        self.broker = broker      # "sim" | "moomoo": keeps dry runs apart from paper-account runs
        self.run_id = run_id or f"{datetime.now(timezone.utc):%Y%m%dT%H%M%S}-{uuid.uuid4().hex[:6]}"
        d = os.path.dirname(path)
        if d:
            os.makedirs(d, exist_ok=True)

    def write(self, event: str, **data: Any) -> dict:
        rec = {"ts": datetime.now(timezone.utc).isoformat(), "run_id": self.run_id,
               "broker": self.broker, "event": event, **_clean(data)}
        line = json.dumps(rec, default=str, allow_nan=False) + "\n"
        # an interrupted earlier append can leave a line without its newline: start a new line so
        # this record is not merged into (and lost with) the damaged one
        if os.path.exists(self.path) and os.path.getsize(self.path):
            with open(self.path, "rb") as f:
                f.seek(-1, os.SEEK_END)
                if f.read(1) != b"\n":
                    line = "\n" + line
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(line)
        return rec

    def _lines(self):
        """Yield (record_or_None, raw_line). None marks a line that is not valid JSON."""
        if not os.path.exists(self.path):
            return
        with open(self.path, encoding="utf-8") as f:
            for raw in f:
                if not raw.strip():
                    continue
                try:
                    rec = json.loads(raw)
                except ValueError:
                    yield None, raw
                    continue
                yield (rec, raw) if isinstance(rec, dict) else (None, raw)   # [] or 5 is damage too

    def read(self) -> list[dict]:
        """All valid records; damaged lines are skipped (see `unresolved_state_failure`)."""
        return [r for r, _ in self._lines() if r is not None]

    def unresolved_state_failure(self, broker: str | None) -> bool:
        """True if the latest state event for this broker is a failed save that no human has
        acknowledged. A failed save can leave closed-trade losses missing from the saved risk
        state, so a restart must not trade on it unattended.

        A damaged ledger line could have been that event, so it counts as an unresolved failure
        until a later acknowledgement; exits still run, only new entries are held back."""
        latest = None
        for rec, _raw in self._lines():
            if rec is None:
                latest = "state_persist_failed"
            elif rec.get("broker") == broker and rec.get("action") in (
                    "state_persist_failed", "state_failure_acknowledged"):
                latest = rec["action"]
        return latest == "state_persist_failed"
