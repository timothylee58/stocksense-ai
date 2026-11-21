"""Round 3 proof — acceptance tests A1-A16.

Each test maps to one row of docs/PROOF.md.  The tests exercise the paper
sandbox (demo broker / fake SIMULATE SDK) and never reach a live account.
"""
import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.agents import policy
from app.agents.registry import AGENT_IDS
from app.api.routes import trading
from app.data import moomoo_trade_client as trade_client
from app.ml import predictor
from app.schemas.risk import (
    KillSwitchState,
    OrderIntent,
    OrderSide,
    OrderType,
    PortfolioPosition,
    PortfolioSnapshot,
    RiskLimits,
)
from app.services import decision_ledger, paper_broker
from app.services.risk_gate import evaluate_order

NOW = datetime.now(timezone.utc)


def _limits(**overrides) -> RiskLimits:
    base = dict(
        max_position_pct=0.25,
        max_gross_exposure_pct=0.90,
        max_order_notional=50_000.0,
        max_daily_loss_pct=0.03,
        max_drawdown_pct=0.15,
        min_cash_buffer_pct=0.10,
        require_limit_orders=True,
        max_quote_age_s=60.0,
        us_only=True,
    )
    base.update(overrides)
    return RiskLimits(**base)


def _intent(**overrides) -> OrderIntent:
    base = dict(
        ticker="AAPL",
        side=OrderSide.BUY,
        quantity=10,
        price=100.0,
        dry_run=False,
        idempotency_key="dec-1",
        strategy_id="acceptance",
        quote_ts=NOW,
    )
    base.update(overrides)
    return OrderIntent(**base)


def _portfolio(**overrides) -> PortfolioSnapshot:
    base = dict(
        account_id="SIM-1193367",
        equity=100_000.0,
        cash=100_000.0,
        day_pnl=0.0,
        peak_equity=100_000.0,
        positions=[],
    )
    base.update(overrides)
    return PortfolioSnapshot(**base)


def _frame(n: int = 120) -> pd.DataFrame:
    idx = pd.date_range("2026-01-01", periods=n, freq="B")
    close = np.linspace(100.0, 120.0, n)
    return pd.DataFrame(
        {
            "Close": close,
            "rsi": np.full(n, 55.0),
            "macd": np.full(n, 0.5),
            "macd_signal": np.full(n, 0.4),
            "bb_lower": close * 0.97,
            "bb_upper": close * 1.03,
            "sma_20": close * 0.99,
            "sma_50": close * 0.98,
        },
        index=idx,
    )


def _guard_settings(**overrides) -> SimpleNamespace:
    base = dict(
        moomoo_trade_enabled=True,
        moomoo_trd_env="SIMULATE",
        moomoo_paper_account_id="1193367",
        moomoo_trd_market="US",
        moomoo_security_firm="FUTUSECURITIES",
        moomoo_host="127.0.0.1",
        moomoo_port=11111,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


class _FakeCtx:
    def __init__(self, acc_id: str = "1193367"):
        self.placed: list[dict] = []
        self.accounts = pd.DataFrame(
            [{"acc_id": acc_id, "trd_env": "SIMULATE", "currency": "USD",
              "total_assets": 100_000.0, "cash": 100_000.0, "market_val": 0.0}]
        )

    def accinfo_query(self, **_kwargs):
        return 0, self.accounts

    def place_order(self, **kwargs):
        self.placed.append(kwargs)
        return 0, pd.DataFrame([{"order_id": "3116213"}])


class _FakeSDK:
    RET_OK = 0
    TrdEnv = SimpleNamespace(SIMULATE="SIMULATE")
    TrdSide = SimpleNamespace(BUY="BUY", SELL="SELL")
    OrderType = SimpleNamespace(MARKET="MARKET", NORMAL="NORMAL")


def _order_payload(**overrides) -> dict:
    base = {
        "ticker": "AAPL",
        "side": "BUY",
        "quantity": 10,
        "price": 100.0,
        "dry_run": False,
        "idempotency_key": "acceptance-1",
        "strategy_id": "acceptance",
        "quote_ts": datetime.now(timezone.utc).isoformat(),
    }
    base.update(overrides)
    return base


def _route_client(monkeypatch, tmp_path, *, ledger_store: str = "jsonl") -> TestClient:
    monkeypatch.setattr(paper_broker, "get_settings", lambda: SimpleNamespace(demo_mode=True))
    paper_broker.reset_demo()
    monkeypatch.setattr(
        decision_ledger,
        "get_settings",
        lambda: SimpleNamespace(decision_ledger_jsonl=str(tmp_path / "ledger.jsonl")),
    )
    monkeypatch.setattr(decision_ledger, "get_ch_client", lambda: None)
    monkeypatch.setattr(trading, "settings", SimpleNamespace(admin_api_token="test", secret_key="test"))

    async def fake_get_kill_switch():
        return KillSwitchState()

    used: set[str] = set()

    async def fake_claim(key: str) -> bool:
        if key in used:
            return False
        used.add(key)
        return True

    monkeypatch.setattr(trading, "get_kill_switch", fake_get_kill_switch)
    monkeypatch.setattr(trading, "_claim_idempotency", fake_claim)
    if ledger_store == "unavailable":
        monkeypatch.setattr(decision_ledger, "record_decision", lambda decision, actor: "unavailable")

    app = FastAPI()
    app.include_router(trading.router, prefix="/api")
    return TestClient(app)


# A1 ---------------------------------------------------------------------
def test_a01_paper_only_guard(monkeypatch):
    monkeypatch.setattr(trade_client, "get_settings", lambda: _guard_settings(moomoo_trd_env="REAL"))
    with pytest.raises(trade_client.LiveTradingForbidden):
        trade_client.verify_paper_guard()

    monkeypatch.setattr(trade_client, "get_settings", lambda: _guard_settings(moomoo_trade_enabled=False))
    with pytest.raises(trade_client.TradingDisabled):
        trade_client.verify_paper_guard()

    monkeypatch.setattr(trade_client, "get_settings", lambda: _guard_settings(moomoo_paper_account_id=""))
    with pytest.raises(trade_client.PaperAccountIdRequired):
        trade_client.verify_paper_guard()


# A2 ---------------------------------------------------------------------
def test_a02_live_tools_are_excluded_for_every_agent():
    for agent_id in AGENT_IDS:
        for tool in policy.LIVE_DENY_EXAMPLES:
            verdict = policy.check_tool(agent_id, tool)
            assert not verdict.allowed and verdict.code == policy.LIVE_TOOL_DENIED


# A3 ---------------------------------------------------------------------
def test_a03_limit_orders_only():
    assert OrderIntent(ticker="AAPL", side="BUY", quantity=1, price=1.0).order_type is OrderType.LIMIT

    blocked = evaluate_order("a3a", _intent(order_type=OrderType.MARKET), _portfolio(), _limits())
    assert "MARKET_ORDER_FORBIDDEN" in blocked.reason_codes

    allowed = evaluate_order("a3b", _intent(order_type=OrderType.LIMIT), _portfolio(), _limits())
    assert allowed.approved


# A4 ---------------------------------------------------------------------
def test_a04_quote_freshness():
    missing = evaluate_order("a4a", _intent(quote_ts=None), _portfolio(), _limits())
    assert "QUOTE_TIMESTAMP_MISSING" in missing.reason_codes

    stale_ts = datetime.now(timezone.utc) - timedelta(seconds=120)
    stale = evaluate_order("a4b", _intent(quote_ts=stale_ts), _portfolio(), _limits())
    assert "STALE_QUOTE" in stale.reason_codes

    fresh_ts = datetime.now(timezone.utc) - timedelta(seconds=5)
    fresh = evaluate_order("a4c", _intent(quote_ts=fresh_ts), _portfolio(), _limits())
    assert fresh.approved

    held = _portfolio(positions=[PortfolioPosition(ticker="AAPL", quantity=10, market_value=1_000.0)])
    sell = evaluate_order("a4d", _intent(side=OrderSide.SELL, quote_ts=None), held, _limits())
    assert sell.approved


# A5 ---------------------------------------------------------------------
@pytest.mark.parametrize("ticker", ["MY.1155", "1155.KL", "HK.00700", "D05.SI", "SH.600519"])
def test_a05_us_only_universe(ticker):
    decision = evaluate_order("a5", _intent(ticker=ticker), _portfolio(), _limits())
    assert "UNIVERSE_NOT_TRADABLE" in decision.reason_codes


# A6 ---------------------------------------------------------------------
def test_a06_risk_limits():
    notional = evaluate_order(
        "a6a", _intent(quantity=600, price=100.0), _portfolio(), _limits(max_order_notional=10_000.0)
    )
    assert "ORDER_NOTIONAL_EXCEEDED" in notional.reason_codes

    held = _portfolio(positions=[PortfolioPosition(ticker="AAPL", quantity=250, market_value=25_000.0)])
    position = evaluate_order("a6b", _intent(quantity=5, price=100.0), held, _limits(max_position_pct=0.25))
    assert "POSITION_LIMIT_EXCEEDED" in position.reason_codes

    gross_book = _portfolio(positions=[PortfolioPosition(ticker="NVDA", quantity=100, market_value=20_000.0)])
    gross = evaluate_order(
        "a6c", _intent(quantity=150, price=100.0), gross_book, _limits(max_gross_exposure_pct=0.30)
    )
    assert "GROSS_EXPOSURE_EXCEEDED" in gross.reason_codes

    buffer = evaluate_order("a6d", _intent(), _portfolio(cash=10_500.0), _limits(min_cash_buffer_pct=0.10))
    assert "CASH_BUFFER_BREACHED" in buffer.reason_codes

    cash = evaluate_order("a6e", _intent(), _portfolio(cash=500.0), _limits(min_cash_buffer_pct=0.0))
    assert "INSUFFICIENT_CASH" in cash.reason_codes

    daily = evaluate_order("a6f", _intent(), _portfolio(day_pnl=-1_600.0), _limits(max_daily_loss_pct=0.015))
    assert "DAILY_LOSS_LIMIT_BREACHED" in daily.reason_codes

    drawdown = evaluate_order(
        "a6g",
        _intent(quantity=1, price=100.0),
        _portfolio(equity=80_000.0, cash=80_000.0, peak_equity=100_000.0),
        _limits(),
    )
    assert "MAX_DRAWDOWN_BREACHED" in drawdown.reason_codes


# A7 ---------------------------------------------------------------------
def test_a07_kill_switch_blocks_buys_not_sells():
    active = KillSwitchState(enabled=True, reason="acceptance", actor="test")
    buy = evaluate_order("a7a", _intent(), _portfolio(), _limits(), kill_switch=active)
    assert "KILL_SWITCH_ACTIVE" in buy.reason_codes

    held = _portfolio(positions=[PortfolioPosition(ticker="AAPL", quantity=10, market_value=1_000.0)])
    sell = evaluate_order(
        "a7b", _intent(side=OrderSide.SELL), held, _limits(), kill_switch=active
    )
    assert sell.approved


# A8 ---------------------------------------------------------------------
def test_a08_ledger_unavailable_fails_closed(monkeypatch, tmp_path):
    client = _route_client(monkeypatch, tmp_path, ledger_store="unavailable")
    payload = client.post("/api/trading/orders", json=_order_payload(idempotency_key="a8")).json()

    assert payload["decision"]["approved"] is True
    assert payload["execution"]["status"] == "failed"
    assert "fail-closed" in payload["execution"]["message"]
    assert not (tmp_path / "ledger.jsonl").exists()


# A9 ---------------------------------------------------------------------
def test_a09_duplicate_order_is_blocked(monkeypatch, tmp_path):
    client = _route_client(monkeypatch, tmp_path)
    body = _order_payload(idempotency_key="a9")

    first = client.post("/api/trading/orders", json=body).json()
    assert first["execution"]["status"] == "filled"

    second = client.post("/api/trading/orders", json=body).json()
    assert second["execution"]["status"] == "duplicate_blocked"


# A10 --------------------------------------------------------------------
def test_a10_broker_remark_stamps_decision_id(monkeypatch):
    ctx = _FakeCtx()
    monkeypatch.setattr(trade_client, "_sdk", lambda: _FakeSDK)
    monkeypatch.setattr(trade_client, "_get_ctx", lambda: ctx)
    monkeypatch.setattr(trade_client, "get_settings", lambda: _guard_settings())

    execution = trade_client.place_paper_order(_intent(idempotency_key="dec-42"))
    assert execution.status == "submitted"
    assert execution.order_id == "3116213"

    sent = ctx.placed[-1]
    assert sent["remark"] == "stocksense:dec-42"
    assert sent["trd_env"] == "SIMULATE"
    assert sent["acc_id"] == 1193367  # resolved from settings, never from the order payload
    assert sent["order_type"] == "NORMAL"
    assert sent["code"] == "US.AAPL"


# A11 --------------------------------------------------------------------
def test_a11_account_resolved_at_runtime_and_mismatch_refused(monkeypatch):
    intent = OrderIntent(
        ticker="AAPL", side="BUY", quantity=1, price=1.0,
        account_id="LIVE-999",  # type: ignore[call-arg]
    )
    assert "account_id" not in intent.model_dump()

    ctx = _FakeCtx(acc_id="999999")
    monkeypatch.setattr(trade_client, "_sdk", lambda: _FakeSDK)
    monkeypatch.setattr(trade_client, "_get_ctx", lambda: ctx)
    monkeypatch.setattr(trade_client, "get_settings", lambda: _guard_settings())
    with pytest.raises(trade_client.PaperAccountMismatch):
        trade_client.verify_paper_guard()


# A12 --------------------------------------------------------------------
def test_a12_shorting_disabled():
    held = _portfolio(positions=[PortfolioPosition(ticker="AAPL", quantity=2, market_value=200.0)])
    sell = evaluate_order("a12a", _intent(side=OrderSide.SELL, quantity=5), held, _limits())
    assert "POSITION_NOT_HELD" in sell.reason_codes

    with pytest.raises(ValidationError):
        OrderIntent(ticker="AAPL", side="BUY", quantity=-1, price=1.0)
    with pytest.raises(ValidationError):
        OrderIntent(ticker="AAPL", side="SHORT", quantity=1, price=1.0)  # type: ignore[arg-type]


# A13 --------------------------------------------------------------------
def test_a13_confidence_bounded_and_no_logits(monkeypatch):
    async def fake_fetch(_ticker):
        return _frame()

    async def fake_get(_key):
        return None

    async def fake_set(_key, _value, _ttl):
        return None

    monkeypatch.setattr(predictor, "fetch_stock_data", fake_fetch)
    monkeypatch.setattr(predictor, "cache_get", fake_get)
    monkeypatch.setattr(predictor, "cache_set", fake_set)
    monkeypatch.setattr(predictor, "get_stock_info", lambda _t: {"name": "Apple", "sector": "Technology"})
    monkeypatch.setattr(predictor, "predict_lstm", lambda df, ticker: ([115.0] * 30, 0.9))
    monkeypatch.setattr(predictor, "predict_xgb", lambda df, ticker: ("BUY", 0.9))

    payload = asyncio.run(predictor.run_prediction("AAPL"))
    assert 0.0 <= payload["confidence"] <= 1.0
    assert "logits" not in payload


# A14 --------------------------------------------------------------------
def test_a14_no_feature_vectors_exposed(monkeypatch, tmp_path):
    intent = _intent(feature_snapshot={"rsi": 55.2})  # type: ignore[call-arg]
    assert "feature_snapshot" not in intent.model_dump()

    monkeypatch.setattr(
        decision_ledger,
        "get_settings",
        lambda: SimpleNamespace(decision_ledger_jsonl=str(tmp_path / "ledger.jsonl")),
    )
    monkeypatch.setattr(decision_ledger, "get_ch_client", lambda: None)
    decision = evaluate_order("a14", _intent(), _portfolio(), _limits())
    assert decision_ledger.record_decision(decision, "test") == "jsonl"
    assert "feature_snapshot" not in (tmp_path / "ledger.jsonl").read_text(encoding="utf-8")


# A15 --------------------------------------------------------------------
def test_a15_pre_trained_artifacts_only(monkeypatch, tmp_path):
    from app.services import isolation_forest, xgboost_service

    monkeypatch.setattr(xgboost_service, "settings", SimpleNamespace(models_dir=str(tmp_path)))
    monkeypatch.setattr(isolation_forest, "settings", SimpleNamespace(models_dir=str(tmp_path)))

    def _refuse(*_args, **_kwargs):
        raise AssertionError("inference attempted to train")

    monkeypatch.setattr(xgboost_service, "train_xgboost", _refuse)
    monkeypatch.setattr(isolation_forest, "train_isolation_forest", _refuse)

    assert xgboost_service.predict_xgboost(_frame(), "AAPL") == (0.5, 0.5)
    anomalies = isolation_forest.predict_anomalies(_frame(), "AAPL")
    assert (anomalies["anomaly_score"] == 0.0).all()
    assert list(tmp_path.iterdir()) == []


# A16 --------------------------------------------------------------------
def test_a16_demo_sandbox_never_calls_broker(monkeypatch):
    monkeypatch.setattr(paper_broker, "get_settings", lambda: SimpleNamespace(demo_mode=True))

    def _refuse(_intent):
        raise AssertionError("demo sandbox must not reach the moomoo broker")

    monkeypatch.setattr(paper_broker.moomoo, "place_paper_order", _refuse)
    paper_broker.reset_demo()

    status = paper_broker.account_status()
    assert status["source"] == "demo"
    assert status["trd_env"] == "SIMULATE"

    execution = paper_broker.execute_order(_intent())
    assert execution.status == "filled"
    paper_broker.reset_demo()
