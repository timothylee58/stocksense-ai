"""Moomoo OpenAPI paper-trading broker (TrdEnv.SIMULATE only).

Requires moomoo OpenD running and logged in. The environment is hard-coded
to SIMULATE: there is deliberately no way to pass REAL, so this class cannot
place live orders.

Notes
  * Orders are limit orders priced slightly through the market (`aggression_bps`)
    so they fill like a market order but with bounded slippage.
  * `place_order` blocks (polls) up to `fill_timeout` seconds; unfilled
    remainder is cancelled and a partial fill is returned as-is.
  * Moomoo has no native stop for this flow, so stop-losses are tracked
    locally and persisted to `state_path` to survive restarts.
"""
from __future__ import annotations

import json
import logging
import math
import os
import time
from typing import Any

from app.agent.models import Account, Fill, Position, Side

logger = logging.getLogger("agent.moomoo")

_TERMINAL = {"FILLED_ALL", "CANCELLED_ALL", "CANCELLED_PART", "FAILED", "SUBMIT_FAILED",
             "TIMEOUT", "DISABLED", "DELETED", "FILL_CANCELLED"}
_PREFIXES = ("US.", "MY.", "HK.", "SG.", "CN.")


class MoomooSimBroker:
    def __init__(self, host: str = "127.0.0.1", port: int = 11111, market: str = "US",
                 security_firm: str = "FUTUINC", acc_id: int = 0, fill_timeout: float = 20.0,
                 poll_interval: float = 1.0, cancel_timeout: float = 5.0,
                 aggression_bps: float = 20.0,
                 state_path: str = "logs/moomoo_stops.json", ctx: Any = None):
        import moomoo as m
        self._m = m
        self.env = m.TrdEnv.SIMULATE
        self.market = market.upper()
        self.acc_id = acc_id
        self.fill_timeout, self.poll = fill_timeout, poll_interval
        self.cancel_timeout = cancel_timeout
        self.aggr = aggression_bps / 10_000
        self.state_path = state_path
        self._prices: dict[str, float] = {}
        self._stops: dict[str, float] = self._load_stops()
        self.ctx = ctx or m.OpenSecTradeContext(
            filter_trdmarket=getattr(m.TrdMarket, self.market), host=host, port=port,
            security_firm=getattr(m.SecurityFirm, security_firm))

    # ── helpers ──────────────────────────────────────────────────────────────
    def _code(self, ticker: str) -> str:
        return ticker if ticker.upper().startswith(_PREFIXES) else f"{self.market}.{ticker.upper()}"

    def _ticker(self, code: str) -> str:
        return code.split(".", 1)[1] if code.upper().startswith(_PREFIXES) else code

    stops_unsaved = False      # set when a fill happened but the stop file could not be written

    def _load_stops(self) -> dict[str, float]:
        try:
            with open(self.state_path, encoding="utf-8") as f:
                return {k: float(v) for k, v in json.load(f).items()}
        except FileNotFoundError:
            return {}
        except (OSError, ValueError):
            logger.error("stop-loss state %s is unreadable; protecting no positions until "
                         "stops are re-set", self.state_path)
            return {}

    def _save_stops(self) -> None:
        d = os.path.dirname(self.state_path)
        if d:
            os.makedirs(d, exist_ok=True)
        tmp = self.state_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:     # atomic: never leave half a file
            json.dump(self._stops, f)
        os.replace(tmp, self.state_path)
        self.stops_unsaved = False      # the whole in-memory stop map is now durable

    def _ok(self, ret: Any, data: Any, what: str) -> bool:
        if ret == self._m.RET_OK:
            return True
        logger.error("moomoo %s failed: %s", what, data)
        return False

    # ── Broker interface ─────────────────────────────────────────────────────
    def update_prices(self, prices: dict[str, float]) -> None:
        self._prices.update(prices)

    def get_account(self) -> Account:
        ret, info = self.ctx.accinfo_query(trd_env=self.env, acc_id=self.acc_id, refresh_cache=True)
        if not self._ok(ret, info, "accinfo_query"):
            raise RuntimeError("cannot read moomoo account")
        cash = float(info["cash"].iloc[0])
        ret, pos = self.ctx.position_list_query(trd_env=self.env, acc_id=self.acc_id, refresh_cache=True)
        if not self._ok(ret, pos, "position_list_query"):
            raise RuntimeError("cannot read moomoo positions")
        acct = Account(cash=cash, prices=dict(self._prices))
        for _, r in pos.iterrows():
            qty = float(r["qty"])
            if qty <= 0:
                continue
            t = self._ticker(str(r["code"]))
            acct.positions[t] = Position(t, qty, float(r["cost_price"]), self._stops.get(t))
            acct.prices.setdefault(t, float(r.get("nominal_price", r["cost_price"])))
        return acct

    def place_order(self, ticker: str, side: Side, qty: float, price: float,
                    stop_loss: float | None = None) -> Fill | None:
        m = self._m
        if ticker.upper().startswith(_PREFIXES) and not ticker.upper().startswith(self.market + "."):
            logger.error("refusing %s: market prefix does not match broker market %s", ticker, self.market)
            return None
        ticker = self._ticker(self._code(ticker))      # accept "NVDA" or "US.NVDA"
        if not (math.isfinite(qty) and math.isfinite(price)) or qty <= 0 or price <= 0:
            return None
        if stop_loss is not None and not (math.isfinite(stop_loss) and 0 < stop_loss < price):
            stop_loss = None                            # an invalid stop is never recorded
        before = None
        if side == "SELL":
            before = self.get_account().positions.get(ticker)
            if before is None:
                return None
            send_qty = float(qty)                       # allow closing fractional holdings
        else:
            send_qty = float(math.floor(qty))           # buy whole shares only
            if send_qty < 1:
                return None
        raw = price * (1 + self.aggr if side == "BUY" else 1 - self.aggr)
        limit = round(raw, 2 if raw >= 1 else 4)        # finer ticks for sub-$1 stocks
        ret, data = self.ctx.place_order(
            price=limit, qty=send_qty, code=self._code(ticker),
            trd_side=m.TrdSide.BUY if side == "BUY" else m.TrdSide.SELL,
            order_type=m.OrderType.NORMAL, trd_env=self.env, acc_id=self.acc_id)
        if not self._ok(ret, data, "place_order"):
            return None
        order_id = str(data["order_id"].iloc[0])
        dealt, avg = self._wait_fill(order_id)
        if dealt <= 0:
            logger.warning("order %s for %s not filled", order_id, ticker)
            return None
        pnl = None
        try:
            if side == "BUY":
                if stop_loss:
                    prev = self._stops.get(ticker)
                    self._stops[ticker] = max(prev, stop_loss) if prev else stop_loss   # ratchet up only
                    self._save_stops()
            else:
                pnl = (avg - before.avg_price) * dealt   # gross: commission not reported by the API
                if dealt >= before.qty:
                    self._stops.pop(ticker, None)
                    self._save_stops()
        except OSError:
            # the order already filled: losing the Fill would hide a real position from the ledger
            logger.error("stop-loss state %s not writable; fill for %s is real", self.state_path, ticker)
            self.stops_unsaved = True
        if side == "SELL" and pnl is None:
            pnl = (avg - before.avg_price) * dealt
        self._prices[ticker] = price
        return Fill(ticker, side, dealt, avg, 0.0, pnl)

    def _poll(self, order_id: str) -> tuple[float, float, bool]:
        """Latest (dealt_qty, avg_price, is_terminal) for an order."""
        ret, df = self.ctx.order_list_query(order_id=order_id, trd_env=self.env,
                                            acc_id=self.acc_id, refresh_cache=True)
        if not self._ok(ret, df, "order_list_query") or not len(df):
            return 0.0, 0.0, False
        row = df.iloc[0]
        return (float(row["dealt_qty"]), float(row["dealt_avg_price"]),
                str(row["order_status"]) in _TERMINAL)

    def _wait_fill(self, order_id: str) -> tuple[float, float]:
        deadline = time.time() + self.fill_timeout
        dealt, avg = 0.0, 0.0
        while True:
            dealt, avg, done = self._poll(order_id)
            if done:
                return dealt, avg
            if time.time() >= deadline:
                break
            time.sleep(self.poll)
        # timed out: cancel, then confirm the final state (a fill can land
        # between the last poll and the cancel, or the cancel can fail)
        ret, data = self.ctx.modify_order(self._m.ModifyOrderOp.CANCEL, order_id, 0, 0,
                                          trd_env=self.env, acc_id=self.acc_id)
        if not self._ok(ret, data, "cancel_order"):
            logger.error("cancel failed for order %s; it may still be live", order_id)
        end = time.time() + self.cancel_timeout
        while time.time() < end:
            dealt, avg, done = self._poll(order_id)
            if done:
                return dealt, avg
            time.sleep(self.poll)
        dealt, avg, _ = self._poll(order_id)
        logger.error("order %s not terminal after cancel; reporting %s filled", order_id, dealt)
        return dealt, avg

    def close(self) -> None:
        self.ctx.close()
