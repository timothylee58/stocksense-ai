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
from app.agent.risk import RiskManager, effective_stop

logger = logging.getLogger("agent")

SignalSource = Callable[[], Awaitable[list[TradeSignal]]]


class TradingAgent:
    def __init__(self, broker: Broker, risk: RiskManager, ledger: Ledger, source: SignalSource,
                 state_path: str | None = None):
        self.broker, self.risk, self.ledger, self.source = broker, risk, ledger, source
        self.state_path = state_path
        self.state_ok = True      # False while risk state cannot be saved: entries fail closed

    def _persist(self) -> None:
        """Save risk state. A write failure must never stop exits: log it and block new entries."""
        if not self.state_path:
            return
        try:
            self.risk.save(self.state_path)
            self.state_ok = True
        except OSError as exc:
            self.state_ok = False
            logger.error("cannot persist risk state to %s: %s", self.state_path, exc)
            try:
                self.ledger.write("risk_event", action="state_persist_failed", error=str(exc))
            except OSError:
                pass

    def _sell(self, ticker: str, price: float, reason: str) -> bool:
        """Sell the whole position. Returns True only if the position is gone."""
        pos = self.broker.get_account().positions.get(ticker)
        if not pos:
            return True
        qty_before = pos.qty        # brokers may mutate `pos` in place
        fill = self.broker.place_order(ticker, "SELL", qty_before, price)
        if not fill:
            self.ledger.write("risk_event", action="order_rejected", side="SELL",
                              ticker=ticker, reason=reason)
            return False
        # closure comes from the confirmed fill quantity, not a second account read
        remaining = max(qty_before - fill.qty, 0.0)
        closed = remaining <= 1e-9
        pnl = self.risk.open_trade_pnl.get(ticker, 0.0) + (fill.realized_pnl or 0.0)
        trade_pnl = None
        if closed:   # one closed trade per round trip; partial fills were summed
            self.risk.open_trade_pnl.pop(ticker, None)
            self.risk.record_closed_trade(pnl)
            trade_pnl = pnl
        else:
            self.risk.open_trade_pnl[ticker] = pnl
        self._persist()      # durable before anything else can fail
        self.ledger.write("fill", reason=reason, closed=closed, trade_pnl=trade_pnl,
                          remaining=remaining, **fill.__dict__)
        if not closed:
            self.ledger.write("risk_event", action="partial_exit", ticker=ticker, remaining=remaining)
        return closed

    def _reconcile(self, acct) -> None:
        """Drop partial-exit PnL whose position no longer exists (closed outside the agent).

        It is keyed by ticker only, so keeping it would leak into the next round trip.
        """
        orphans = [t for t in self.risk.open_trade_pnl if t not in acct.positions]
        for t in orphans:
            lost = self.risk.open_trade_pnl.pop(t)
            self.ledger.write("risk_event", action="orphaned_partial_pnl", ticker=t, pnl=lost,
                              note="position closed outside the agent; PnL not carried forward")
        if orphans:
            self._persist()

    def _mark(self, phase: str) -> None:
        acct = self.broker.get_account()
        self.risk.mark(acct.equity, utcnow())
        self.ledger.write("equity", phase=phase, equity=acct.equity, cash=acct.cash,
                          drawdown=self.risk.drawdown, daily_loss=self.risk.daily_loss)

    def _flatten(self, attempts: int = 3) -> None:
        reason = self.risk.halt_reason() or "halt"
        self.ledger.write("risk_event", action="flatten", reason=reason)
        for _ in range(attempts):      # retry partial/failed exits within the cycle
            acct = self.broker.get_account()
            if not acct.positions:
                return
            for t, pos in list(acct.positions.items()):
                self._sell(t, acct.prices.get(t, pos.avg_price), reason)
        left = list(self.broker.get_account().positions)
        if left:
            self.ledger.write("risk_event", action="flatten_incomplete", remaining=left)

    async def run_cycle(self) -> None:
        signals = await self.source()
        for s_ in signals:      # full input audit trail, including HOLDs and no-op SELLs
            self.ledger.write("signal", ticker=s_.ticker, action=s_.action,
                              confidence=s_.confidence, price=s_.price, stop_loss=s_.stop_loss)
        self.broker.update_prices({s.ticker: s.price for s in signals})
        acct = self.broker.get_account()
        self._reconcile(acct)
        self._mark("pre")

        # held positions whose signal is missing still need their stops checked
        have = {s.ticker for s in signals}
        for t, pos in acct.positions.items():
            if t not in have:
                px = acct.prices.get(t, pos.avg_price)
                self.ledger.write("signal", ticker=t, action="HOLD", price=px,
                                  note="held position, no signal this cycle")
                signals.append(TradeSignal(t, "HOLD", 0.0, px))

        try:
            if self.risk.should_flatten():
                self._flatten()
                return

            # 1) exits are never blocked by the gate
            sold: set[str] = set()
            for s in signals:
                why = self.risk.exit_reason(s, self.broker.get_account())
                if why:
                    self.ledger.write("decision", ticker=s.ticker, action="SELL", approved=True, reason=why)
                    self._sell(s.ticker, s.price, why)
                    sold.add(s.ticker)

            # exits changed equity: re-mark before gating entries
            self._mark("post_exit")
            if self.risk.should_flatten():
                self._flatten()
                return

            # 2) entries, most confident first; never re-buy what we just sold
            if not self.state_ok:
                self.ledger.write("risk_event", action="entries_blocked",
                                  reason="risk state is not being saved")
                return
            for s in sorted((x for x in signals if x.action == "BUY"), key=lambda x: -x.confidence):
                if s.ticker in sold:
                    self.ledger.write("decision", ticker=s.ticker, action="BUY", approved=False,
                                      reason="sold earlier this cycle")
                    continue
                acct = self.broker.get_account()
                d = self.risk.evaluate_entry(s, acct)
                self.ledger.write("decision", ticker=s.ticker, action="BUY", approved=d.approved,
                                  qty=d.qty, reason=d.reason, confidence=s.confidence, price=s.price)
                if not d.approved:
                    continue
                stop = effective_stop(s, self.risk.limits)   # same stop as used for sizing
                fill = self.broker.place_order(s.ticker, "BUY", d.qty, s.price, stop)
                if fill:
                    self.risk.open_trade_pnl.pop(s.ticker, None)   # a new round trip starts clean
                    self.ledger.write("fill", reason="entry", stop_loss=stop, **fill.__dict__)
                else:
                    self.ledger.write("risk_event", action="order_rejected", side="BUY", ticker=s.ticker)
        finally:
            try:
                self._mark("post")                  # report sees fills and costs
            finally:
                self._persist()                     # saved even if the account read fails


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
    risk = RiskManager()
    # persist only against a real (paper) account; the in-memory sim restarts at $100k
    state = args.risk_state if args.broker == "moomoo" else None
    if state and risk.load(state):
        logger.info("restored risk state from %s", state)
    agent = TradingAgent(broker, risk, Ledger(args.ledger, broker=args.broker), predictor_source(tickers),
                         state_path=state)
    try:
        for i in range(args.cycles):
            await agent.run_cycle()
            if i < args.cycles - 1:
                await asyncio.sleep(args.interval)
    finally:
        getattr(broker, "close", lambda: None)()   # moomoo contexts keep the process alive


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    ap = argparse.ArgumentParser()
    ap.add_argument("--tickers", default="NVDA")
    ap.add_argument("--cycles", type=int, default=1)
    ap.add_argument("--interval", type=float, default=300)
    ap.add_argument("--ledger", default="logs/agent_ledger.jsonl")
    ap.add_argument("--risk-state", default="logs/risk_state.json",
                    help="persisted peak equity / loss history; delete to reset")
    ap.add_argument("--broker", choices=["sim", "moomoo"], default="sim",
                    help="sim = in-memory; moomoo = OpenD paper (SIMULATE) account")
    ap.add_argument("--market", default="US", help="moomoo market for --broker moomoo")
    asyncio.run(_main(ap.parse_args()))
