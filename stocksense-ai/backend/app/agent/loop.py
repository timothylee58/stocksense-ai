"""Execution loop: signals -> exits -> risk-gated entries -> fills -> ledger.

    python -m app.agent.loop --tickers NVDA,AAPL --cycles 1 --broker sim

Use --broker moomoo for the OpenD paper (SIMULATE) account; default is the
in-memory simulator.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
from collections.abc import Awaitable, Callable

from app.agent.broker import Broker, SimBroker
from app.agent.ledger import Ledger
from app.agent.models import TradeSignal, utcnow
from app.agent.risk import RiskManager

logger = logging.getLogger("agent")

SignalSource = Callable[[], Awaitable[list[TradeSignal]]]


class TradingAgent:
    def __init__(self, broker: Broker, risk: RiskManager, ledger: Ledger, source: SignalSource):
        self.broker, self.risk, self.ledger, self.source = broker, risk, ledger, source

    def _sell(self, ticker: str, price: float, reason: str) -> None:
        pos = self.broker.get_account().positions.get(ticker)
        if not pos:
            return
        fill = self.broker.place_order(ticker, "SELL", pos.qty, price)
        if fill:
            if fill.realized_pnl is not None:
                self.risk.record_closed_trade(fill.realized_pnl)
            self.ledger.write("fill", reason=reason, **fill.__dict__)

    async def run_cycle(self) -> None:
        now = utcnow()
        signals = await self.source()
        self.broker.update_prices({s.ticker: s.price for s in signals})
        acct = self.broker.get_account()
        self.risk.mark(acct.equity, now)
        self.ledger.write("equity", equity=acct.equity, cash=acct.cash,
                          drawdown=self.risk.drawdown, daily_loss=self.risk.daily_loss)

        if self.risk.should_flatten():
            reason = self.risk.halt_reason() or "halt"
            self.ledger.write("risk_event", action="flatten", reason=reason)
            for t in list(acct.positions):
                self._sell(t, acct.prices.get(t, acct.positions[t].avg_price), reason)
            return

        # 1) exits are never blocked by the gate
        for s in signals:
            why = self.risk.exit_reason(s, self.broker.get_account())
            if why:
                self.ledger.write("decision", ticker=s.ticker, action="SELL", approved=True, reason=why)
                self._sell(s.ticker, s.price, why)

        # 2) entries, most confident first
        for s in sorted((x for x in signals if x.action == "BUY"), key=lambda x: -x.confidence):
            acct = self.broker.get_account()
            d = self.risk.evaluate_entry(s, acct)
            self.ledger.write("decision", ticker=s.ticker, action="BUY", approved=d.approved,
                              qty=d.qty, reason=d.reason, confidence=s.confidence, price=s.price)
            if not d.approved:
                continue
            stop = s.stop_loss if s.stop_loss and s.stop_loss < s.price \
                else s.price * (1 - self.risk.limits.default_stop_pct)
            fill = self.broker.place_order(s.ticker, "BUY", d.qty, s.price, stop)
            if fill:
                self.ledger.write("fill", reason="entry", stop_loss=stop, **fill.__dict__)
            else:
                self.ledger.write("risk_event", action="order_rejected", ticker=s.ticker)


def predictor_source(tickers: list[str]) -> SignalSource:
    """Adapt the existing ensemble (`run_prediction`) to TradeSignals."""
    async def _src() -> list[TradeSignal]:
        from app.ml.predictor import run_prediction
        out: list[TradeSignal] = []
        for t in tickers:
            try:
                p = await run_prediction(t)
                out.append(TradeSignal(t, p["signal"], float(p["confidence"]),
                                       float(p["current_price"]), p["timing"].get("stop_loss")))
            except Exception as e:  # noqa: BLE001 - one bad ticker must not stop the cycle
                logger.warning("signal failed for %s: %s", t, e)
        return out
    return _src


async def _main(args: argparse.Namespace) -> None:
    tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    if args.broker == "moomoo":
        from app.agent.moomoo_broker import MoomooSimBroker
        from app.core.config import get_settings
        cfg = get_settings()
        broker: Broker = MoomooSimBroker(cfg.moomoo_host, cfg.moomoo_port, market=args.market)
    else:
        broker = SimBroker()
    agent = TradingAgent(broker, RiskManager(), Ledger(args.ledger), predictor_source(tickers))
    for i in range(args.cycles):
        await agent.run_cycle()
        if i < args.cycles - 1:
            await asyncio.sleep(args.interval)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    ap = argparse.ArgumentParser()
    ap.add_argument("--tickers", default="NVDA")
    ap.add_argument("--cycles", type=int, default=1)
    ap.add_argument("--interval", type=float, default=300)
    ap.add_argument("--ledger", default="logs/agent_ledger.jsonl")
    ap.add_argument("--broker", choices=["sim", "moomoo"], default="sim",
                    help="sim = in-memory; moomoo = OpenD paper (SIMULATE) account")
    ap.add_argument("--market", default="US", help="moomoo market for --broker moomoo")
    asyncio.run(_main(ap.parse_args()))
