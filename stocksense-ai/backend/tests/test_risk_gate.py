from app.schemas.risk import (
    KillSwitchState,
    OrderIntent,
    OrderSide,
    PortfolioPosition,
    PortfolioSnapshot,
    RiskLimits,
)
from app.services.risk_gate import evaluate_order


def _portfolio(**overrides):
    base = dict(
        account_id="TEST",
        equity=100_000.0,
        cash=100_000.0,
        day_pnl=0.0,
        peak_equity=100_000.0,
        positions=[],
    )
    base.update(overrides)
    return PortfolioSnapshot(**base)


def _intent(**overrides):
    base = dict(ticker="AAPL", side=OrderSide.BUY, quantity=10, price=100.0)
    base.update(overrides)
    return OrderIntent(**base)


def _codes(decision):
    return set(decision.reason_codes)


def test_approves_small_buy():
    decision = evaluate_order("d1", _intent(), _portfolio(), RiskLimits())
    assert decision.approved
    assert decision.notional == 1000.0
    assert decision.projected_position_pct == 0.01


def test_kill_switch_blocks_buy_but_allows_flattening_sell():
    kill = KillSwitchState(enabled=True, reason="manual")
    buy = evaluate_order("d1", _intent(), _portfolio(), RiskLimits(), kill)
    assert not buy.approved
    assert "KILL_SWITCH_ACTIVE" in _codes(buy)

    held = _portfolio(
        cash=99_000.0,
        positions=[PortfolioPosition(ticker="AAPL", quantity=10, market_value=1_000.0)],
    )
    sell = evaluate_order("d2", _intent(side=OrderSide.SELL, quantity=5), held, RiskLimits(), kill)
    assert sell.approved


def test_position_limit_blocks_oversized_buy():
    decision = evaluate_order(
        "d1", _intent(quantity=100), _portfolio(), RiskLimits(max_position_pct=0.05)
    )
    assert not decision.approved
    assert "POSITION_LIMIT_EXCEEDED" in _codes(decision)


def test_order_notional_limit():
    decision = evaluate_order(
        "d1", _intent(quantity=11), _portfolio(), RiskLimits(max_order_notional=1_000.0)
    )
    assert not decision.approved
    assert "ORDER_NOTIONAL_EXCEEDED" in _codes(decision)


def test_daily_loss_limit_blocks_new_buy():
    decision = evaluate_order(
        "d1", _intent(), _portfolio(day_pnl=-4_000.0), RiskLimits(max_daily_loss_pct=0.03)
    )
    assert not decision.approved
    assert "DAILY_LOSS_LIMIT_BREACHED" in _codes(decision)


def test_drawdown_limit_blocks_new_buy():
    decision = evaluate_order(
        "d1",
        _intent(quantity=1),
        _portfolio(equity=80_000.0, cash=80_000.0, peak_equity=100_000.0),
        RiskLimits(max_drawdown_pct=0.15),
    )
    assert not decision.approved
    assert "MAX_DRAWDOWN_BREACHED" in _codes(decision)


def test_cash_buffer_limit():
    decision = evaluate_order(
        "d1",
        _intent(quantity=5),
        _portfolio(cash=10_000.0),
        RiskLimits(min_cash_buffer_pct=0.10),
    )
    assert not decision.approved
    assert "CASH_BUFFER_BREACHED" in _codes(decision)


def test_sell_more_than_held_is_rejected():
    decision = evaluate_order(
        "d1",
        _intent(side=OrderSide.SELL, quantity=5),
        _portfolio(),
        RiskLimits(),
    )
    assert not decision.approved
    assert "POSITION_NOT_HELD" in _codes(decision)


def test_ticker_is_normalised():
    assert _intent(ticker=" aapl ").ticker == "AAPL"
