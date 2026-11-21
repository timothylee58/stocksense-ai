"""Local daily-OHLCV snapshots sourced from moomoo quote APIs.

Read-only by construction: this module stores quote data only and imports
nothing from the trading/order modules. Snapshots are plain JSON so they can
be produced either by the OpenD puller or by importing raw
``quote_cur_kline`` MCP output.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

import pandas as pd

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1
_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_DIR = _BACKEND_ROOT / "data" / "cache" / "moomoo"
_REQUIRED = ("open", "high", "low", "close", "volume")
_MARKET_PREFIXES = ("US", "MY", "SG", "HK", "CN", "JP", "AU", "CA")


def cache_dir() -> Path:
    return Path(os.getenv("MOOMOO_KLINE_CACHE_DIR", str(_DEFAULT_DIR)))


def bare_ticker(ticker: str) -> str:
    """Drop a moomoo market prefix so US.NVDA and NVDA share one cache file."""
    head, _, tail = ticker.upper().partition(".")
    return tail if tail and head in _MARKET_PREFIXES else ticker.upper()


def cache_path(ticker: str) -> Path:
    return cache_dir() / f"{bare_ticker(ticker)}.json"


def write_bars(
    ticker: str,
    market: str,
    code: str,
    source: str,
    rows: list[dict[str, Any]],
    ktype: str = "day",
) -> Path:
    """Persist one ticker's bars atomically."""
    if not rows:
        raise ValueError(f"no bars to write for {ticker}")

    payload = {
        "schema": SCHEMA_VERSION,
        "ticker": bare_ticker(ticker),
        "market": market.upper(),
        "code": code,
        "source": source,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "ktype": ktype,
        "bars": sorted(rows, key=lambda r: r["date"]),
    }

    path = cache_path(ticker)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tmp.replace(path)
    return path


def read_snapshot(ticker: str, max_age_hours: Optional[float] = None) -> Optional[dict]:
    path = cache_path(ticker)
    if not path.exists():
        return None

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Unreadable K-line cache %s: %s", path, exc)
        return None

    if payload.get("schema") != SCHEMA_VERSION or not payload.get("bars"):
        logger.warning("Ignoring K-line cache %s: unexpected schema", path)
        return None

    if max_age_hours is not None:
        try:
            fetched_at = datetime.fromisoformat(payload["fetched_at"])
        except (KeyError, ValueError):
            return None
        if datetime.now(timezone.utc) - fetched_at > timedelta(hours=max_age_hours):
            logger.info("K-line cache for %s is stale (fetched %s)", ticker, payload.get("fetched_at"))
            return None

    return payload


def read_cached_klines(ticker: str, max_age_hours: Optional[float] = None) -> Optional[pd.DataFrame]:
    """Return an OHLCV frame indexed by date, or None when unusable."""
    if max_age_hours is None:
        max_age_hours = float(os.getenv("MOOMOO_KLINE_CACHE_MAX_AGE_H", "72"))

    payload = read_snapshot(ticker, max_age_hours)
    if payload is None:
        return None

    rows = [r for r in payload["bars"] if all(k in r for k in _REQUIRED)]
    if len(rows) < 2:
        return None

    df = pd.DataFrame(rows).set_index("date")
    df.index = pd.to_datetime(df.index)
    df.index.name = "Date"
    df = df.rename(columns={"open": "Open", "high": "High", "low": "Low",
                            "close": "Close", "volume": "Volume"})
    df = df[["Open", "High", "Low", "Close", "Volume"]].apply(pd.to_numeric, errors="coerce")
    df = df.dropna(subset=["Close"])
    df.attrs["source"] = f"local_cache:{payload.get('source', 'unknown')}"
    return df


def rows_from_opend_frame(frame: pd.DataFrame) -> list[dict[str, Any]]:
    """Normalise an OpenD ``get_cur_kline`` DataFrame."""
    rows = []
    for _, r in frame.iterrows():
        date = pd.Timestamp(r["time_key"]).date().isoformat()
        rows.append({
            "date": date,
            "open": float(r["open"]),
            "high": float(r["high"]),
            "low": float(r["low"]),
            "close": float(r["close"]),
            "volume": float(r["volume"]),
            "turnover": float(r.get("turnover", 0) or 0),
            "last_close": float(r.get("last_close", 0) or 0),
            "change_rate": float(r.get("change_rate", 0) or 0),
        })
    return rows


def rows_from_mcp_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalise the raw ``quote_cur_kline`` / ``quote_history_kline`` response."""
    if payload.get("ret_code") != 0:
        raise ValueError(f"moomoo ret_code={payload.get('ret_code')} msg={payload.get('ret_msg')}")

    klines = (payload.get("data") or {}).get("kline_list") or []
    rows = []
    for k in klines:
        d = int(k["date"])
        rows.append({
            "date": f"{d // 10000:04d}-{d // 100 % 100:02d}-{d % 100:02d}",
            "open": float(k["open_price"]),
            "high": float(k["high_price"]),
            "low": float(k["low_price"]),
            "close": float(k["close_price"]),
            "volume": float(k["volume"]),
            "turnover": float(k.get("turnover", 0) or 0),
            "last_close": float(k.get("last_close_price", 0) or 0),
            "change_rate": float(k.get("change_rate", 0) or 0),
        })
    return rows
