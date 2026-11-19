from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import portfolio
from app.schemas.risk import KillSwitchState, OrderIntent, OrderSide, PortfolioSnapshot, RiskLimits
from app.services import decision_ledger, paper_broker, portfolio_history
from app.services.risk_gate import evaluate_order


def _client(monkeypatch, tmp_path):
    cfg = SimpleNamespace(
        demo_mode=True,
        decision_ledger_jsonl=str(tmp_path / "ledger.jsonl"),
        portfolio_history_jsonl=str(tmp_path / "history.jsonl"),
    )
    monkeypatch.setattr(paper_broker, "get_settings", lambda: cfg)
    paper_broker.reset_demo()
    monkeypatch.setattr(decision_ledger, "get_settings", lambda: cfg)
    monkeypatch.setattr(decision_ledger, "get_ch_client", lambda: None)
    monkeypatch.setattr(portfolio_history, "get_settings", lambda: cfg)
    monkeypatch.setattr(portfolio_history, "get_ch_client", lambda: None)
    monkeypatch.setattr(portfolio, "settings", SimpleNamespace(demo_mode=True))

    state = KillSwitchState()

    async def fake_get_kill_switch():
        return state

    monkeypatch.setattr(portfolio, "get_kill_switch", fake_get_kill_switch)

    app = FastAPI()
    app.include_router(portfolio.router, prefix="/api")
    return TestClient(app)


def _intent(**overrides):
    base = dict(
        ticker="AAPL",
        side=OrderSide.BUY,
        quantity=10,
        price=100.0,
        dry_run=False,
        idempotency_key="order-1",
        strategy_id="test",
    )
    base.update(overrides)
    return OrderIntent(**base)


def _decision(intent, kill=False):
    return evaluate_order(
        "decision-1",
        intent,
        PortfolioSnapshot(account_id="DEMO-PAPER", equity=100_000.0, cash=100_000.0),
        RiskLimits(),
        KillSwitchState(enabled=kill, reason="test"),
    )


def test_summary_records_snapshot_and_exposes_pnl(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    intent = _intent()
    paper_broker.execute_order(intent)
    decision_ledger.record_decision(_decision(intent), "agent")

    response = client.get("/api/portfolio/summary")
    assert response.status_code == 200
    payload = response.json()
    summary = payload["summary"]

    assert summary["equity"] == 100_000.0
    assert summary["cash"] == 99_000.0
    assert summary["market_value"] == 1_000.0
    assert summary["position_count"] == 1
    assert summary["gross_exposure_pct"] == 1.0
    assert summary["total_pnl"] == 0.0
    assert summary["snapshot_storage"] == "jsonl"
    assert payload["positions"][0]["allocation_pct"] == 1.0
    assert payload["ledger"]["decisions"] == 1
    assert payload["ledger"]["approved"] == 1

    curve = client.get("/api/portfolio/equity-curve").json()
    assert curve["count"] == 1
    assert curve["points"][0]["equity"] == 100_000.0
    assert curve["points"][0]["kill_switch_active"] is False

    client.get("/api/portfolio/summary")
    assert client.get("/api/portfolio/equity-curve").json()["count"] == 2


def test_rejected_list_only_returns_rejections(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    intent = _intent()
    decision_ledger.record_decision(_decision(intent, kill=True), "risk")

    response = client.get("/api/portfolio/rejected")
    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 1
    rejection = payload["rejections"][0]
    assert rejection["status"] == "rejected"
    assert rejection["ticker"] == "AAPL"
    assert "KILL_SWITCH_ACTIVE" in rejection["reason_codes"]
