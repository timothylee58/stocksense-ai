"""Tool bindings for the agent run loop.

Every binding call is checked against the machine-checkable allowlist first
(``app.agents.policy.check_tool``); a denied tool raises ``PolicyViolation``
and is never executed.  This is the only place the runtime touches moomoo or
the paper broker.

``LocalBindings`` implements the contract with the existing data layer and the
paper broker.  Tests inject a deterministic fake with the same shape.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from app.agents.artifacts import Bar
from app.agents.policy import check_tool
from app.core.config import get_settings
from app.schemas.risk import OrderExecution, OrderIntent, PortfolioSnapshot
from app.services import paper_broker

logger = logging.getLogger(__name__)


class PolicyViolation(RuntimeError):
    def __init__(self, agent_id: str, tool: str, code: str):
        super().__init__(f"{agent_id} may not call {tool} ({code})")
        self.agent_id = agent_id
        self.tool = tool
        self.code = code


def require_tool(agent_id: str, tool: str) -> None:
    verdict = check_tool(agent_id, tool)
    if not verdict.allowed:
        raise PolicyViolation(agent_id, tool, verdict.code)


def _parse_ts(raw: Any) -> datetime:
    # Broker timestamps without an offset are local wall-clock time (the
    # fetcher fabricates ``datetime.now()`` when moomoo omits update_time);
    # reading them as UTC makes every quote look 8 h in the future.
    if isinstance(raw, datetime):
        return raw.astimezone(timezone.utc)
    text = str(raw or "").strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).astimezone(timezone.utc)
        except ValueError:
            continue
    try:
        import pandas as pd

        return pd.Timestamp(text).to_pydatetime().astimezone(timezone.utc)
    except Exception:
        return datetime.now(timezone.utc)


class AgentBindings:
    """Interface implemented by LocalBindings and test fakes."""

    async def health(self, agent_id: str) -> dict:
        raise NotImplementedError

    async def dataset(self, agent_id: str, symbol: str) -> dict:
        raise NotImplementedError

    async def news(self, agent_id: str, symbol: str) -> tuple[float, list[str]]:
        raise NotImplementedError

    async def ml(self, agent_id: str, symbol: str, bars: list[Bar]) -> dict:
        raise NotImplementedError

    async def portfolio(self, agent_id: str) -> PortfolioSnapshot:
        raise NotImplementedError

    async def open_orders(self, agent_id: str) -> list[dict]:
        raise NotImplementedError

    async def place_order(self, agent_id: str, intent: OrderIntent, decision_id: str) -> OrderExecution:
        raise NotImplementedError


class LocalBindings(AgentBindings):
    async def health(self, agent_id: str) -> dict:
        require_tool(agent_id, "quote_market_state")
        if get_settings().demo_mode:
            return {"ok": True, "source": "demo", "reason": "", "trading_day": True}
        from app.data.moomoo_fetcher import fetch_realtime_quote

        quote = await fetch_realtime_quote("AAPL", "US")
        price = float(quote.get("last_price") or 0.0)
        return {
            "ok": price > 0,
            "source": str(quote.get("source", "moomoo")),
            "reason": "" if price > 0 else "quote_market_state unavailable",
            "trading_day": True,
        }

    async def dataset(self, agent_id: str, symbol: str) -> dict:
        require_tool(agent_id, "quote_stock_quote")
        from app.services.risk_gate import is_us_ticker

        if not is_us_ticker(symbol):
            return {"valid": False, "deny_reason": "OUTSIDE_UNIVERSE"}

        from app.data.moomoo_fetcher import fetch_realtime_quote

        quote = await fetch_realtime_quote(symbol, "US")
        if float(quote.get("last_price") or 0) <= 0:
            return {"valid": False, "deny_reason": "MISSING_QUOTE"}
        source = "yfinance" if "yfinance" in str(quote.get("source", "")) else "moomoo"

        from app.data.fetcher import fetch_stock_data

        df = await fetch_stock_data(symbol)

        bars = [
            Bar(
                ts=idx.to_pydatetime() if hasattr(idx, "to_pydatetime") else idx,
                open=max(float(row["Open"]), 0.01),
                high=max(float(row["High"]), 0.01),
                low=max(float(row["Low"]), 0.01),
                close=max(float(row["Close"]), 0.01),
                volume=max(float(row.get("Volume", 0) or 0), 0.0),
            )
            for idx, row in df.tail(180).iterrows()
        ]
        ts = _parse_ts(quote.get("update_time"))
        return {
            "valid": True,
            "quote": {
                "price": float(quote["last_price"]),
                "prev_close": float(quote.get("prev_close_price") or 0) or None,
                "ts": ts,
                "source": source,
                "delayed": source != "moomoo",
            },
            "bars": bars,
        }

    async def news(self, agent_id: str, symbol: str) -> tuple[float, list[str]]:
        require_tool(agent_id, "news_search")
        from app.services.finbert_service import get_finbert_score

        score, headlines = await asyncio.to_thread(get_finbert_score, symbol)
        return float(score), [h["title"] for h in headlines if h.get("title")]

    async def ml(self, agent_id: str, symbol: str, bars: list[Bar]) -> dict:
        require_tool(agent_id, "quote_history_kline")
        if not bars:
            return {"xgboost": ("HOLD", 0.0), "lstm": ("NEUTRAL", 0.0), "atr": None}

        def _run() -> dict:
            from app.agents.signals import bars_to_frame
            from app.data.fetcher import add_indicators
            from app.ml.models.lstm import predict_lstm
            from app.ml.models.xgb_model import predict_xgb

            df = add_indicators(bars_to_frame(bars))
            signal, confidence = predict_xgb(df, symbol)
            prices, lstm_conf = predict_lstm(df, symbol, n_days=10)
            last = float(df["Close"].squeeze().iloc[-1])
            if len(prices) >= 7 and last > 0:
                ret = (float(prices[6]) - last) / last
                lstm_dir = "UP" if ret > 0.005 else "DOWN" if ret < -0.005 else "NEUTRAL"
            else:
                lstm_dir = "NEUTRAL"
            atr = df["atr_14"].iloc[-1] if "atr_14" in df.columns else None
            return {
                "xgboost": (signal, float(confidence)),
                "lstm": (lstm_dir, float(lstm_conf)),
                "atr": float(atr) if atr is not None and float(atr) > 0 else None,
            }

        return await asyncio.to_thread(_run)

    async def portfolio(self, agent_id: str) -> PortfolioSnapshot:
        require_tool(agent_id, "sim_trade_account_list")
        return await asyncio.to_thread(paper_broker.get_portfolio)

    async def open_orders(self, agent_id: str) -> list[dict]:
        require_tool(agent_id, "sim_trade_history_order_list")
        return await asyncio.to_thread(paper_broker.list_orders)

    async def place_order(self, agent_id: str, intent: OrderIntent, decision_id: str) -> OrderExecution:
        require_tool(agent_id, "sim_trade_input_order")
        status = await asyncio.to_thread(paper_broker.account_status)
        if str(status.get("trd_env", "")).upper() != "SIMULATE":
            raise PolicyViolation(agent_id, "sim_trade_input_order", "NON_SIMULATE_ACCOUNT")
        return await asyncio.to_thread(paper_broker.execute_order, intent)
