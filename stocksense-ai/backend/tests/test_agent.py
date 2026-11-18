import asyncio
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
