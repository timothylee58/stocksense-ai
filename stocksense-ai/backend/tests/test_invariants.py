"""Challenge invariants: no runtime training, no feature-vector exposure,
confidence bounds on every prediction."""
import asyncio
import json
from types import SimpleNamespace

import numpy as np
import pandas as pd
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.router import api_router
from app.ml import predictor
from app.schemas.risk import OrderIntent, OrderSide, RiskDecision, RiskLimits
from app.services import decision_ledger
from app.services.risk_gate import evaluate_order


def test_no_runtime_training_routes():
    paths = [getattr(r, "path", "") for r in api_router.routes]
    assert not any("train" in p for p in paths)


def test_training_endpoint_is_not_served():
    app = FastAPI()
    app.include_router(api_router, prefix="/api")
    client = TestClient(app)
    assert client.post("/api/train/AAPL").status_code == 404
    assert client.post("/api/train/all/batch").status_code == 404


def test_order_intent_cannot_carry_feature_snapshot():
    intent = OrderIntent(
        ticker="AAPL",
        side="BUY",
        quantity=1,
        price=100.0,
        feature_snapshot={"rsi": 55.2},  # type: ignore[call-arg]
    )
    assert "feature_snapshot" not in intent.model_dump()


def _decision() -> RiskDecision:
    intent = OrderIntent(ticker="AAPL", side=OrderSide.BUY, quantity=1, price=100.0)
    return evaluate_order("d1", intent, _portfolio(), RiskLimits())


def _portfolio():
    from app.schemas.risk import PortfolioSnapshot

    return PortfolioSnapshot(account_id="T", equity=100_000.0, cash=100_000.0)


def _patch_ledger(monkeypatch, tmp_path):
    path = tmp_path / "ledger.jsonl"
    monkeypatch.setattr(
        decision_ledger,
        "get_settings",
        lambda: SimpleNamespace(decision_ledger_jsonl=str(path)),
    )
    monkeypatch.setattr(decision_ledger, "get_ch_client", lambda: None)
    return path


def test_ledger_writes_no_feature_snapshot(monkeypatch, tmp_path):
    path = _patch_ledger(monkeypatch, tmp_path)
    assert decision_ledger.record_decision(_decision(), "test") == "jsonl"
    assert "feature_snapshot" not in path.read_text(encoding="utf-8")


def test_ledger_reads_hide_legacy_feature_snapshot(monkeypatch, tmp_path):
    path = _patch_ledger(monkeypatch, tmp_path)
    legacy = {
        "decision_id": "d0",
        "event_type": "decision",
        "status": "approved",
        "ticker": "AAPL",
        "feature_snapshot": '{"rsi": 55.2}',
        "event_time": "2026-01-01T00:00:00+00:00",
    }
    path.write_text(json.dumps(legacy) + "\n", encoding="utf-8")
    rows = decision_ledger.list_decisions()
    assert rows and all("feature_snapshot" not in r for r in rows)


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


def test_xgboost_inference_never_trains(monkeypatch, tmp_path):
    from app.services import xgboost_service as svc

    monkeypatch.setattr(svc, "settings", SimpleNamespace(models_dir=str(tmp_path)))
    trained: list[str] = []
    monkeypatch.setattr(svc, "train_xgboost", lambda df, ticker: trained.append(ticker))

    assert svc.predict_xgboost(_frame(), "AAPL") == (0.5, 0.5)
    assert trained == []
    assert not (tmp_path / "xgb_AAPL.json").exists()


def test_isolation_forest_inference_never_trains(monkeypatch, tmp_path):
    from app.services import isolation_forest as svc

    monkeypatch.setattr(svc, "settings", SimpleNamespace(models_dir=str(tmp_path)))
    trained: list[str] = []
    monkeypatch.setattr(
        svc, "train_isolation_forest", lambda df, ticker: trained.append(ticker)
    )

    out = svc.predict_anomalies(_frame(), "AAPL")

    assert trained == []
    assert not (tmp_path / "isolation_forest_AAPL.pkl").exists()
    assert (out["anomaly_score"] == 0.0).all()
    assert not out["is_anomaly"].any()


def test_prediction_confidence_is_bounded_and_logits_free(monkeypatch):
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
    monkeypatch.setattr(predictor, "predict_lstm", lambda df, ticker: ([115.0 + i * 0.1 for i in range(30)], 0.9))
    monkeypatch.setattr(predictor, "predict_xgb", lambda df, ticker: ("BUY", 0.9))

    payload = asyncio.run(predictor.run_prediction("AAPL"))

    assert 0.0 <= payload["confidence"] <= 1.0
    assert "logits" not in payload
