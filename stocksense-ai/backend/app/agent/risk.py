"""Pre-trade risk gate. Pure logic, no I/O except an optional kill-switch file.

Rules (all limits configurable via RiskLimits):
  * Kill switch: manual flag or file on disk -> block entries, flatten book.
  * Drawdown ladder: soft DD halves position size; hard DD halts + flattens.
  * Daily loss limit: no new entries for the rest of the day.
  * Strategy invalidation: N consecutive losses or rolling hit-rate below
    a floor -> halt entries (the thesis is considered broken).
  * Sizing: risk a fixed % of equity per trade to the stop, capped by
    per-position and gross-exposure limits and cash.
Exits (stop-loss / SELL signal) are never blocked by the gate.
"""
from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

from app.agent.models import Account, TradeSignal

# Anchored to the backend directory so the file works from any cwd.
DEFAULT_KILL_SWITCH = str(Path(__file__).resolve().parents[2] / "KILL_SWITCH")


@dataclass
class RiskLimits:
    min_confidence: float = 0.60
    max_position_pct: float = 0.10       # of equity, per ticker
    max_gross_exposure_pct: float = 0.60
    max_open_positions: int = 5
    risk_per_trade_pct: float = 0.005    # equity risked to the stop
    default_stop_pct: float = 0.05       # used if the signal has no stop
    soft_drawdown_pct: float = 0.05      # halve size
    hard_drawdown_pct: float = 0.10      # halt + flatten
    daily_loss_limit_pct: float = 0.03
    max_consecutive_losses: int = 5
    hit_rate_window: int = 20
    min_hit_rate: float = 0.35
    kill_switch_path: str = DEFAULT_KILL_SWITCH
    # Size against a conservative executable price: limit aggression + slippage.
    require_model_signal: bool = True    # no new positions on the rule-based fallback
    exec_buffer_pct: float = 0.005
    fee_allowance: float = 2.0           # per order, reserved out of cash/risk


def effective_stop(sig: TradeSignal, limits: RiskLimits) -> float:
    """The one stop used for both sizing and order submission."""
    st = sig.stop_loss
    if st is not None and math.isfinite(st) and 0 < st < sig.price:
        return float(st)
    return sig.price * (1 - limits.default_stop_pct)


@dataclass
class Decision:
    approved: bool
    qty: float = 0.0
    reason: str = ""
    size_factor: float = 1.0


@dataclass
class RiskManager:
    limits: RiskLimits = field(default_factory=RiskLimits)
    peak_equity: float = 0.0
    day: date | None = None
    day_start_equity: float = 0.0
    closed_pnls: list[float] = field(default_factory=list)
    manual_kill: bool = False
    invalidated: str | None = None      # latched until a human resets it
    open_trade_pnl: dict = field(default_factory=dict)   # realized PnL of partly-closed trades
    equity_known: bool = True
    _equity: float = 0.0

    # ── persistence (survive restarts) ───────────────────────────────────────
    def save(self, path: str) -> None:
        d = os.path.dirname(path)
        if d:
            os.makedirs(d, exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"peak_equity": self.peak_equity,
                       "day": self.day.isoformat() if self.day else None,
                       "day_start_equity": self.day_start_equity,
                       "closed_pnls": self.closed_pnls[-200:],
                       "invalidated": self.invalidated,
                       "open_trade_pnl": self.open_trade_pnl}, f)
        os.replace(tmp, path)

    def load(self, path: str) -> bool:
        """Load saved state. Returns False, changing nothing, for any unreadable or malformed file."""
        try:
            with open(path, encoding="utf-8") as f:
                st = json.load(f)
            if not isinstance(st, dict):
                return False
            def num(v: Any) -> float:
                if isinstance(v, bool) or not isinstance(v, (int, float)):
                    raise TypeError("not a number")
                return float(v)

            peak = num(st["peak_equity"])
            day_raw = st["day"]
            if day_raw is not None and not isinstance(day_raw, str):
                return False
            day = date.fromisoformat(day_raw) if day_raw else None
            day_start = num(st["day_start_equity"])
            if not isinstance(st["closed_pnls"], list) or not isinstance(st["open_trade_pnl"], dict):
                return False
            closed = [num(x) for x in st["closed_pnls"]]
            invalidated = st["invalidated"]
            if invalidated is not None and not isinstance(invalidated, str):
                return False
            open_pnl = {str(k): num(v) for k, v in st["open_trade_pnl"].items()}
            numbers = [peak, day_start, *closed, *open_pnl.values()]
            if not all(math.isfinite(x) for x in numbers) or peak < 0 or day_start < 0:
                return False       # NaN/inf/negative would silently disable drawdown protection
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            return False
        self.peak_equity, self.day, self.day_start_equity = peak, day, day_start
        self.closed_pnls, self.invalidated, self.open_trade_pnl = closed, invalidated, open_pnl
        return True

    # ── state updates ────────────────────────────────────────────────────────
    def mark(self, equity: float, now: datetime) -> None:
        if not isinstance(equity, (int, float)) or not math.isfinite(equity):
            self.equity_known = False          # NaN would make every drawdown comparison false
            return
        self.equity_known = True
        self._equity = equity
        self.peak_equity = max(self.peak_equity, equity)
        if self.day != now.date():
            self.day = now.date()
            self.day_start_equity = equity

    def reset_invalidation(self) -> None:
        """Human decision to resume after reviewing the thesis."""
        self.invalidated = None
        self.closed_pnls.clear()

    def record_closed_trade(self, pnl: float) -> None:
        self.closed_pnls.append(pnl)

    # ── status checks ────────────────────────────────────────────────────────
    @property
    def drawdown(self) -> float:
        if self.peak_equity <= 0:
            return 0.0
        return max(0.0, (self.peak_equity - self._equity) / self.peak_equity)

    @property
    def daily_loss(self) -> float:
        if self.day_start_equity <= 0:
            return 0.0
        return max(0.0, (self.day_start_equity - self._equity) / self.day_start_equity)

    def kill_switch_active(self) -> bool:
        return self.manual_kill or os.path.exists(self.limits.kill_switch_path)

    def halt_reason(self) -> str | None:
        """Reason new entries are blocked, or None. Hard halts also flatten."""
        lim = self.limits
        if self.kill_switch_active():
            return "kill switch active"
        if not self.equity_known:
            return "account equity unavailable or not finite"
        if self.drawdown >= lim.hard_drawdown_pct:
            return f"hard drawdown {self.drawdown:.1%} >= {lim.hard_drawdown_pct:.0%}"
        return self.entry_block_reason()

    def should_flatten(self) -> bool:
        return self.kill_switch_active() or self.drawdown >= self.limits.hard_drawdown_pct

    def entry_block_reason(self) -> str | None:
        lim = self.limits
        if self.daily_loss >= lim.daily_loss_limit_pct:
            return f"daily loss {self.daily_loss:.1%} >= {lim.daily_loss_limit_pct:.0%}"
        if self.invalidated:
            return self.invalidated
        tail = self.closed_pnls[-lim.max_consecutive_losses:]
        if len(tail) == lim.max_consecutive_losses and all(p < 0 for p in tail):
            self.invalidated = f"strategy invalidated: {lim.max_consecutive_losses} consecutive losses"
            return self.invalidated
        win = self.closed_pnls[-lim.hit_rate_window:]
        if len(win) == lim.hit_rate_window:
            hit = sum(p > 0 for p in win) / len(win)
            if hit < lim.min_hit_rate:
                self.invalidated = f"strategy invalidated: hit rate {hit:.0%} < {lim.min_hit_rate:.0%}"
                return self.invalidated
        return None

    # ── entry gate ───────────────────────────────────────────────────────────
    def evaluate_entry(self, sig: TradeSignal, acct: Account) -> Decision:
        lim = self.limits
        if sig.action != "BUY":
            return Decision(False, reason="not a BUY signal")
        halt = self.halt_reason()
        if halt:
            return Decision(False, reason=f"halted: {halt}")
        if lim.require_model_signal and sig.source != "xgb_binary":
            # allow-list: a missing, rule-based, demo or unverified source never opens a position
            return Decision(False, reason=f"signal is not from a verified trained model "
                                          f"(source={sig.source})")
        if sig.confidence < lim.min_confidence:
            return Decision(False, reason=f"confidence {sig.confidence:.2f} < {lim.min_confidence:.2f}")
        if sig.ticker in acct.positions:
            return Decision(False, reason="already holding")
        if len(acct.positions) >= lim.max_open_positions:
            return Decision(False, reason="max open positions")
        if not math.isfinite(sig.price) or sig.price <= 0:
            return Decision(False, reason="invalid price")

        equity = acct.equity
        stop = effective_stop(sig, lim)
        px = sig.price * (1 + lim.exec_buffer_pct)      # conservative fill price
        risk_per_share = px - stop

        factor = 0.5 if self.drawdown >= lim.soft_drawdown_pct else 1.0
        budget = equity * lim.risk_per_trade_pct * factor - lim.fee_allowance
        qty_by_risk = budget / risk_per_share if budget > 0 else 0.0
        qty_by_pos = (equity * lim.max_position_pct * factor - lim.fee_allowance) / px
        room = max(0.0, equity * lim.max_gross_exposure_pct - acct.gross_exposure)
        qty_by_gross = (room - lim.fee_allowance) / px
        qty_by_cash = (acct.cash - lim.fee_allowance) / px

        qty = math.floor(max(0.0, min(qty_by_risk, qty_by_pos, qty_by_gross, qty_by_cash)))
        if qty < 1:
            return Decision(False, reason="size < 1 share after limits")
        note = "soft-drawdown half size" if factor < 1 else "ok"
        return Decision(True, qty=float(qty), reason=note, size_factor=factor)

    # ── exit rules (never blocked) ───────────────────────────────────────────
    def exit_reason(self, sig: TradeSignal, acct: Account) -> str | None:
        pos = acct.positions.get(sig.ticker)
        if pos is None:
            return None
        if pos.stop_loss is not None and sig.price <= pos.stop_loss:
            return f"stop-loss hit ({sig.price:.2f} <= {pos.stop_loss:.2f})"
        if sig.action == "SELL":
            return "SELL signal"
        return None
