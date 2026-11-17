import pandas as pd
import pytest

pytest.importorskip("moomoo")
from app.agent.moomoo_broker import MoomooSimBroker


class FakeCtx:
    """Mimics OpenSecTradeContext for a single instantly-filled order."""

    def __init__(self, cash=100_000.0, positions=None, status="FILLED_ALL", dealt=None):
        self.cash, self.positions, self.status, self.dealt = cash, positions or [], status, dealt
        self.orders, self.cancelled, self.envs = [], [], []

    def accinfo_query(self, **kw):
        self.envs.append(kw["trd_env"])
        return 0, pd.DataFrame([{"cash": self.cash}])

    def position_list_query(self, **kw):
        self.envs.append(kw["trd_env"])
        return 0, pd.DataFrame(self.positions, columns=["code", "qty", "cost_price", "nominal_price"])

    def place_order(self, **kw):
        self.envs.append(kw["trd_env"])
        self.orders.append(kw)
        return 0, pd.DataFrame([{"order_id": "42"}])

    def order_list_query(self, **kw):
        qty = self.orders[-1]["qty"] if self.dealt is None else self.dealt
        px = self.orders[-1]["price"]
        return 0, pd.DataFrame([{"order_status": self.status, "dealt_qty": qty, "dealt_avg_price": px}])

    def modify_order(self, *a, **kw):
        self.cancelled.append(a)
        return 0, pd.DataFrame()

    def close(self):
        pass


def broker(tmp_path, ctx, **kw):
    return MoomooSimBroker(ctx=ctx, state_path=str(tmp_path / "s.json"),
                           fill_timeout=0.05, poll_interval=0.01, **kw)


def test_account_maps_positions_and_stops(tmp_path):
    ctx = FakeCtx(positions=[["US.NVDA", 10, 100.0, 105.0]])
    b = broker(tmp_path, ctx)
    b._stops["NVDA"] = 95.0
    a = b.get_account()
    assert a.cash == 100_000 and a.positions["NVDA"].stop_loss == 95.0
    assert a.equity == 100_000 + 10 * 105.0


def test_buy_places_simulate_limit_order_and_saves_stop(tmp_path):
    ctx = FakeCtx()
    b = broker(tmp_path, ctx)
    f = b.place_order("NVDA", "BUY", 10, 100.0, stop_loss=95.0)
    o = ctx.orders[0]
    assert o["code"] == "US.NVDA" and o["price"] == 100.2 and o["qty"] == 10
    assert f.qty == 10 and f.realized_pnl is None
    assert b._load_stops() == {"NVDA": 95.0}
    assert all(e == b._m.TrdEnv.SIMULATE for e in ctx.envs)


def test_sell_reports_realized_pnl_and_clears_stop(tmp_path):
    ctx = FakeCtx(positions=[["US.NVDA", 10, 100.0, 90.0]])
    b = broker(tmp_path, ctx)
    b._stops["NVDA"] = 95.0
    f = b.place_order("NVDA", "SELL", 10, 90.0)
    assert f.realized_pnl == pytest.approx((89.82 - 100.0) * 10)
    assert "NVDA" not in b._stops


def test_unfilled_order_is_cancelled_and_returns_none(tmp_path):
    ctx = FakeCtx(status="SUBMITTED", dealt=0)
    b = broker(tmp_path, ctx)
    assert b.place_order("NVDA", "BUY", 10, 100.0) is None
    assert ctx.cancelled


def test_partial_fill_returns_filled_qty(tmp_path):
    ctx = FakeCtx(status="SUBMITTED", dealt=4)
    f = broker(tmp_path, ctx).place_order("NVDA", "BUY", 10, 100.0)
    assert f.qty == 4


def test_sell_without_position_is_noop(tmp_path):
    ctx = FakeCtx()
    assert broker(tmp_path, ctx).place_order("NVDA", "SELL", 5, 100.0) is None
    assert not ctx.orders
