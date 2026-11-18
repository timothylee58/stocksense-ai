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
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, default=str, allow_nan=False) + "\n")
        return rec

    def read(self) -> list[dict]:
        if not os.path.exists(self.path):
            return []
        with open(self.path, encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]

    def unresolved_state_failure(self, broker: str | None) -> bool:
        """True if the latest state event for this broker is a failed save that no human has
        acknowledged. A failed save can leave closed-trade losses missing from the saved risk
        state, so a restart must not trade on it unattended."""
        latest = None
        for e in self.read():
            if e.get("broker") == broker and e.get("action") in (
                    "state_persist_failed", "state_failure_acknowledged"):
                latest = e["action"]
        return latest == "state_persist_failed"
