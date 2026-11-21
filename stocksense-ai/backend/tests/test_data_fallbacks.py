"""Data-source fallbacks: Yahoo symbol mapping, MY/SG quote fallback, moomoo K-lines."""

import asyncio

import pandas as pd
import pytest

from app.core.stocks import get_yfinance_symbol
from app.data import moomoo_fetcher


def test_yf_symbol_mapping():
    assert get_yfinance_symbol("MAYBANK", "MY") == "1155.KL"
    assert get_yfinance_symbol("MY.MAYBANK", "MY") == "1155.KL"
    assert get_yfinance_symbol("1155", "MY") == "1155.KL"
    assert get_yfinance_symbol("DBS", "SG") == "D05.SI"
    assert get_yfinance_symbol("SG.D05", "SG") == "D05.SI"
    assert get_yfinance_symbol("AAPL", "US") == "AAPL"
    assert get_yfinance_symbol("US.NVDA", "US") == "NVDA"


def test_realtime_fallback_uses_market_symbol(monkeypatch):
    captured = {}

    def fake_download(symbol, **_kwargs):
        captured["symbol"] = symbol
        return pd.DataFrame(
            {"Open": [67.0], "High": [68.0], "Low": [66.5], "Close": [67.39], "Volume": [1000]},
            index=pd.DatetimeIndex(["2026-11-18"]),
        )

    import yfinance
    monkeypatch.setattr(yfinance, "download", fake_download)

    quote = asyncio.run(moomoo_fetcher._fallback_yfinance_quote("D05", "SG"))
    assert captured["symbol"] == "D05.SI"
    assert quote["last_price"] == 67.39
    assert quote["market"] == "SG"


class _FakeClient:
    def __init__(self, sub_ret=-1, kline=(-1, "err")):
        self.sub_ret = sub_ret
        self.kline = kline
        self.calls = []

    def subscribe(self, codes, subtypes, subscribe_push=False):
        self.calls.append(("subscribe", codes))
        return self.sub_ret, "No permission"

    def get_cur_kline(self, code, num, ktype=None, autype=None):
        self.calls.append(("kline", code, num))
        return self.kline


def _patch_client(monkeypatch, fake):
    monkeypatch.setattr(moomoo_fetcher, "_HAS_MOOMOO", True)
    monkeypatch.setattr(moomoo_fetcher.MoomooClient, "get_client", classmethod(lambda cls: fake))


def test_kline_subscribe_denied_returns_empty_without_recursing(monkeypatch):
    fake = _FakeClient(sub_ret=-1)
    _patch_client(monkeypatch, fake)

    df = asyncio.run(moomoo_fetcher.fetch_stock_data_moomoo("AAPL", 60))
    assert df.empty
    assert [c[0] for c in fake.calls] == ["subscribe"]


def test_kline_success_builds_indicator_frame(monkeypatch):
    n = 40
    raw = pd.DataFrame({
        "time_key": pd.date_range("2026-09-01", periods=n).strftime("%Y-%m-%d 00:00:00"),
        "open": [10.0 + i * 0.1 for i in range(n)],
        "high": [10.5 + i * 0.1 for i in range(n)],
        "low": [9.5 + i * 0.1 for i in range(n)],
        "close": [10.2 + i * 0.1 for i in range(n)],
        "volume": [1000 + i for i in range(n)],
    })
    fake = _FakeClient(sub_ret=0, kline=(0, raw))
    _patch_client(monkeypatch, fake)

    df = asyncio.run(moomoo_fetcher.fetch_stock_data_moomoo("AAPL", 40))
    assert len(df) == n
    assert {"Open", "Close", "rsi", "macd"}.issubset(df.columns)
    assert fake.calls[0] == ("subscribe", ["US.AAPL"])
    assert fake.calls[1] == ("kline", "US.AAPL", 40)
