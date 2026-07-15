"""
ClickHouse read/write helpers for OHLCV, news sentiment, and backtest results.

All functions are synchronous (intended for asyncio.to_thread) and fail
silently when ClickHouse is unavailable, so callers always get a degraded
result rather than an exception.
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Optional

import pandas as pd

from app.core.clickhouse_client import get_ch_client

logger = logging.getLogger(__name__)

# Indicator column names as produced by fetcher.py add_indicators()
_INDICATOR_COLS = [
    "rsi", "macd", "macd_signal", "macd_hist",
    "sma_20", "sma_50",
    "bb_upper", "bb_mid", "bb_lower", "bb_width", "bb_pct_b",
    "ema_9", "ema_12", "ema_26",
    "atr_14", "roc_5", "roc_20",
    "volume_zscore", "daily_return", "return_5d",
    "price_vs_sma20", "golden_cross",
]

_CH_SELECT_COLS = [
    "date", "open", "high", "low", "close", "volume", "adj_close",
] + _INDICATOR_COLS


def _market(ticker: str) -> str:
    if ticker.endswith(".KL"):
        return "MY"
    if ticker.endswith(".HK"):
        return "HK"
    return "US"


def _to_date(d) -> date:
    if isinstance(d, datetime):
        return d.date()
    if isinstance(d, date):
        return d
    try:
        return date.fromisoformat(str(d))
    except Exception:
        return date.today()


# ── OHLCV ──────────────────────────────────────────────────────────────────────

def ch_read_ohlcv(ticker: str, period_years: int) -> Optional[pd.DataFrame]:
    """
    Returns a DataFrame indexed by datetime with OHLCV + indicators,
    or None if ClickHouse is unavailable or has no data for this ticker.
    """
    client = get_ch_client()
    if client is None:
        return None
    try:
        cutoff = date.today().replace(year=date.today().year - period_years)
        result = client.query(
            f"""
            SELECT {', '.join(_CH_SELECT_COLS)}
            FROM ohlcv FINAL
            WHERE ticker = {{ticker:String}}
              AND date >= {{cutoff:Date}}
            ORDER BY date
            """,
            parameters={"ticker": ticker, "cutoff": cutoff},
        )
        if result.row_count == 0:
            return None
        df = result.df()
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date")
        # Restore title-case OHLCV columns expected by downstream code
        df = df.rename(columns={
            "open": "Open", "high": "High", "low": "Low",
            "close": "Close", "volume": "Volume",
        })
        return df
    except Exception as exc:
        logger.warning("CH read ohlcv %s: %s", ticker, exc)
        return None


def ch_write_ohlcv(ticker: str, df: pd.DataFrame) -> None:
    """
    Persist a DataFrame (as returned by fetch_stock_data) to ClickHouse.
    Silently ignores errors — Redis / yfinance remain the source of truth.
    """
    client = get_ch_client()
    if client is None or df.empty:
        return
    try:
        rows = df.reset_index().copy()
        # Normalise index/date column
        rows.columns = [str(c) for c in rows.columns]
        date_col = next(
            (c for c in rows.columns if c.lower() in ("date", "datetime", "index")),
            rows.columns[0],
        )
        rows = rows.rename(columns={date_col: "date"})
        rows["date"] = pd.to_datetime(rows["date"]).dt.date

        # Lowercase all columns
        rows.columns = [c.lower() for c in rows.columns]

        rows["ticker"] = ticker
        rows["market"] = _market(ticker)
        rows["ingested_at"] = datetime.utcnow()

        # adj_close fallback
        if "adj_close" not in rows.columns:
            rows["adj_close"] = rows.get("close", 0.0)

        # Ensure every CH column is present (fill missing with None)
        ch_cols = [
            "ticker", "market", "date",
            "open", "high", "low", "close", "volume", "adj_close",
        ] + _INDICATOR_COLS + ["ingested_at"]
        for col in ch_cols:
            if col not in rows.columns:
                rows[col] = None

        client.insert_df("ohlcv", rows[ch_cols])
        logger.debug("CH write ohlcv %s: %d rows", ticker, len(rows))
    except Exception as exc:
        logger.warning("CH write ohlcv %s: %s", ticker, exc)


def ch_is_fresh(ticker: str, period_years: int, max_staleness_days: int = 2) -> bool:
    """True if ClickHouse has data for this ticker and it is up-to-date."""
    client = get_ch_client()
    if client is None:
        return False
    try:
        result = client.query(
            "SELECT max(date) AS latest FROM ohlcv FINAL WHERE ticker = {ticker:String}",
            parameters={"ticker": ticker},
        )
        if result.row_count == 0:
            return False
        latest = result.first_row[0]
        if latest is None:
            return False
        latest_date = _to_date(latest)
        return (date.today() - latest_date).days <= max_staleness_days
    except Exception as exc:
        logger.warning("CH freshness check %s: %s", ticker, exc)
        return False


# ── News sentiment ──────────────────────────────────────────────────────────────

def ch_write_sentiment(ticker: str, records: list[dict]) -> None:
    """
    Write news sentiment records to ClickHouse.

    Each record must have:
        published_at: datetime
        headline:     str
        source:       str       (e.g. "newsapi", "reddit")
        sentiment:    str       (positive | neutral | negative)
        score:        float     (signed: positive_prob - negative_prob)
    """
    client = get_ch_client()
    if client is None or not records:
        return
    try:
        df = pd.DataFrame(records)
        df["ticker"] = ticker
        df["ingested_at"] = datetime.utcnow()
        client.insert_df("news_sentiment", df[[
            "ticker", "published_at", "headline", "source",
            "sentiment", "score", "ingested_at",
        ]])
        logger.debug("CH write sentiment %s: %d rows", ticker, len(df))
    except Exception as exc:
        logger.warning("CH write sentiment %s: %s", ticker, exc)


def ch_read_sentiment(ticker: str, days: int = 7) -> pd.DataFrame:
    """Recent headlines + sentiment scores for a ticker."""
    client = get_ch_client()
    if client is None:
        return pd.DataFrame()
    try:
        result = client.query(
            """
            SELECT ticker, published_at, headline, source, sentiment, score
            FROM news_sentiment
            WHERE ticker = {ticker:String}
              AND published_at >= now() - INTERVAL {days:Int32} DAY
            ORDER BY published_at DESC
            """,
            parameters={"ticker": ticker, "days": days},
        )
        return result.df() if result.row_count > 0 else pd.DataFrame()
    except Exception as exc:
        logger.warning("CH read sentiment %s: %s", ticker, exc)
        return pd.DataFrame()


# ── Backtest results ────────────────────────────────────────────────────────────

def ch_write_backtest(ticker: str, result: dict) -> None:
    """
    Persist backtest metrics from run_backtest() to ClickHouse for
    historical tracking and cross-ticker comparison.
    """
    client = get_ch_client()
    if client is None:
        return
    try:
        m = result.get("metrics", {})
        period = result.get("test_period", {})
        row = {
            "ticker":            ticker,
            "run_at":            datetime.utcnow(),
            "test_start":        _to_date(period.get("start")),
            "test_end":          _to_date(period.get("end")),
            "total_return":      float(m.get("total_return", 0)),
            "benchmark_return":  float(m.get("benchmark_return", 0)),
            "alpha":             float(m.get("alpha", 0)),
            "sharpe_ratio":      float(m.get("sharpe_ratio", 0)),
            "sortino_ratio":     float(m.get("sortino_ratio", 0)),
            "calmar_ratio":      float(m.get("calmar_ratio", 0)),
            "max_drawdown":      float(m.get("max_drawdown", 0)),
            "win_rate":          float(m.get("win_rate", 0)),
            "n_trades":          int(m.get("n_trades", 0)),
            "annualised_return": float(m.get("annualised_return", 0)),
        }
        client.insert_df("backtest_results", pd.DataFrame([row]))
        logger.info("CH write backtest %s (sharpe=%.2f)", ticker, row["sharpe_ratio"])
    except Exception as exc:
        logger.warning("CH write backtest %s: %s", ticker, exc)


def ch_read_backtest_history(ticker: str, limit: int = 20) -> pd.DataFrame:
    """Historical backtest runs for a ticker, newest first."""
    client = get_ch_client()
    if client is None:
        return pd.DataFrame()
    try:
        result = client.query(
            """
            SELECT run_at, total_return, benchmark_return, alpha,
                   sharpe_ratio, sortino_ratio, calmar_ratio, max_drawdown,
                   win_rate, n_trades, annualised_return
            FROM backtest_results
            WHERE ticker = {ticker:String}
            ORDER BY run_at DESC
            LIMIT {limit:UInt32}
            """,
            parameters={"ticker": ticker, "limit": limit},
        )
        return result.df() if result.row_count > 0 else pd.DataFrame()
    except Exception as exc:
        logger.warning("CH read backtest %s: %s", ticker, exc)
        return pd.DataFrame()
