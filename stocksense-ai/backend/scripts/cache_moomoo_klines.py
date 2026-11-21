#!/usr/bin/env python3
"""Cache moomoo daily K-lines locally for the prediction pipeline.

Read-only: talks to the quote gateway only and never imports a trade context,
so no order, cancel, transfer or subscription endpoint can be reached.

Two sources are supported:

1. OpenD gateway (scriptable, same data as the MCP tool):
   python scripts/cache_moomoo_klines.py --tickers NVDA,AAPL --bars 370

2. Raw ``mcp__moomoo__quote_cur_kline`` output saved by an agent session:
   python scripts/cache_moomoo_klines.py --from-json snapshot.json --ticker NVDA

Cache files land in backend/data/cache/moomoo (override with
MOOMOO_KLINE_CACHE_DIR) and are read by app.data.fetcher.fetch_stock_data.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.data.local_kline_cache import (  # noqa: E402
    cache_path,
    rows_from_mcp_payload,
    rows_from_opend_frame,
    write_bars,
)

MARKETS = ("US", "MY", "SG", "HK", "CN", "JP", "AU", "CA")


def split_symbol(raw: str) -> tuple[str, str]:
    raw = raw.strip().upper()
    head, _, tail = raw.partition(".")
    if tail and head in MARKETS:
        return head, raw
    return "US", f"US.{raw}"


def pull_from_opend(codes: list[str], bars: int) -> list[Path]:
    from moomoo import AuType, KLType, OpenQuoteContext, RET_OK, SubType

    written: list[Path] = []
    ctx = OpenQuoteContext(
        host=os.getenv("MOOMOO_HOST", "127.0.0.1"),
        port=int(os.getenv("MOOMOO_PORT", "11111")),
    )
    try:
        ret, err = ctx.subscribe(codes, [SubType.K_DAY], subscribe_push=False)
        if ret != RET_OK:
            raise RuntimeError(f"K-line subscribe failed: {err}")

        for code in codes:
            ret, data = ctx.get_cur_kline(code, bars, ktype=KLType.K_DAY, autype=AuType.QFQ)
            market, ticker = split_symbol(code)
            if ret != RET_OK:
                print(f"[FAIL] {code}: {data}")
                continue
            path = write_bars(ticker, market, code, "opend:get_cur_kline",
                              rows_from_opend_frame(data))
            written.append(path)
            print(f"[OK]   {code}: {len(data)} bars -> {path}")
    finally:
        ctx.close()
    return written


def import_mcp_json(snapshot: str, ticker_arg: str) -> Path:
    if snapshot == "-":
        payload = json.load(sys.stdin)
    else:
        payload = json.loads(Path(snapshot).read_text(encoding="utf-8"))

    market, ticker = split_symbol(ticker_arg)
    path = write_bars(ticker, market, ticker, "mcp:quote_cur_kline",
                      rows_from_mcp_payload(payload))
    print(f"[OK]   {ticker}: imported from MCP snapshot -> {path}")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tickers", help="Comma-separated symbols, e.g. NVDA,AAPL,US.NVDA")
    parser.add_argument("--bars", type=int, default=370, help="Daily bars to fetch (1-370)")
    parser.add_argument("--from-json", help="Raw quote_cur_kline JSON file, or '-' for stdin")
    parser.add_argument("--ticker", help="Ticker for --from-json, e.g. NVDA or US.NVDA")
    args = parser.parse_args()

    if args.from_json:
        if not args.ticker:
            parser.error("--from-json requires --ticker")
        import_mcp_json(args.from_json, args.ticker)
        return 0

    if not args.tickers:
        parser.error("provide --tickers or --from-json")

    if not 1 <= args.bars <= 370:
        parser.error("--bars must be between 1 and 370")

    codes = [split_symbol(t)[1] for t in args.tickers.split(",") if t.strip()]
    written = pull_from_opend(codes, args.bars)
    print(f"\n{len(written)}/{len(codes)} tickers cached under {cache_path('X').parent}")
    return 0 if written else 1


if __name__ == "__main__":
    raise SystemExit(main())
