"""Append-only JSONL ledger: every decision, fill, risk event and equity mark.

This is the 'log of trading decisions, fills and results' the challenge
submission requires, and the audit trail for the risk gate.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any


class Ledger:
    def __init__(self, path: str = "logs/agent_ledger.jsonl"):
        self.path = path
        d = os.path.dirname(path)
        if d:
            os.makedirs(d, exist_ok=True)

    def write(self, event: str, **data: Any) -> dict:
        rec = {"ts": datetime.now(timezone.utc).isoformat(), "event": event, **data}
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, default=str) + "\n")
        return rec

    def read(self) -> list[dict]:
        if not os.path.exists(self.path):
            return []
        with open(self.path, encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]
