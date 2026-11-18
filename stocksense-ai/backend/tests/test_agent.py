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
    lim = RiskLimits(kill_switch_path="/nonexistent/KS")
    b = _Sim(cash=100_000)
    d = rm().evaluate_entry(sig(stop=99.9), b.get_account())  # tight stop -> huge risk qty
    cost = d.qty * 100.0 * (1 + lim.exec_buffer_pct) + lim.fee_allowance
    assert cost <= lim.max_position_pct * 100_000 + 1e-6      # per-position cap incl. buffer and fee


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


def test_flatten_reports_incomplete_when_broker_rejects_sells(tmp_path):
    async def src():
        return [sig(a="HOLD")]
    r = rm()
    r.manual_kill = True
    a = TradingAgent(_NoSell(), r, Ledger(str(tmp_path / "l.jsonl")), src)
    a.broker.place_order("NVDA", "BUY", 10, 100.0, 95.0)
    asyncio.run(a.run_cycle())
    ev = a.ledger.read()
    assert "NVDA" in a.broker.get_account().positions
    assert any(e.get("action") == "flatten_incomplete" and e["remaining"] == ["NVDA"] for e in ev)
    assert sum(1 for e in ev if e.get("action") == "order_rejected") == 3     # retried


def test_sim_broker_rejects_non_finite_inputs_and_updates_stop_on_add_on():
    b = _Sim()
    assert b.place_order("X", "BUY", 5, float("nan")) is None
    assert b.place_order("X", "BUY", float("inf"), 100.0) is None
    b.place_order("X", "BUY", 5, 100.0, stop_loss=90.0)
    b.place_order("X", "BUY", 5, 100.0, stop_loss=95.0)
    assert b.get_account().positions["X"].stop_loss == 95.0


# ── sixth review round ───────────────────────────────────────────────────────
def _broken_save(*_a, **_k):
    raise OSError("disk full")


def test_unwritable_risk_state_never_blocks_exits_and_blocks_entries(tmp_path):
    r = rm()
    r.save = _broken_save                 # state file cannot be written

    async def stop_out():
        return [sig(p=90.0, a="HOLD")]
    a = TradingAgent(_Sim(), r, Ledger(str(tmp_path / "l.jsonl")), stop_out,
                     state_path=str(tmp_path / "risk.json"))
    a.broker.place_order("NVDA", "BUY", 10, 100.0, 95.0)
    asyncio.run(a.run_cycle())
    assert "NVDA" not in a.broker.get_account().positions        # the stop still fired
    assert a.state_ok is False
    assert any(e.get("action") == "state_persist_failed" for e in a.ledger.read())

    async def buy():
        return [sig()]
    a.source = buy
    asyncio.run(a.run_cycle())                                    # next cycle: entries fail closed
    assert "NVDA" not in a.broker.get_account().positions
    assert any(e.get("action") == "entries_blocked" for e in a.ledger.read())


def test_kill_switch_flatten_survives_unwritable_state(tmp_path):
    r = rm()
    r.manual_kill = True
    r.save = _broken_save

    async def src():
        return [sig(a="HOLD")]
    a = TradingAgent(_Sim(), r, Ledger(str(tmp_path / "l.jsonl")), src,
                     state_path=str(tmp_path / "risk.json"))
    a.broker.place_order("NVDA", "BUY", 10, 100.0, 95.0)
    asyncio.run(a.run_cycle())
    assert not a.broker.get_account().positions


def test_reconcile_does_not_write_when_nothing_changed(tmp_path):
    r = rm()
    calls = []
    r.save = lambda *_a, **_k: calls.append(1)

    async def src():
        return [sig(a="HOLD")]
    a = TradingAgent(_Sim(), r, Ledger(str(tmp_path / "l.jsonl")), src,
                     state_path=str(tmp_path / "risk.json"))
    a._reconcile(a.broker.get_account())
    assert calls == []                      # nothing orphaned -> no write


def test_multi_run_sim_report_does_not_chain_equity_across_runs():
    from app.agent.report import summarise
    ev = []
    for run, (start, end) in {"r1": (100_000, 101_000), "r2": (100_000, 100_500)}.items():
        for v in (start, end):
            ev.append({"event": "equity", "run_id": run, "broker": "sim", "equity": v})
    s = summarise(ev)
    assert s["max_drawdown_pct"] == 0                      # the reset between runs is not a loss
    assert s["return_pct"] == pytest.approx((1.01 * 1.005 - 1) * 100)
    assert "2 simulator runs" in s["equity_note"]


def test_moomoo_multi_run_report_is_one_continuous_curve():
    from app.agent.report import summarise
    ev = [{"event": "equity", "run_id": r, "broker": "moomoo", "equity": v}
          for r, v in (("a", 100_000), ("a", 105_000), ("b", 99_750), ("b", 103_000))]
    s = summarise(ev)
    assert s["max_drawdown_pct"] == pytest.approx(5.0)     # 105k peak -> 99.75k across runs
    assert s["equity_note"] is None


# ── seventh review round ─────────────────────────────────────────────────────
def test_restart_after_failed_save_blocks_entries_until_acknowledged(tmp_path):
    path = str(tmp_path / "l.jsonl")
    state = str(tmp_path / "risk.json")
    r1 = rm()
    r1.save = _broken_save

    async def stop_out():
        return [sig(p=90.0, a="HOLD")]
    a1 = TradingAgent(_Sim(), r1, Ledger(path, broker="moomoo"), stop_out, state_path=state)
    a1.broker.place_order("NVDA", "BUY", 10, 100.0, 95.0)
    asyncio.run(a1.run_cycle())                 # sells, but the loss could not be saved

    async def buy():
        return [sig()]
    # new process: fresh agent, writable state, but the earlier failure is unresolved
    a2 = TradingAgent(_Sim(), rm(), Ledger(path, broker="moomoo"), buy, state_path=state)
    assert a2.unresolved_failure
    asyncio.run(a2.run_cycle())
    assert "NVDA" not in a2.broker.get_account().positions
    assert any(e.get("action") == "entries_blocked" and "--ack-state-failure" in e["reason"]
               for e in a2.ledger.read())

    Ledger(path, broker="moomoo").write("risk_event", action="state_failure_acknowledged")
    a3 = TradingAgent(_Sim(), rm(), Ledger(path, broker="moomoo"), buy, state_path=state)
    assert not a3.unresolved_failure
    asyncio.run(a3.run_cycle())
    assert "NVDA" in a3.broker.get_account().positions        # trading resumes after the ack


def test_unwritable_state_is_detected_before_the_first_order(tmp_path):
    r = rm()
    r.save = _broken_save

    async def buy():
        return [sig()]
    a = TradingAgent(_Sim(), r, Ledger(str(tmp_path / "l.jsonl")), buy,
                     state_path=str(tmp_path / "risk.json"))
    asyncio.run(a.run_cycle())                  # first cycle: probe fails -> no entry at all
    assert "NVDA" not in a.broker.get_account().positions
    assert any(e.get("action") == "entries_blocked" for e in a.ledger.read())


def test_multi_run_sim_report_end_equity_matches_return():
    from app.agent.report import summarise
    ev = []
    for run, (start, end) in {"r1": (100_000, 101_000), "r2": (100_000, 100_500)}.items():
        for v in (start, end):
            ev.append({"event": "equity", "run_id": run, "broker": "sim", "equity": v})
    s = summarise(ev)
    assert s["end_equity"] == pytest.approx(s["start_equity"] * (1 + s["return_pct"] / 100))
    assert "100,500.00" in s["equity_note"]                # the last run's real balance is disclosed


# ── eighth review round ──────────────────────────────────────────────────────
def test_damaged_ledger_line_does_not_stop_exits_and_holds_entries(tmp_path):
    path = tmp_path / "l.jsonl"
    path.write_text('{"event": "equity", "broker": "moomoo"}\n{"event": "fill", "bro')   # truncated
    led = Ledger(str(path), broker="moomoo")
    assert led.unresolved_state_failure("moomoo")            # damaged line = unknown = hold entries

    async def stop_out():
        return [sig(p=90.0, a="HOLD")]
    a = TradingAgent(_Sim(), rm(), led, stop_out, state_path=str(tmp_path / "risk.json"))
    a.broker.place_order("NVDA", "BUY", 10, 100.0, 95.0)
    asyncio.run(a.run_cycle())                               # constructing and running still work
    assert "NVDA" not in a.broker.get_account().positions    # the stop-loss exit still ran


def test_acknowledgement_clears_a_damaged_ledger_gate(tmp_path):
    path = tmp_path / "l.jsonl"
    path.write_text('{"event": "x"}\nnot json at all\n')
    led = Ledger(str(path), broker="moomoo")
    assert led.unresolved_state_failure("moomoo")
    led.write("risk_event", action="state_failure_acknowledged")
    assert not Ledger(str(path), broker="moomoo").unresolved_state_failure("moomoo")


def test_write_after_truncated_line_is_not_merged_into_it(tmp_path):
    path = tmp_path / "l.jsonl"
    path.write_text('{"event": "fill", "bro')                 # interrupted append, no newline
    led = Ledger(str(path))
    led.write("equity", equity=1.0)
    assert [e["event"] for e in led.read()] == ["equity"]    # the new record survives


def test_unreadable_risk_state_is_never_overwritten_and_holds_entries(tmp_path):
    state = tmp_path / "risk.json"
    state.write_text("{corrupt")

    async def buy():
        return [sig()]
    a = TradingAgent(_Sim(), rm(), Ledger(str(tmp_path / "l.jsonl")), buy,
                     state_path=str(state), state_unreadable=True)
    asyncio.run(a.run_cycle())
    assert state.read_text() == "{corrupt"                   # left for a human to repair
    assert "NVDA" not in a.broker.get_account().positions
    assert any("unreadable" in e.get("reason", "") for e in a.ledger.read())


def test_sim_report_tolerates_a_run_without_equity_marks():
    from app.agent.report import summarise, to_markdown
    ev = [{"event": "equity", "run_id": "r1", "broker": "sim", "equity": 100_000},
          {"event": "equity", "run_id": "r1", "broker": "sim", "equity": 101_000},
          {"event": "signal", "run_id": "r2", "broker": "sim"}]          # r2 stopped before a mark
    s = summarise(ev)
    assert s["end_equity"] == pytest.approx(101_000)
    assert "Trading agent report" in to_markdown(s)
    only_signals = summarise([{"event": "signal", "run_id": "a", "broker": "sim"},
                              {"event": "signal", "run_id": "b", "broker": "sim"}])
    assert only_signals["end_equity"] is None


# ── ninth review round ───────────────────────────────────────────────────────
@pytest.mark.parametrize("bad", [
    '{"peak_equity": null, "day_start_equity": 1}',          # wrong type
    '{"peak_equity": 1, "day_start_equity": 1, "closed_pnls": 5}',
    '{"peak_equity": 1, "day_start_equity": 1, "invalidated": 7}',
    '[1, 2, 3]',                                             # valid JSON, wrong shape
    '{"peak_equity": 1}',                                    # missing field
])
def test_malformed_risk_state_is_rejected_without_partial_apply(tmp_path, bad):
    p = tmp_path / "risk.json"
    p.write_text(bad)
    r = rm()
    before = (r.peak_equity, r.day_start_equity, list(r.closed_pnls))
    assert r.load(str(p)) is False                           # never raises
    assert (r.peak_equity, r.day_start_equity, list(r.closed_pnls)) == before


def test_non_object_ledger_lines_count_as_damage_and_are_skipped(tmp_path):
    path = tmp_path / "l.jsonl"
    path.write_text('[]\n5\n"x"\n{"event": "equity", "broker": "moomoo", "equity": 1.0}\n')
    led = Ledger(str(path), broker="moomoo")
    assert [e["event"] for e in led.read()] == ["equity"]    # reports skip the non-objects
    assert led.unresolved_state_failure("moomoo")            # and the startup check does not crash
    from app.agent.report import summarise
    assert summarise(led.read())["end_equity"] == 1.0


def test_broker_is_closed_even_when_the_acknowledgement_is_refused(tmp_path, monkeypatch):
    import argparse
    import sys
    import types

    closed = []

    class FakeBroker(_Sim):
        def __init__(self, *a, **k):
            super().__init__()

        def close(self):
            closed.append(1)

    monkeypatch.setitem(sys.modules, "app.agent.moomoo_broker",
                        types.SimpleNamespace(MoomooSimBroker=FakeBroker))
    monkeypatch.setitem(sys.modules, "app.core.config", types.SimpleNamespace(
        get_settings=lambda: types.SimpleNamespace(moomoo_host="h", moomoo_port=1)))
    state = tmp_path / "risk.json"
    state.write_text("{corrupt")
    args = argparse.Namespace(tickers="NVDA", broker="moomoo", market="US", cycles=1, interval=0,
                              ledger=str(tmp_path / "l.jsonl"), risk_state=str(state),
                              ack_state_failure=True)
    from app.agent.loop import _main
    with pytest.raises(SystemExit):
        asyncio.run(_main(args))
    assert closed == [1]                                     # no leaked trade context
    assert not any(e.get("action") == "state_failure_acknowledged"
                   for e in Ledger(str(tmp_path / "l.jsonl")).read())


# ── tenth review round ───────────────────────────────────────────────────────
@pytest.mark.parametrize("bad", [
    '{"peak_equity": NaN, "day_start_equity": 1}',
    '{"peak_equity": Infinity, "day_start_equity": 1}',
    '{"peak_equity": 1, "day_start_equity": -5}',
    '{"peak_equity": -1, "day_start_equity": 1}',
    '{"peak_equity": 1, "day_start_equity": 1, "closed_pnls": [NaN]}',
    '{"peak_equity": 1, "day_start_equity": 1, "open_trade_pnl": {"X": Infinity}}',
])
def test_non_finite_or_negative_risk_state_is_rejected(tmp_path, bad):
    p = tmp_path / "risk.json"
    p.write_text(bad)
    assert rm().load(str(p)) is False


def test_valid_initial_state_with_zero_peak_still_loads(tmp_path):
    p = tmp_path / "risk.json"
    p.write_text('{"peak_equity": 0, "day": null, "day_start_equity": 0, "closed_pnls": [], '
                 '"invalidated": null, "open_trade_pnl": {}}')
    assert rm().load(str(p)) is True


def test_non_finite_account_equity_holds_entries_instead_of_disabling_protection():
    r = rm()
    r.mark(float("nan"), NOW)                     # bad broker read
    d = r.evaluate_entry(sig(), SimBroker().get_account())
    assert not d.approved and "equity" in d.reason
    assert not r.should_flatten()                 # exits and stops are not blocked by it
    r.mark(100_000, NOW)                          # a good read clears the hold
    assert r.evaluate_entry(sig(), SimBroker().get_account()).approved


# ── unified model: the agent never opens positions on the fallback signal ───
def test_rule_based_fallback_signal_cannot_open_a_position():
    fallback = TradeSignal("NVDA", "BUY", 0.9, 100.0, 95.0, "rule_based")
    d = rm().evaluate_entry(fallback, SimBroker().get_account())
    assert not d.approved and "rule-based" in d.reason
    trained = TradeSignal("NVDA", "BUY", 0.9, 100.0, 95.0, "xgb_binary")
    assert rm().evaluate_entry(trained, SimBroker().get_account()).approved
    unknown = TradeSignal("NVDA", "BUY", 0.9, 100.0, 95.0, None)
    assert rm().evaluate_entry(unknown, SimBroker().get_account()).approved   # source not reported


def test_gate_can_be_relaxed_explicitly():
    lim = RiskLimits(kill_switch_path="/nonexistent/KS", require_model_signal=False)
    r = RiskManager(lim)
    r.mark(100_000, NOW)
    fallback = TradeSignal("NVDA", "BUY", 0.9, 100.0, 95.0, "rule_based")
    assert r.evaluate_entry(fallback, SimBroker().get_account()).approved
