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
                           fill_timeout=0.05, poll_interval=0.01, cancel_timeout=0.05, **kw)


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
    assert ctx.cancelled[0][:2] == (b._m.ModifyOrderOp.CANCEL, "42")


def test_partial_fill_returns_filled_qty(tmp_path):
    ctx = FakeCtx(status="SUBMITTED", dealt=4)
    f = broker(tmp_path, ctx).place_order("NVDA", "BUY", 10, 100.0)
    assert f.qty == 4


def test_sell_without_position_is_noop(tmp_path):
    ctx = FakeCtx()
    assert broker(tmp_path, ctx).place_order("NVDA", "SELL", 5, 100.0) is None
    assert not ctx.orders


def test_fill_landing_during_cancel_is_captured(tmp_path):
    class LateFill(FakeCtx):
        def __init__(self):
            super().__init__(status="SUBMITTED", dealt=0)
            self.canceled = False

        def modify_order(self, *a, **kw):
            self.canceled = True
            self.status, self.dealt = "CANCELLED_PART", 3
            return 0, pd.DataFrame()

    ctx = LateFill()
    f = broker(tmp_path, ctx).place_order("NVDA", "BUY", 10, 100.0, stop_loss=95.0)
    assert ctx.canceled and f is not None and f.qty == 3


def test_calls_match_real_sdk_signatures(tmp_path):
    """The fake accepts anything, so check every kwarg we send exists in the real SDK."""
    import inspect

    import moomoo as m

    class Strict(FakeCtx):
        def __getattribute__(self, name):
            attr = super().__getattribute__(name)
            if name in ("accinfo_query", "position_list_query", "place_order",
                        "order_list_query", "modify_order"):
                real = inspect.signature(getattr(m.OpenSecTradeContext, name)).parameters

                def checked(*a, **kw):
                    bad = set(kw) - set(real)
                    assert not bad, f"{name} got unknown kwargs {bad}"
                    return attr(*a, **kw)
                return checked
            return attr

    ctx = Strict(status="SUBMITTED", dealt=0, positions=[["US.NVDA", 5, 100.0, 100.0]])
    b = broker(tmp_path, ctx)
    b.place_order("NVDA", "BUY", 3, 100.0, 95.0)      # exercises place/poll/cancel/query
    b.place_order("NVDA", "SELL", 5, 100.0)


def test_prefixed_ticker_is_normalised(tmp_path):
    ctx = FakeCtx(positions=[["US.NVDA", 10, 100.0, 90.0]])
    b = broker(tmp_path, ctx)
    f = b.place_order("US.NVDA", "SELL", 10, 90.0)
    assert f is not None and f.ticker == "NVDA" and ctx.orders[0]["code"] == "US.NVDA"


def test_buy_floors_to_whole_shares_and_rejects_zero(tmp_path):
    ctx = FakeCtx()
    b = broker(tmp_path, ctx)
    assert b.place_order("NVDA", "BUY", 0.6, 100.0) is None and not ctx.orders
    b.place_order("NVDA", "BUY", 2.9, 100.0)
    assert ctx.orders[0]["qty"] == 2.0


def test_fractional_position_can_be_closed(tmp_path):
    ctx = FakeCtx(positions=[["US.NVDA", 2.5, 100.0, 90.0]])
    broker(tmp_path, ctx).place_order("NVDA", "SELL", 2.5, 90.0)
    assert ctx.orders[0]["qty"] == 2.5


def test_sub_dollar_price_keeps_four_decimals(tmp_path):
    ctx = FakeCtx()
    broker(tmp_path, ctx).place_order("PENNY", "BUY", 100, 0.5)
    assert ctx.orders[0]["price"] == 0.501


def test_stops_file_written_atomically_and_corrupt_file_is_handled(tmp_path):
    ctx = FakeCtx()
    b = broker(tmp_path, ctx)
    b.place_order("NVDA", "BUY", 10, 100.0, stop_loss=95.0)
    assert not (tmp_path / "s.json.tmp").exists()
    (tmp_path / "s.json").write_text("{not json")
    assert b._load_stops() == {}
