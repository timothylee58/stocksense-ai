import math

import pytest

from app.agent.report import select, summarise
from app.agent.risk import RiskManager


def ev(event, ts="2026-11-18T10:00:00", **kw):
    return {"event": event, "ts": ts, "run_id": "r1", "broker": "sim", **kw}


def test_date_filter_is_exact_and_validated():
    events = [ev("equity", equity=1.0, ts="2026-11-18T10:00:00"), ev("equity", equity=2.0, ts="2026-11-18T11:00:00")]
    assert len(select(events, date="2026-11-18")) == 2
    with pytest.raises(ValueError):
        select(events, date="2026-11")


def test_nonfinite_equity_marks_ignored_and_no_marks_gives_none_drawdown():
    s = summarise([ev("equity", equity=float("nan")), ev("equity", equity=100.0), ev("equity", equity=90.0)])
    assert s["end_equity"] == 90.0 and math.isclose(s["max_drawdown_pct"], 10.0)
    s = summarise([ev("decision", approved=True, reason="x")])
    assert s["max_drawdown_pct"] is None


def test_mixed_brokers_refused():
    with pytest.raises(ValueError):
        summarise([ev("equity", equity=1.0), ev("equity", equity=1.0, broker="moomoo")])


def test_risk_state_requires_exact_types(tmp_path):
    import json
    good = {"peak_equity": 100.0, "day": None, "day_start_equity": 100.0,
            "closed_pnls": [], "invalidated": None, "open_trade_pnl": {}}
    p = tmp_path / "s.json"
    for bad in ({**good, "peak_equity": True}, {**good, "closed_pnls": "x"},
                {k: v for k, v in good.items() if k != "invalidated"}):
        p.write_text(json.dumps(bad))
        assert RiskManager().load(str(p)) is False
    p.write_text(json.dumps(good))
    assert RiskManager().load(str(p)) is True
