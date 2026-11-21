from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import trading
from app.schemas.risk import KillSwitchState
from app.services import decision_ledger, paper_broker


def _client(monkeypatch, tmp_path):
    monkeypatch.setattr(paper_broker, "get_settings", lambda: SimpleNamespace(demo_mode=True))
    paper_broker.reset_demo()

    monkeypatch.setattr(
        decision_ledger,
        "get_settings",
        lambda: SimpleNamespace(decision_ledger_jsonl=str(tmp_path / "ledger.jsonl")),
    )
    monkeypatch.setattr(decision_ledger, "get_ch_client", lambda: None)
    monkeypatch.setattr(
        trading,
        "settings",
        SimpleNamespace(admin_api_token="test-admin", secret_key="unused"),
    )

    state = KillSwitchState()
    used: set[str] = set()

    async def fake_get_kill_switch():
        return state

    async def fake_set_kill_switch(enabled, reason, actor):
        nonlocal state
        state = KillSwitchState(enabled=enabled, reason=reason, actor=actor)
        return state

    async def fake_claim(key):
        if key in used:
            return False
        used.add(key)
        return True

    monkeypatch.setattr(trading, "get_kill_switch", fake_get_kill_switch)
    monkeypatch.setattr(trading, "set_kill_switch", fake_set_kill_switch)
    monkeypatch.setattr(trading, "_claim_idempotency", fake_claim)

    app = FastAPI()
    app.include_router(trading.router, prefix="/api")
    return TestClient(app)


def _order(**overrides):
    base = {
        "ticker": "AAPL",
        "side": "BUY",
        "quantity": 10,
        "price": 100.0,
        "dry_run": False,
        "idempotency_key": "order-1",
        "strategy_id": "test",
        "quote_ts": datetime.now(timezone.utc).isoformat(),
    }
    base.update(overrides)
    return base


def test_order_flow_ledgers_and_fills(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    response = client.post("/api/trading/orders", json=_order())
    assert response.status_code == 200
    payload = response.json()
    assert payload["decision"]["approved"] is True
    assert payload["execution"]["status"] == "filled"
    assert (tmp_path / "ledger.jsonl").exists()


def test_duplicate_idempotency_key_is_blocked(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    assert client.post("/api/trading/orders", json=_order()).json()["execution"]["status"] == "filled"
    second = client.post("/api/trading/orders", json=_order()).json()
    assert second["execution"]["status"] == "duplicate_blocked"


def test_kill_switch_blocks_buy_but_allows_sell(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    client.post("/api/trading/orders", json=_order(idempotency_key="seed"))

    response = client.post(
        "/api/risk/kill-switch",
        json={"enabled": True, "reason": "daily loss breach"},
        headers={"X-Admin-Token": "test-admin", "X-Agent-Id": "ops"},
    )
    assert response.status_code == 200

    blocked = client.post("/api/trading/orders", json=_order(idempotency_key="blocked")).json()
    assert blocked["decision"]["approved"] is False
    assert "KILL_SWITCH_ACTIVE" in blocked["decision"]["reason_codes"]

    flatten = client.post(
        "/api/trading/orders",
        json=_order(side="SELL", quantity=5, idempotency_key="flatten"),
    ).json()
    assert flatten["decision"]["approved"] is True
    assert flatten["execution"]["status"] == "filled"


def test_kill_switch_requires_admin_token(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    response = client.post(
        "/api/risk/kill-switch",
        json={"enabled": True, "reason": "test"},
        headers={"X-Admin-Token": "wrong"},
    )
    assert response.status_code == 401


def test_dry_run_never_executes(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    payload = client.post(
        "/api/trading/orders",
        json=_order(dry_run=True, idempotency_key="dry"),
    ).json()
    assert payload["decision"]["approved"] is True
    assert payload["execution"]["status"] == "dry_run"
    assert paper_broker.get_portfolio().cash == 100_000.0


def test_market_order_is_rejected(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    payload = client.post(
        "/api/trading/orders",
        json=_order(order_type="MARKET"),
    ).json()
    assert payload["decision"]["approved"] is False
    assert "MARKET_ORDER_FORBIDDEN" in payload["decision"]["reason_codes"]
    assert payload["execution"] is None


def test_buy_without_quote_timestamp_is_rejected(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    payload = client.post(
        "/api/trading/orders",
        json=_order(quote_ts=None),
    ).json()
    assert payload["decision"]["approved"] is False
    assert "QUOTE_TIMESTAMP_MISSING" in payload["decision"]["reason_codes"]


def test_buy_on_stale_quote_is_rejected(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    stale = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
    payload = client.post(
        "/api/trading/orders",
        json=_order(quote_ts=stale),
    ).json()
    assert payload["decision"]["approved"] is False
    assert "STALE_QUOTE" in payload["decision"]["reason_codes"]


def test_sell_is_not_blocked_by_missing_quote_timestamp(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    client.post("/api/trading/orders", json=_order(idempotency_key="seed-sell"))
    payload = client.post(
        "/api/trading/orders",
        json=_order(side="SELL", quantity=5, idempotency_key="exit", quote_ts=None),
    ).json()
    assert payload["decision"]["approved"] is True
    assert "QUOTE_TIMESTAMP_MISSING" not in payload["decision"]["reason_codes"]
