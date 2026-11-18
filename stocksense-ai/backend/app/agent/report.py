"""Summarise the agent ledger as markdown (decisions, fills, PnL, drawdown).

    python -m app.agent.report --ledger logs/agent_ledger.jsonl [--run-id ID] [--date YYYY-MM-DD]
"""
from __future__ import annotations

import argparse
from collections import Counter

from app.agent.ledger import Ledger


def select(events: list[dict], run_id: str | None = None, date: str | None = None,
           broker: str | None = None) -> list[dict]:
    """Pick the events to summarise.

    - run_id given: that run only.
    - date given: every run on that UTC day (YYYY-MM-DD), for one broker.
    - neither: the latest run.
    `broker` ("sim" | "moomoo") defaults to the broker of the latest matching event, so
    dry-run and paper-account equity are never mixed.
    """
    if run_id:
        return [e for e in events if e.get("run_id") == run_id]
    if date:
        events = [e for e in events if str(e.get("ts", "")).startswith(date)]
        if broker is None and events:
            broker = events[-1].get("broker")
        return [e for e in events if e.get("broker") == broker] if broker else events
    latest = next((e["run_id"] for e in reversed(events) if e.get("run_id")), None)
    return [e for e in events if e.get("run_id") == latest] if latest else events


def _curve_stats(events: list[dict]) -> tuple[float | None, float | None, float | None, float]:
    """(start, end, return_pct, max_drawdown_pct) of one continuous equity curve."""
    eq = [e["equity"] for e in events if e["event"] == "equity" and e.get("equity") is not None]
    peak, max_dd = 0.0, 0.0
    for v in eq:
        peak = max(peak, v)
        if peak > 0:
            max_dd = max(max_dd, (peak - v) / peak)
    ret = (eq[-1] / eq[0] - 1) * 100 if len(eq) > 1 and eq[0] else None
    return (eq[0] if eq else None), (eq[-1] if eq else None), ret, max_dd * 100


def _equity_summary(events: list[dict]) -> dict:
    """One paper account is a single curve. Simulator runs each restart at $100k, so they are
    measured per run (return compounded, drawdown = worst run) instead of being chained."""
    runs: dict[str, list[dict]] = {}
    for e in events:
        runs.setdefault(e.get("run_id") or "", []).append(e)
    is_sim = any(e.get("broker") == "sim" for e in events)
    if len(runs) <= 1 or not is_sim:
        start, end, ret, dd = _curve_stats(events)
        return {"start_equity": start, "end_equity": end, "return_pct": ret,
                "max_drawdown_pct": dd, "equity_note": None}
    stats = [st for st in (_curve_stats(r) for r in runs.values()) if st[0] is not None]
    if not stats:                       # runs exist but none logged an equity mark
        return {"start_equity": None, "end_equity": None, "return_pct": None,
                "max_drawdown_pct": 0.0, "equity_note": None}
    growth = 1.0
    for _, _, r, _ in stats:
        growth *= 1 + (r or 0.0) / 100
    start = stats[0][0]
    return {"start_equity": start,
            "end_equity": start * growth if start else None,     # consistent with the return
            "return_pct": (growth - 1) * 100,
            "max_drawdown_pct": max(d for *_, d in stats),
            "equity_note": (f"{len(stats)} simulator runs measured separately (each restarts at start equity); "
                            f"end equity is the start compounded by each run's return, the last run ended at "
                            f"{stats[-1][1]:,.2f}")}


def summarise(events: list[dict]) -> dict:
    eqs = _equity_summary(events)
    fills = [e for e in events if e["event"] == "fill"]
    # a closed trade is a round trip that reached zero; its PnL is summed over partial fills
    closed = [f for f in fills if f.get("closed") and f.get("trade_pnl") is not None]
    sells = closed
    wins = [f for f in closed if f["trade_pnl"] > 0]
    decisions = [e for e in events if e["event"] == "decision"]
    rejects = Counter(d["reason"] for d in decisions if not d.get("approved"))
    return {
        **eqs,
        "n_fills": len(fills),
        "n_closed_trades": len(sells),
        "realized_pnl": sum(f["trade_pnl"] for f in closed),
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
        *(["", f"_{s['equity_note']}_"] if s.get("equity_note") else []),
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
    ap.add_argument("--run-id", help="default: the latest run in the ledger")
    ap.add_argument("--date", help="all runs on one UTC day, YYYY-MM-DD")
    ap.add_argument("--broker", choices=["sim", "moomoo"], help="with --date: which broker's runs")
    a = ap.parse_args()
    print(to_markdown(summarise(select(Ledger(a.ledger).read(), a.run_id, a.date, a.broker))), end="")
