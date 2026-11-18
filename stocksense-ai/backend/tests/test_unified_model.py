"""One XGBoost model drives the trading signal, SHAP and the backtest."""
import json

import numpy as np
import pandas as pd
import pytest

pytest.importorskip("xgboost")
pytest.importorskip("sklearn")
pytest.importorskip("pydantic_settings")

from app.ml.models import xgb_model
from app.services import xgboost_service as svc
from app.services.feature_service import DIRECTION_FEATURES


def make_df(n=400, seed=0, with_anomaly=False) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, n)))
    df = pd.DataFrame({"Close": close}, index=pd.date_range("2024-01-01", periods=n, freq="B"))
    for col in DIRECTION_FEATURES:
        if col == "anomaly_score" and not with_anomaly:
            continue
        df[col] = rng.normal(0, 1, n)
    # a learnable signal: tomorrow's direction leans on today's rsi
    df["rsi"] = (np.sign(np.roll(close, -1) - close) * 1.5 + rng.normal(0, 1, n))
    return df


@pytest.fixture()
def models_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(svc.settings, "models_dir", str(tmp_path))
    monkeypatch.setattr(xgb_model.settings, "models_dir", str(tmp_path))
    return tmp_path


def test_no_model_means_rule_based_fallback_and_never_trains(models_dir):
    df = make_df()
    assert svc.predict_prob_up(df, "TST") is None
    signal, conf, source = xgb_model.predict_xgb_with_source(df, "TST")
    assert source == "rule_based" and signal in {"BUY", "SELL", "HOLD"} and 0 <= conf <= 1
    assert not list(models_dir.iterdir())            # inference must not create a model


def test_training_saves_model_and_feature_list(models_dir):
    df = make_df()
    svc.train_xgboost(df, "TST")
    assert (models_dir / "xgb_TST.json").exists()
    cols = json.loads((models_dir / "xgb_TST.features.json").read_text())
    assert cols and set(cols) <= set(DIRECTION_FEATURES)


def test_signal_uses_the_same_model_as_explain_and_backtest(models_dir):
    df = make_df()
    svc.train_xgboost(df, "TST")
    p = svc.predict_prob_up(df, "TST")
    assert p is not None and 0.0 <= p <= 1.0
    pytest.importorskip("shap")
    explained = svc.shap_explain(df, "TST")
    assert explained["probability"] == pytest.approx(round(p, 4), abs=1e-4)   # same P(UP)


def test_signal_mapping_follows_the_threshold(models_dir, monkeypatch):
    df = make_df()
    monkeypatch.setattr(xgb_model.settings, "direction_threshold", 0.60)
    for prob, expected in [(0.72, ("BUY", 0.72)), (0.30, ("SELL", 0.70)), (0.52, ("HOLD", 0.52))]:
        monkeypatch.setattr(svc, "predict_prob_up", lambda *_a, p=prob: p)
        signal, conf, source = xgb_model.predict_xgb_with_source(df, "TST")
        assert (signal, round(conf, 2)) == expected and source == "xgb_binary"


def test_inference_aligns_to_saved_columns_with_or_without_anomaly_score(models_dir):
    train_df = make_df(with_anomaly=True)             # trained WITH anomaly_score (18 features)
    svc.train_xgboost(train_df, "TST")
    live_df = make_df(with_anomaly=False, seed=1)     # live data has no anomaly_score column
    p = svc.predict_prob_up(live_df, "TST")
    assert p is not None and 0.0 <= p <= 1.0          # missing column is filled, no crash


def test_mismatched_features_without_a_feature_list_fail_safe(models_dir):
    svc.train_xgboost(make_df(with_anomaly=True), "TST")
    (models_dir / "xgb_TST.features.json").unlink()   # legacy model without the sidecar
    assert svc.predict_prob_up(make_df(with_anomaly=False), "TST") is None
    assert xgb_model.predict_xgb_with_source(make_df(), "TST")[2] == "rule_based"


def test_a_corrupt_model_file_falls_back_instead_of_breaking(models_dir):
    (models_dir / "xgb_TST.json").write_text("not a model")
    assert xgb_model.predict_xgb_with_source(make_df(), "TST")[2] == "rule_based"
