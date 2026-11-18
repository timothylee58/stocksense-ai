"""Summarise the agent ledger as markdown (decisions, fills, PnL, drawdown).

    python -m app.agent.report --ledger logs/agent_ledger.jsonl > report.md
"""
from __future__ import annotations

import argparse
from collections import Counter

from app.agent.ledger import Ledger


def summarise(events: list[dict]) -> dict:
    eq = [e["equity"] for e in events if e["event"] == "equity"]
    peak, max_dd = 0.0, 0.0
    for v in eq:
        peak = max(peak, v)
        if peak > 0:
            max_dd = max(max_dd, (peak - v) / peak)
    fills = [e for e in events if e["event"] == "fill"]
    sells = [f for f in fills if f.get("realized_pnl") is not None]
    wins = [f for f in sells if f["realized_pnl"] > 0]
    decisions = [e for e in events if e["event"] == "decision"]
    rejects = Counter(d["reason"] for d in decisions if not d.get("approved"))
    return {
        "start_equity": eq[0] if eq else None,
        "end_equity": eq[-1] if eq else None,
        "return_pct": (eq[-1] / eq[0] - 1) * 100 if len(eq) > 1 and eq[0] else None,
        "max_drawdown_pct": max_dd * 100,
        "n_fills": len(fills),
        "n_closed_trades": len(sells),
        "realized_pnl": sum(f["realized_pnl"] for f in sells),
        "win_rate_pct": len(wins) / len(sells) * 100 if sells else None,
        "n_decisions": len(decisions),
        "n_approved": sum(1 for d in decisions if d.get("approved")),
        "top_rejections": rejects.most_common(5),
        "risk_events": [e for e in events if e["event"] == "risk_event"],
    }


def _fmt(v: float | None, spec: str = ".2f", suffix: str = "") -> str:
    return "n/a" if v is None else f"{v:{spec}}{suffix}"


def to_markdown(s: dict) -> str:
    lines = [
        "# Trading agent report", "",
        "| Metric | Value |", "|---|---|",
        f"| Start equity | {_fmt(s['start_equity'], ',.2f')} |",
        f"| End equity | {_fmt(s['end_equity'], ',.2f')} |",
        f"| Return | {_fmt(s['return_pct'], '.2f', '%')} |",
        f"| Max drawdown | {_fmt(s['max_drawdown_pct'], '.2f', '%')} |",
        f"| Closed trades | {s['n_closed_trades']} |",
        f"| Realized PnL | {_fmt(s['realized_pnl'], ',.2f')} |",
        f"| Win rate | {_fmt(s['win_rate_pct'], '.0f', '%')} |",
        f"| Decisions (approved/total) | {s['n_approved']}/{s['n_decisions']} |",
        "", "## Why trades were rejected", "",
    ]
    lines += [f"- {n}x {r}" for r, n in s["top_rejections"]] or ["- none"]
    lines += ["", "## Risk events", ""]
    lines += [f"- {e['ts']}: {e.get('action')} {e.get('reason', '')}".rstrip()
              for e in s["risk_events"]] or ["- none"]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--ledger", default="logs/agent_ledger.jsonl")
    print(to_markdown(summarise(Ledger(ap.parse_args().ledger).read())), end="")
