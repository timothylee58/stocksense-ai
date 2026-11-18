import asyncio
import json
import pathlib
from datetime import datetime, timezone

import pytest

from app.agent.broker import SimBroker
from app.agent.ledger import Ledger
from app.agent.loop import TradingAgent
from app.agent.models import TradeSignal
from app.agent.risk import RiskLimits, RiskManager

NOW = datetime(2026, 11, 17, tzinfo=timezone.utc)


def sig(t="NVDA", a="BUY", c=0.8, p=100.0, stop=95.0):
    return TradeSignal(t, a, c, p, stop)


def rm(**kw):
    r = RiskManager(RiskLimits(kill_switch_path="/nonexistent/KS", **kw))
    r.mark(100_000, NOW)
    return r


def test_sizing_respects_risk_and_position_caps():
    b = SimBroker()
    d = rm().evaluate_entry(sig(), b.get_account())
    # conservative px 100.5, stop 95: (500-2 fee)/5.5 = 90 sh; position cap allows 99
    assert d.approved and d.qty == 90


def test_low_confidence_rejected():
    assert not rm().evaluate_entry(sig(c=0.5), SimBroker().get_account()).approved


def test_soft_drawdown_halves_size():
    r = rm()
    r.mark(94_000, NOW.replace(day=18))  # 6% below peak, new day so daily-loss limit is not hit
    d = r.evaluate_entry(sig(), SimBroker(cash=94_000).get_account())
    assert d.approved and d.size_factor == 0.5 and d.qty == 42


def test_hard_drawdown_halts_and_flattens():
    r = rm()
    r.mark(89_000, NOW)
    assert r.should_flatten()
    assert not r.evaluate_entry(sig(), SimBroker().get_account()).approved


def test_kill_switch_blocks_entries():
    r = rm()
    r.manual_kill = True
    d = r.evaluate_entry(sig(), SimBroker().get_account())
    assert not d.approved and "kill switch" in d.reason


def test_consecutive_losses_invalidate_strategy():
    r = rm()
    for _ in range(5):
        r.record_closed_trade(-10)
    d = r.evaluate_entry(sig(), SimBroker().get_account())
    assert not d.approved and "invalidated" in d.reason


def test_daily_loss_limit():
    r = rm()
    r.mark(96_500, NOW)  # -3.5% on the day
    assert not r.evaluate_entry(sig(), SimBroker().get_account()).approved


def test_max_open_positions():
    b = SimBroker()
    r = rm(max_open_positions=1)
    b.place_order("AAPL", "BUY", 10, 100)
    assert not r.evaluate_entry(sig(), b.get_account()).approved


def _agent(tmp_path, signals):
    async def src():
        return signals.pop(0)
    return TradingAgent(SimBroker(), rm(), Ledger(str(tmp_path / "l.jsonl")), src)


def test_loop_enters_then_stops_out(tmp_path):
    a = _agent(tmp_path, [[sig()], [sig(p=94.0, a="HOLD")]])
    asyncio.run(a.run_cycle())
    assert "NVDA" in a.broker.get_account().positions
    asyncio.run(a.run_cycle())
    assert "NVDA" not in a.broker.get_account().positions
    assert a.risk.closed_pnls and a.risk.closed_pnls[0] < 0
    events = [e["event"] for e in a.ledger.read()]
    assert events.count("fill") == 2 and "decision" in events


def test_loop_flattens_on_kill_switch(tmp_path):
    a = _agent(tmp_path, [[sig()], [sig(a="HOLD")]])
    asyncio.run(a.run_cycle())
    a.risk.manual_kill = True
    asyncio.run(a.run_cycle())
    assert not a.broker.get_account().positions
    assert any(e.get("action") == "flatten" for e in a.ledger.read())


def test_report_summarises_ledger(tmp_path):
    from app.agent.report import summarise, to_markdown
    a = _agent(tmp_path, [[sig()], [sig(p=94.0, a="HOLD")]])
    asyncio.run(a.run_cycle())
    asyncio.run(a.run_cycle())
    s = summarise(a.ledger.read())
    assert s["n_closed_trades"] == 1 and s["win_rate_pct"] == 0
    assert s["max_drawdown_pct"] > 0 and "Trading agent report" in to_markdown(s)


# ── regressions from PR review ───────────────────────────────────────────────
from app.agent.broker import SimBroker as _Sim
from app.agent.risk import effective_stop


def test_invalid_stop_replaced_consistently():
    lim = RiskLimits()
    assert effective_stop(sig(stop=-5.0), lim) == pytest.approx(95.0)
    assert effective_stop(sig(stop=float("nan")), lim) == pytest.approx(95.0)
    assert effective_stop(sig(stop=None), lim) == pytest.approx(95.0)


def test_sizing_never_exceeds_caps_after_costs():
    b = _Sim(cash=100_000)
    d = rm().evaluate_entry(sig(stop=99.9), b.get_account())  # tight stop -> huge risk qty
    assert d.qty * 100.5 + 2 <= 10_000 + 1e-6      # per-position cap incl. buffer and fee


def test_risk_state_survives_restart(tmp_path):
    p = str(tmp_path / "risk.json")
    r = rm()
    r.mark(89_000, NOW)                  # 11% drawdown
    r.record_closed_trade(-5)
    r.save(p)
    r2 = RiskManager(RiskLimits(kill_switch_path="/nonexistent/KS"))
    assert r2.load(p)
    r2.mark(89_000, NOW)
    assert r2.should_flatten() and r2.closed_pnls == [-5]


def test_stopped_out_ticker_not_rebought_same_cycle(tmp_path):
    a = _agent(tmp_path, [[sig()], [sig(p=94.0, a="BUY")]])
    asyncio.run(a.run_cycle())
    asyncio.run(a.run_cycle())
    assert "NVDA" not in a.broker.get_account().positions
    assert len(a.risk.closed_pnls) == 1


def test_held_position_stop_checked_without_signal(tmp_path):
    a = _agent(tmp_path, [[sig()], []])
    asyncio.run(a.run_cycle())
    a.broker.update_prices({"NVDA": 90.0})       # price known, signal missing
    asyncio.run(a.run_cycle())
    assert "NVDA" not in a.broker.get_account().positions


class _NoSell(_Sim):
    def place_order(self, ticker, side, qty, price, stop_loss=None):
        return None if side == "SELL" else super().place_order(ticker, side, qty, price, stop_loss)


class _HalfSell(_Sim):
    def place_order(self, ticker, side, qty, price, stop_loss=None):
        return super().place_order(ticker, side, qty / 2 if side == "SELL" else qty, price, stop_loss)


def test_failed_exit_is_logged(tmp_path):
    async def src():
        return [sig(p=94.0)]
    a = TradingAgent(_NoSell(), rm(), Ledger(str(tmp_path / "l.jsonl")), src)
    a.broker.place_order("NVDA", "BUY", 10, 100.0, 95.0)
    asyncio.run(a.run_cycle())
    ev = a.ledger.read()
    assert any(e.get("action") == "order_rejected" and e.get("side") == "SELL" for e in ev)


def test_partial_exit_is_not_a_closed_trade(tmp_path):
    async def src():
        return [sig(p=94.0, a="HOLD")]
    a = TradingAgent(_HalfSell(), rm(), Ledger(str(tmp_path / "l.jsonl")), src)
    a.broker.place_order("NVDA", "BUY", 10, 100.0, 95.0)
    asyncio.run(a.run_cycle())
    assert a.risk.closed_pnls == []
    assert any(e.get("action") == "partial_exit" for e in a.ledger.read())


def test_last_equity_mark_includes_fills(tmp_path):
    a = _agent(tmp_path, [[sig()]])
    asyncio.run(a.run_cycle())
    eq = [e for e in a.ledger.read() if e["event"] == "equity"]
    assert eq[-1]["phase"] == "post" and eq[-1]["equity"] < 100_000   # costs booked


# ── second review round ──────────────────────────────────────────────────────
def test_kill_switch_file_blocks_entries(tmp_path):
    ks = tmp_path / "KS"
    r = RiskManager(RiskLimits(kill_switch_path=str(ks)))
    r.mark(100_000, NOW)
    assert r.evaluate_entry(sig(), SimBroker().get_account()).approved
    ks.write_text("")
    d = r.evaluate_entry(sig(), SimBroker().get_account())
    assert not d.approved and "kill switch" in d.reason and r.should_flatten()


def test_default_kill_switch_path_is_absolute():
    from app.agent.risk import DEFAULT_KILL_SWITCH
    assert DEFAULT_KILL_SWITCH.startswith("/") and DEFAULT_KILL_SWITCH.endswith("KILL_SWITCH")


def test_hit_rate_invalidation_latches_and_persists(tmp_path):
    r = rm()
    for p in [10, -1] * 10:               # 50% hit rate: fine
        r.record_closed_trade(p)
    assert r.entry_block_reason() is None
    r2 = rm()
    for p in ([10] + [-1] * 4) * 4:       # 20% hit rate, never 5 losses in a row
        r2.record_closed_trade(p)
    assert "hit rate" in (r2.entry_block_reason() or "")
    r2.record_closed_trade(100)           # a later win must NOT clear a latched halt
    assert r2.entry_block_reason() is not None
    path = str(tmp_path / "r.json")
    r2.save(path)
    r3 = rm()
    assert r3.load(path) and r3.entry_block_reason() is not None
    r3.reset_invalidation()
    assert r3.entry_block_reason() is None


def test_flatten_retries_partial_exits(tmp_path):
    class Half(_Sim):
        def place_order(self, ticker, side, qty, price, stop_loss=None):
            return super().place_order(ticker, side, qty / 2 if side == "SELL" else qty, price, stop_loss)

    async def src():
        return [sig(a="HOLD")]
    r = rm()
    r.manual_kill = True
    a = TradingAgent(Half(), r, Ledger(str(tmp_path / "l.jsonl")), src)
    a.broker.place_order("NVDA", "BUY", 8, 100.0, 95.0)
    asyncio.run(a.run_cycle())
    assert not a.broker.get_account().positions or a.broker.get_account().positions["NVDA"].qty < 1.1


def test_signals_are_logged_including_holds(tmp_path):
    a = _agent(tmp_path, [[sig(a="HOLD")]])
    asyncio.run(a.run_cycle())
    assert any(e["event"] == "signal" and e["action"] == "HOLD" for e in a.ledger.read())


def test_fill_does_not_overwrite_ledger_timestamp(tmp_path):
    a = _agent(tmp_path, [[sig()]])
    asyncio.run(a.run_cycle())
    fills = [e for e in a.ledger.read() if e["event"] == "fill"]
    assert "T" in fills[0]["ts"] and "filled_at" in fills[0]


def test_ledger_sanitises_non_finite(tmp_path):
    led = Ledger(str(tmp_path / "l.jsonl"))
    led.write("equity", equity=float("nan"), x=[float("inf")])
    raw = pathlib.Path(led.path).read_text()
    assert "NaN" not in raw and "Infinity" not in raw and led.read()[0]["equity"] is None


def test_sim_round_trip_pnl_matches_cash_change():
    b = _Sim(cash=100_000)
    b.place_order("X", "BUY", 10, 100.0)
    f = b.place_order("X", "SELL", 10, 100.0)
    assert 100_000 + f.realized_pnl == pytest.approx(b.get_account().cash)


def test_report_isolates_runs_and_counts_round_trips(tmp_path):
    from app.agent.report import select, summarise
    path = str(tmp_path / "l.jsonl")
    for _ in range(2):                    # two separate runs in one ledger
        led = Ledger(path)
        async def src():
            return [sig()]
        a = TradingAgent(SimBroker(), rm(), led, src)
        asyncio.run(a.run_cycle())
    ev = Ledger(path).read()
    assert len({e["run_id"] for e in ev}) == 2
    assert len(select(ev)) < len(ev)                          # latest run only
    assert summarise(select(ev))["start_equity"] == 100_000   # not mixed with the other run
    assert select(ev, date="1999-01-01") == []


# ── third review round ───────────────────────────────────────────────────────
class _HalfOnce(_Sim):
    """Sells half the first time, everything afterwards."""
    def __init__(self):
        super().__init__()
        self.first = True

    def place_order(self, ticker, side, qty, price, stop_loss=None):
        if side == "SELL" and self.first:
            self.first = False
            qty = qty / 2
        return super().place_order(ticker, side, qty, price, stop_loss)


def test_partial_exit_pnl_survives_restart(tmp_path):
    state = str(tmp_path / "risk.json")
    b = _HalfOnce()
    b.place_order("NVDA", "BUY", 10, 100.0, 95.0)

    async def lose():
        return [sig(p=90.0, a="HOLD")]      # below the 95 stop: sell at a loss

    a1 = TradingAgent(b, rm(), Ledger(str(tmp_path / "l.jsonl")), lose, state_path=state)
    asyncio.run(a1.run_cycle())
    assert a1.risk.closed_pnls == [] and a1.risk.open_trade_pnl["NVDA"] < 0

    async def gain():
        return [sig(p=120.0, a="SELL")]     # remainder sold at a gain

    r2 = RiskManager(RiskLimits(kill_switch_path="/nonexistent/KS"))
    assert r2.load(state)
    a2 = TradingAgent(b, r2, Ledger(str(tmp_path / "l2.jsonl")), gain, state_path=state)
    asyncio.run(a2.run_cycle())
    assert len(r2.closed_pnls) == 1
    f1 = next(e for e in a1.ledger.read() if e["event"] == "fill")["realized_pnl"]
    f2 = next(e for e in a2.ledger.read() if e["event"] == "fill")["realized_pnl"]
    assert f1 < 0 < f2
    assert r2.closed_pnls[0] == pytest.approx(f1 + f2)   # whole round trip, not just the last leg
    assert r2.open_trade_pnl == {}


class _BreaksAfterSell(_Sim):
    broken = False

    def place_order(self, *a, **kw):
        f = super().place_order(*a, **kw)
        if a[1] == "SELL" and f:
            self.broken = True
        return f

    def get_account(self):
        if self.broken:
            raise RuntimeError("account read failed")
        return super().get_account()


def test_closed_loss_is_saved_even_if_account_read_fails(tmp_path):
    state = str(tmp_path / "risk.json")
    b = _BreaksAfterSell()
    b.place_order("NVDA", "BUY", 10, 100.0, 95.0)

    async def src():
        return [sig(p=90.0, a="HOLD")]
    a = TradingAgent(b, rm(), Ledger(str(tmp_path / "l.jsonl")), src, state_path=state)
    with pytest.raises(RuntimeError):
        asyncio.run(a.run_cycle())
    r2 = RiskManager(RiskLimits(kill_switch_path="/nonexistent/KS"))
    assert r2.load(state) and len(r2.closed_pnls) == 1 and r2.closed_pnls[0] < 0


# ── fourth review round ──────────────────────────────────────────────────────
def test_report_date_includes_all_runs_of_that_day_and_one_broker(tmp_path):
    from app.agent.report import select
    path = str(tmp_path / "l.jsonl")

    async def src():
        return [sig()]
    for brk in ("moomoo", "moomoo", "sim"):
        a = TradingAgent(SimBroker(), rm(), Ledger(path, broker=brk), src)
        asyncio.run(a.run_cycle())
    ev = Ledger(path).read()
    today = ev[0]["ts"][:10]
    moomoo_runs = {e["run_id"] for e in select(ev, date=today, broker="moomoo")}
    assert len(moomoo_runs) == 2                                  # both earlier runs, not just the latest
    assert {e["broker"] for e in select(ev, date=today, broker="moomoo")} == {"moomoo"}
    assert {e["broker"] for e in select(ev, date=today)} == {"sim"}   # default: latest event's broker
    assert len({e["run_id"] for e in select(ev)}) == 1            # no flags: latest run only


def test_orphaned_partial_pnl_is_not_carried_into_next_trade(tmp_path):
    state = str(tmp_path / "risk.json")
    r = rm()
    r.open_trade_pnl["NVDA"] = -500.0        # left over from a position closed outside the agent

    async def src():
        return [sig(a="HOLD")]
    a = TradingAgent(SimBroker(), r, Ledger(str(tmp_path / "l.jsonl")), src, state_path=state)
    asyncio.run(a.run_cycle())
    assert r.open_trade_pnl == {}
    assert any(e.get("action") == "orphaned_partial_pnl" for e in a.ledger.read())
    assert json.loads(pathlib.Path(state).read_text())["open_trade_pnl"] == {}   # persisted clean
