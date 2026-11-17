import asyncio
from datetime import datetime, timezone

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
    # risk: 100k*0.5%/5 = 100 sh; position cap: 100k*10%/100 = 100 sh
    assert d.approved and d.qty == 100


def test_low_confidence_rejected():
    assert not rm().evaluate_entry(sig(c=0.5), SimBroker().get_account()).approved


def test_soft_drawdown_halves_size():
    r = rm()
    r.mark(94_000, NOW.replace(day=18))  # 6% below peak, new day so daily-loss limit is not hit
    d = r.evaluate_entry(sig(), SimBroker(cash=94_000).get_account())
    assert d.approved and d.size_factor == 0.5 and d.qty == 47


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
