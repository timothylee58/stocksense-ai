from types import SimpleNamespace

from app.schemas.risk import KillSwitchState, OrderIntent, OrderSide, PortfolioSnapshot, RiskLimits
from app.services import decision_ledger
from app.services.risk_gate import evaluate_order


def _decision(kill=False):
    intent = OrderIntent(
        ticker="AAPL",
        side=OrderSide.BUY,
        quantity=10,
        price=100.0,
        strategy_id="unit-test",
        model_version="xgb-v1",
        idempotency_key="idem-1",
    )
    portfolio = PortfolioSnapshot(account_id="TEST", equity=100_000.0, cash=100_000.0)
    return evaluate_order(
        "decision-1", intent, portfolio, RiskLimits(),
        KillSwitchState(enabled=kill, reason="test"),
    )


def _patch_storage(monkeypatch, tmp_path):
    cfg = SimpleNamespace(decision_ledger_jsonl=str(tmp_path / "ledger.jsonl"))
    monkeypatch.setattr(decision_ledger, "get_settings", lambda: cfg)
    monkeypatch.setattr(decision_ledger, "get_ch_client", lambda: None)


def test_records_and_reads_jsonl_fallback(monkeypatch, tmp_path):
    _patch_storage(monkeypatch, tmp_path)
    approved = _decision()
    rejected = _decision(kill=True)

    assert decision_ledger.record_decision(approved, "agent") == "jsonl"
    assert decision_ledger.record_decision(rejected, "agent") == "jsonl"

    records = decision_ledger.list_decisions(limit=10)
    assert len(records) == 2
    assert records[0]["status"] == "rejected"
    assert "KILL_SWITCH_ACTIVE" in records[0]["reason_codes"]
    assert records[1]["status"] == "approved"
    assert records[1]["dry_run"] is True
    assert records[1]["strategy_id"] == "unit-test"
    assert records[1]["idempotency_key"] == "idem-1"


def test_filters_by_ticker(monkeypatch, tmp_path):
    _patch_storage(monkeypatch, tmp_path)
    decision_ledger.record_decision(_decision(), "agent")
    assert len(decision_ledger.list_decisions(limit=10, ticker="AAPL")) == 1
    assert len(decision_ledger.list_decisions(limit=10, ticker="MSFT")) == 0
