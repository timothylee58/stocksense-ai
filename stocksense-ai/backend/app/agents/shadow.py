"""Run N sessions from the command line.

Shadow (default) logs decisions and calls no order tool:

    python -m app.agents.shadow --sessions 5

Paper mode exercises the risk gate + Executor against the SIMULATE/demo broker:

    python -m app.agents.shadow --sessions 1 --phase paper --symbols AAPL,NVDA
"""
from __future__ import annotations

import argparse
import asyncio
import json
from datetime import timedelta

from app.agents.runtime import AgentRuntime, latest_session_date


def _session_dates(count: int) -> list:
    dates = []
    d = latest_session_date()
    while len(dates) < count:
        dates.append(d)
        d -= timedelta(days=1)
        while d.weekday() >= 5:
            d -= timedelta(days=1)
    return dates


async def _run(args) -> int:
    runtime = AgentRuntime(phase=args.phase, symbols=args.symbols)
    exit_code = 0
    for session_date in _session_dates(args.sessions):
        summary = await runtime.run_session(session_date=session_date, phase=args.phase)
        print(json.dumps({"session_date": str(session_date), **summary}, default=str), flush=True)
        if summary["run"]["status"] != "completed":
            exit_code = 1
    return exit_code


def _close_clients() -> None:
    # moomoo SDK contexts own non-daemon threads; close them or the CLI never exits.
    try:
        from app.data.moomoo_fetcher import MoomooClient

        if MoomooClient._instance is not None:
            MoomooClient._instance.close()
            MoomooClient._instance = None
            MoomooClient._connected = False
    except Exception:
        pass
    try:
        from app.data import moomoo_trade_client

        if moomoo_trade_client._ctx is not None:
            moomoo_trade_client._ctx.close()
            moomoo_trade_client.reset_client()
    except Exception:
        pass


def main() -> None:
    parser = argparse.ArgumentParser(description="StockSense paper-agent session runner")
    parser.add_argument("--sessions", type=int, default=1)
    parser.add_argument("--phase", choices=("shadow", "paper"), default="shadow")
    parser.add_argument("--symbols", default="", help="comma-separated US tickers")
    args = parser.parse_args()
    args.symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()] or None
    try:
        code = asyncio.run(_run(args))
    finally:
        _close_clients()
    raise SystemExit(code)


if __name__ == "__main__":
    main()
