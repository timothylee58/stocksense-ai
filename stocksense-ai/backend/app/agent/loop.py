"""Execution loop: signals -> exits -> risk-gated entries -> fills -> ledger.

    python -m app.agent.loop --tickers NVDA,AAPL --cycles 1 --broker sim

Use --broker moomoo for the OpenD paper (SIMULATE) account; default is the
in-memory simulator.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
from collections.abc import Awaitable, Callable

from app.agent.broker import Broker, SimBroker
from app.agent.ledger import Ledger
from app.agent.models import TradeSignal, utcnow
from app.agent.risk import RiskManager, effective_stop

logger = logging.getLogger("agent")

SignalSource = Callable[[], Awaitable[list[TradeSignal]]]


class TradingAgent:
    def __init__(self, broker: Broker, risk: RiskManager, ledger: Ledger, source: SignalSource,
                 state_path: str | None = None, state_unreadable: bool = False):
        self.broker, self.risk, self.ledger, self.source = broker, risk, ledger, source
        self.state_path = state_path
        self.state_ok = True      # False while risk state cannot be saved: entries fail closed
        # audit-trail health is tracked apart from state_ok so a successful risk-state save can
        # never clear it; once a ledger write is lost, entries stay blocked until restart
        self.ledger_ok = True
        # a failed save in an earlier process may have lost a closed trade: needs a human ack
        self.unresolved_failure = bool(state_path) and ledger.unresolved_state_failure(ledger.broker)
        # the state file exists but cannot be loaded: never overwrite it, hold entries for a human
        self.state_unreadable = state_unreadable
        self._probed = False

    def _log(self, event: str, **fields) -> None:
        """Audit write that can never skip an exit: on failure entries fail closed instead."""
        try:
            self.ledger.write(event, **fields)
        except OSError as exc:
            self.ledger_ok = False
            logger.error("ledger write failed (%s): %s", event, exc)

    def _entry_block_reason(self) -> str | None:
        """Why new entries must not be placed right now (exits and flatten are never blocked)."""
        if self.state_unreadable:
            return "risk state file is unreadable; repair or remove it"
        if self.unresolved_failure:
            return "an earlier risk-state save failed; reconcile, then run with --ack-state-failure"
        if not self.state_ok:
            return "risk state is not being saved"
        if not self.ledger_ok:
            return "an audit-ledger write failed; entries stay blocked until the ledger is repaired and the agent restarted"
        if getattr(self.broker, "stops_unsaved", False):
            return "stop-loss state could not be saved; restore it before opening more positions"
        if hasattr(self.broker, "stops_unsaved"):        # broker that tracks stops itself (Moomoo)
            bare = [t for t, p in self.broker.get_account().positions.items() if p.stop_loss is None]
            if bare:
                return f"position(s) without a stop-loss: {', '.join(sorted(bare))}"
        return None

    def _persist(self) -> None:
        """Save risk state. A write failure must never stop exits: log it and block new entries."""
        if not self.state_path or self.state_unreadable:
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
            self._log("risk_event", action="order_rejected", side="SELL",
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
        self._log("fill", reason=reason, closed=closed, trade_pnl=trade_pnl,
                          remaining=remaining, **fill.__dict__)
        if not closed:
            self._log("risk_event", action="partial_exit", ticker=ticker, remaining=remaining)
        return closed

    def _reconcile(self, acct) -> None:
        """Drop partial-exit PnL whose position no longer exists (closed outside the agent).

        It is keyed by ticker only, so keeping it would leak into the next round trip.
        """
        orphans = [t for t in self.risk.open_trade_pnl if t not in acct.positions]
        for t in orphans:
            lost = self.risk.open_trade_pnl.pop(t)
            self._log("risk_event", action="orphaned_partial_pnl", ticker=t, pnl=lost,
                              note="position closed outside the agent; PnL not carried forward")
        if orphans:
            self._persist()

    def _mark(self, phase: str) -> None:
        acct = self.broker.get_account()
        self.risk.mark(acct.equity, utcnow())
        self._log("equity", phase=phase, equity=acct.equity, cash=acct.cash,
                          drawdown=self.risk.drawdown, daily_loss=self.risk.daily_loss)

    def _flatten(self, attempts: int = 3) -> None:
        reason = self.risk.halt_reason() or "halt"
        self._log("risk_event", action="flatten", reason=reason)
        for _ in range(attempts):      # retry partial/failed exits within the cycle
            acct = self.broker.get_account()
            if not acct.positions:
                return
            for t, pos in list(acct.positions.items()):
                self._sell(t, acct.prices.get(t, pos.avg_price), reason)
        left = list(self.broker.get_account().positions)
        if left:
            self._log("risk_event", action="flatten_incomplete", remaining=left)

    async def run_cycle(self) -> None:
        signals = await self.source()
        for s_ in signals:      # full input audit trail, including HOLDs and no-op SELLs
            self._log("signal", ticker=s_.ticker, action=s_.action,
                              confidence=s_.confidence, price=s_.price, stop_loss=s_.stop_loss,
                              source=s_.source)
        self.broker.update_prices({s.ticker: s.price for s in signals})
        acct = self.broker.get_account()
        self._reconcile(acct)
        if not self._probed:       # find an unwritable state path before any order is placed
            self._probed = True
            self._persist()
        self._mark("pre")

        # held positions whose signal is missing still need their stops checked
        have = {s.ticker for s in signals}
        for t, pos in acct.positions.items():
            if t not in have:
                px = acct.prices.get(t, pos.avg_price)
                self._log("signal", ticker=t, action="HOLD", price=px,
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
                    self._log("decision", ticker=s.ticker, action="SELL", approved=True, reason=why)
                    self._sell(s.ticker, s.price, why)
                    sold.add(s.ticker)

            # exits changed equity: re-mark before gating entries
            self._mark("post_exit")
            if self.risk.should_flatten():
                self._flatten()
                return

            # 2) entries, most confident first; never re-buy what we just sold
            blocked = self._entry_block_reason()
            if blocked:
                self._log("risk_event", action="entries_blocked", reason=blocked)
                return
            for s in sorted((x for x in signals if x.action == "BUY"), key=lambda x: -x.confidence):
                if s.ticker in sold:
                    self._log("decision", ticker=s.ticker, action="BUY", approved=False,
                                      reason="sold earlier this cycle")
                    continue
                blocked = self._entry_block_reason()          # recheck: an earlier order may have
                if blocked:                                   # left stops or the ledger unsaved
                    self._log("risk_event", action="entries_blocked", reason=blocked)
                    break
                acct = self.broker.get_account()
                d = self.risk.evaluate_entry(s, acct)
                self._log("decision", ticker=s.ticker, action="BUY", approved=d.approved,
                                  qty=d.qty, reason=d.reason, confidence=s.confidence, price=s.price)
                if not d.approved:
                    continue
                if not self.ledger_ok:        # the decision itself could not be recorded
                    break
                stop = effective_stop(s, self.risk.limits)   # same stop as used for sizing
                fill = self.broker.place_order(s.ticker, "BUY", d.qty, s.price, stop)
                if fill:
                    self.risk.open_trade_pnl.pop(s.ticker, None)   # a new round trip starts clean
                    self._log("fill", reason="entry", stop_loss=stop, **fill.__dict__)
                else:
                    self._log("risk_event", action="order_rejected", side="BUY", ticker=s.ticker)
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
                                       float(p["current_price"]), p["timing"].get("stop_loss"),
                                       p.get("signal_source")))
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
    try:
        risk = RiskManager()
        # persist only against a real (paper) account; the in-memory sim restarts at $100k
        state = args.risk_state if args.broker == "moomoo" else None
        loaded = bool(state) and risk.load(state)
        if loaded:
            logger.info("restored risk state from %s", state)
        unreadable = bool(state) and not loaded and os.path.exists(state)
        ledger = Ledger(args.ledger, broker=args.broker)
        if args.ack_state_failure:
            if unreadable:
                # acknowledging would clear the only restart gate while the history is still missing
                raise SystemExit(f"cannot acknowledge: {state} exists but cannot be loaded; repair it first")
            ledger.write("risk_event", action="state_failure_acknowledged")
        if args.reset_invalidation:
            if not loaded:
                raise SystemExit("--reset-invalidation needs a loadable risk state file")
            risk.reset_invalidation()      # keeps peak equity and drawdown history intact
            risk.save(state)
            ledger.write("risk_event", action="invalidation_reset")
        agent = TradingAgent(broker, risk, ledger, predictor_source(tickers), state_path=state,
                             state_unreadable=unreadable)
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
                    help="persisted peak equity / loss history; do not delete to clear an invalidation")
    ap.add_argument("--broker", choices=["sim", "moomoo"], default="sim",
                    help="sim = in-memory; moomoo = OpenD paper (SIMULATE) account")
    ap.add_argument("--market", default="US", help="moomoo market for --broker moomoo")
    ap.add_argument("--ack-state-failure", action="store_true",
                    help="confirm you reconciled risk state after a failed save; unblocks entries")
    ap.add_argument("--reset-invalidation", action="store_true",
                    help="clear a latched strategy invalidation (keeps peak equity/drawdown history)")
    asyncio.run(_main(ap.parse_args()))
