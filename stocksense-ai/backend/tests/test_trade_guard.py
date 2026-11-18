from types import SimpleNamespace

import pytest

from app.data import moomoo_trade_client as client


def _settings(**overrides):
    base = dict(
        moomoo_trade_enabled=True,
        moomoo_trd_env="SIMULATE",
        moomoo_paper_account_id="123456",
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_disabled_trading_is_refused(monkeypatch):
    monkeypatch.setattr(client, "get_settings", lambda: _settings(moomoo_trade_enabled=False))
    with pytest.raises(client.TradingDisabled):
        client.verify_paper_guard()


def test_live_environment_is_refused_before_sdk(monkeypatch):
    monkeypatch.setattr(client, "get_settings", lambda: _settings(moomoo_trd_env="REAL"))
    with pytest.raises(client.LiveTradingForbidden):
        client.verify_paper_guard()


def test_missing_paper_account_id_is_refused_before_sdk(monkeypatch):
    monkeypatch.setattr(client, "get_settings", lambda: _settings(moomoo_paper_account_id=""))
    with pytest.raises(client.PaperAccountIdRequired):
        client.verify_paper_guard()
