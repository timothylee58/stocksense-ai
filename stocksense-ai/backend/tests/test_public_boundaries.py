import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import agent_run, portfolio, trading
from app.agents.journal import Journal
from app.core.config import Settings
from app.schemas.risk import KillSwitchState, PortfolioSnapshot
from app.services import decision_ledger, paper_broker, portfolio_history


@pytest.fixture
def public_client(monkeypatch, tmp_path):
    settings = Settings(
        _env_file=None,
        read_only_mode=True,
        demo_mode=False,
        moomoo_enabled=False,
        moomoo_trade_enabled=False,
        clickhouse_enabled=False,
        admin_api_token="test-admin",
        decision_ledger_jsonl=str(tmp_path / "ledger.jsonl"),
        portfolio_history_jsonl=str(tmp_path / "history.jsonl"),
        agent_journal_jsonl=str(tmp_path / "journal.jsonl"),
    )
    for module in (trading, portfolio, agent_run, portfolio_history, decision_ledger):
        monkeypatch.setattr(module, "get_settings", lambda: settings)
    monkeypatch.setattr(trading, "settings", settings)
    monkeypatch.setattr(portfolio, "settings", settings)
    monkeypatch.setattr(portfolio_history, "get_ch_client", lambda: None)
    monkeypatch.setattr(decision_ledger, "get_ch_client", lambda: None)
    monkeypatch.setattr(Journal, "_mirror_clickhouse", lambda *args: None)
    journal = Journal(settings.agent_journal_jsonl)
    monkeypatch.setattr(agent_run, "Journal", lambda: journal)

    def forbidden(*args, **kwargs):
        pytest.fail("read-only request reached the broker")

    async def kill_unavailable():
        raise ConnectionError("risk store unavailable")

    monkeypatch.setattr(paper_broker, "account_status", forbidden)
    monkeypatch.setattr(paper_broker, "get_portfolio", forbidden)
    monkeypatch.setattr(paper_broker, "execute_order", forbidden)
    monkeypatch.setattr(portfolio, "get_kill_switch", kill_unavailable)
    app = FastAPI()
    for router in (trading.router, portfolio.router, agent_run.router):
        app.include_router(router, prefix="/api")
    return TestClient(app), settings, journal


def test_read_only_order_rejects_before_ledger_or_broker_access(public_client, tmp_path):
    client, _, _ = public_client
    response = client.post(
        "/api/trading/orders",
        headers={"X-Admin-Token": "test-admin"},
        json={"ticker": "AAPL", "side": "BUY", "quantity": 1, "price": 100, "dry_run": False},
    )
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "READ_ONLY_MODE"
    assert list(tmp_path.iterdir()) == []


def test_read_only_portfolio_without_snapshot_is_unavailable_not_zero(public_client, tmp_path):
    client, _, _ = public_client
    response = client.get("/api/portfolio/summary")
    assert response.status_code == 200
    payload = response.json()
    assert payload["stale"] is True
    for field in ("equity", "cash", "market_value", "day_pnl", "day_pnl_pct", "baseline_equity", "total_pnl", "total_return_pct", "position_count", "kill_switch_active"):
        assert payload["summary"][field] is None, field
    assert payload["kill_switch"]["enabled"] is None
    assert list(tmp_path.iterdir()) == []


def test_read_only_portfolio_preserves_history_baseline_without_writes(public_client, tmp_path):
    client, settings, _ = public_client
    rows = [
        {"equity": 100000, "cash": 100000, "market_value": 0, "day_pnl": 0,
         "position_count": 0, "kill_switch_active": False, "captured_at": "2026-11-18T00:00:00+00:00"},
        {"equity": 101250, "cash": 80000, "market_value": 21250, "day_pnl": 250,
         "position_count": 2, "kill_switch_active": True, "captured_at": "2026-11-19T00:00:00+00:00"},
    ]
    path = tmp_path / "history.jsonl"
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))
    original = path.read_bytes()
    payload = client.get("/api/portfolio/summary").json()
    assert payload["summary"]["equity"] == 101250
    assert payload["summary"]["baseline_equity"] == 100000
    assert payload["summary"]["total_pnl"] == 1250
    assert payload["summary"]["total_return_pct"] == 1.25
    assert payload["summary"]["captured_at"] == "2026-11-19T00:00:00+00:00"
    assert payload["kill_switch"]["enabled"] is None
    assert path.read_bytes() == original
    assert not (tmp_path / "ledger.jsonl").exists()


def test_public_journal_exposes_metadata_not_raw_payloads(public_client):
    client, _, journal = public_client
    run = {
        "run_id": "run-test", "session_date": "2026-11-19", "strategy_version": "s1.1",
        "status": "halted", "halt_reason": "private-feature-value",
        "per_name_status": [{"symbol": "AAPL", "status": "aborted", "features": {"rsi": 77}}],
        "features": {"rsi": 77},
    }
    for event_type, payload in (
        ("technical", {"symbol": "AAPL", "features": {"rsi": 77}, "arbitrary": "private-feature-value"}),
        ("audit", {"run_id": "run-test", "decisions": 1, "executions": 0, "breaks": ["private-feature-value"], "hash_chain_ok": True, "features": {"rsi": 77}}),
        ("run_finished", {"run_record": run, "status": "halted", "phase": "paper", "private": "private-feature-value"}),
    ):
        journal.append(run_id="run-test", strategy_version="s1.1", event_type=event_type, payload=payload)
    original = journal.path.read_bytes()
    response = client.get("/api/agents/runs/run-test")
    assert response.status_code == 200
    assert "features" not in response.text
    assert "private-feature-value" not in response.text
    result = response.json()
    assert result["run"]["status"] == "halted"
    assert result["run"]["per_name_status"] == [{"symbol": "AAPL", "status": "aborted"}]
    assert result["audit"]["decisions"] == 1
    assert result["audit"]["break_count"] == 1
    assert len(result["events"]) == 3
    assert result["events"][0]["event_type"] == "technical"
    assert "payload" not in result["events"][0]
    assert journal.path.read_bytes() == original
    assert journal.verify() == (True, [])
    assert client.get("/api/agents/runs").json()["runs"][0]["status"] == "halted"


def test_public_chain_verification_does_not_echo_corrupt_record(public_client):
    client, _, journal = public_client
    journal.path.write_text('{"features": "private-feature-value"\n')
    response = client.get("/api/agents/journal/verify")
    assert response.status_code == 200
    assert response.json()["hash_chain_ok"] is False
    assert response.json()["breaks"]
    assert "private-feature-value" not in response.text
    assert "features" not in response.text


def test_read_only_summary_does_not_capture_even_available_broker(public_client, monkeypatch, tmp_path):
    client, _, _ = public_client
    monkeypatch.setattr(paper_broker, "account_status", lambda: {"equity": 100000, "cash": 100000})
    monkeypatch.setattr(paper_broker, "get_portfolio", lambda: PortfolioSnapshot(equity=100000, cash=100000))

    async def kill():
        return KillSwitchState()

    monkeypatch.setattr(portfolio, "get_kill_switch", kill)
    response = client.get("/api/portfolio/summary")
    assert response.status_code == 200
    assert list(tmp_path.iterdir()) == []
    assert response.json()["summary"]["captured_at"] is None
