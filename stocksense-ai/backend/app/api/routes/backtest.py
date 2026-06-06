"""Walk-forward backtest endpoint.

GET /api/backtest/{ticker}
    Runs the long-only walk-forward backtest on the held-out 20 % test set.
    Returns Sharpe, Sortino, Calmar, alpha, max-drawdown, win-rate, and a
    full equity curve (strategy vs buy-and-hold) for the frontend chart.
    Results are cached 1 hour — backtest is CPU-bound and deterministic.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from app.core.config import get_settings
from app.core.redis_client import cache_get, cache_set

logger = logging.getLogger(__name__)
router = APIRouter()
settings = get_settings()

# 17 demo equity curves (one per tracked MY stock) — deterministic, no model needed
_DEMO_EQUITY_STUB = [{"date": f"2024-{m:02d}-01", "strategy": round(1 + i * 0.005 * (0.8 + 0.4 * (i % 3)), 4), "benchmark": round(1 + i * 0.003, 4)} for i, m in enumerate(range(1, 13))]


def _demo_backtest(ticker: str) -> dict:
    """Return plausible synthetic backtest metrics for demo mode."""
    import random
    rng = random.Random(hash(ticker))
    ret   = round(rng.uniform(0.04, 0.18), 4)
    alpha = round(rng.uniform(0.01, 0.08), 4)
    return {
        "ticker": ticker,
        "test_period": {"start": "2024-01-01", "end": "2024-12-31", "n_days": 252},
        "metrics": {
            "total_return":     ret,
            "benchmark_return": round(ret - alpha, 4),
            "alpha":            alpha,
            "sharpe_ratio":     round(rng.uniform(0.8, 2.2), 3),
            "sortino_ratio":    round(rng.uniform(1.0, 3.0), 3),
            "calmar_ratio":     round(rng.uniform(0.5, 1.8), 3),
            "max_drawdown":     round(rng.uniform(-0.15, -0.04), 4),
            "win_rate":         round(rng.uniform(0.50, 0.60), 3),
            "n_trades":         rng.randint(40, 120),
            "annualised_return":round(ret * 1.1, 4),
        },
        "equity_curve":   _DEMO_EQUITY_STUB,
        "position_logic": "demo mode — synthetic metrics",
        "demo":           True,
    }


@router.get("/backtest/{ticker}")
async def backtest_ticker(ticker: str):
    """Walk-forward backtest: Sharpe, alpha, drawdown, equity curve."""
    tk = ticker.upper()
    cache_key = f"backtest:{tk}:demo" if settings.demo_mode else f"backtest:{tk}"

    cached = await cache_get(cache_key)
    if cached:
        return cached

    if settings.demo_mode:
        result = _demo_backtest(tk)
        await cache_set(cache_key, result, ttl=3600)
        return result

    try:
        import asyncio
        from app.data.fetcher import fetch_stock_data
        from app.services.backtest_service import run_backtest

        df = await fetch_stock_data(tk, period="2y")
        if df is None or df.empty:
            raise HTTPException(status_code=404, detail=f"No data for {tk}")

        result = await asyncio.to_thread(run_backtest, df, tk)
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.error("Backtest failed for %s: %s", tk, e)
        raise HTTPException(status_code=500, detail=f"Backtest error: {e}")

    await cache_set(cache_key, result, ttl=3600)
    return result
