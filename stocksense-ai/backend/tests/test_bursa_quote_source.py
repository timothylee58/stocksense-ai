"""MY quotes default to delayed Yahoo .KL data; moomoo is only the fallback."""

import asyncio
from types import SimpleNamespace

import pytest

from app.api.routes import bursa


@pytest.fixture(autouse=True)
def _non_demo(monkeypatch):
    monkeypatch.setattr(bursa, "settings", SimpleNamespace(demo_mode=False))


def test_my_quote_prefers_yfinance(monkeypatch):
    async def fake_yf(full_code):
        return {"last_price": 9.91, "prev_close_price": 9.92, "source": "yfinance_kl"}

    async def boom(*_args, **_kwargs):
        raise AssertionError("moomoo must not be called when yfinance succeeds")

    monkeypatch.setattr(bursa, "_yf_quote_my", fake_yf)
    monkeypatch.setattr(bursa, "fetch_realtime_quote", boom)

    quote = asyncio.run(bursa._fetch_quote("MY.MAYBANK"))
    assert quote["source"] == "yfinance_kl"
    assert quote["last_price"] == 9.91


def test_my_quote_falls_back_to_moomoo(monkeypatch):
    async def no_yf(_full_code):
        return None

    async def fake_moomoo(_ticker, _market):
        return {"last_price": 9.90, "prev_close_price": 9.92, "source": "moomoo"}

    monkeypatch.setattr(bursa, "_yf_quote_my", no_yf)
    monkeypatch.setattr(bursa, "fetch_realtime_quote", fake_moomoo)

    quote = asyncio.run(bursa._fetch_quote("MY.MAYBANK"))
    assert quote["source"] == "moomoo"
    assert quote["last_price"] == 9.9


def test_my_quote_reports_error_when_both_sources_fail(monkeypatch):
    async def no_yf(_full_code):
        return None

    async def broken_moomoo(_ticker, _market):
        raise RuntimeError("OpenD down")

    monkeypatch.setattr(bursa, "_yf_quote_my", no_yf)
    monkeypatch.setattr(bursa, "fetch_realtime_quote", broken_moomoo)

    quote = asyncio.run(bursa._fetch_quote("MY.MAYBANK"))
    assert quote["source"] == "error"
    assert quote["last_price"] == 0.0
