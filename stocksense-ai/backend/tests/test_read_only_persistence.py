"""Read-only persistence regressions, with no broker, database, or ML access."""
from __future__ import annotations

import asyncio
import builtins
import importlib
import socket
import sys
from datetime import date, datetime
from types import ModuleType, SimpleNamespace

import pandas as pd
import pytest


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("External connections are forbidden in persistence tests")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket.socket, "connect_ex", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)


@pytest.fixture(params=[False, True], ids=["writable", "read-only"])
def settings(request, monkeypatch, tmp_path):
    from app.core import config

    value = config.Settings(
        _env_file=None,
        read_only_mode=request.param,
        moomoo_enabled=False,
        moomoo_trade_enabled=False,
        clickhouse_enabled=False,
        demo_mode=False,
        models_dir=str(tmp_path / "models"),
        default_tickers=["NVDA", "AAPL"],
    )
    monkeypatch.setattr(config, "get_settings", lambda: value)
    return value


@pytest.fixture
def load_module(monkeypatch, settings):
    """Use real modules; restore any previously imported modules after each test."""
    def load(name):
        parent_name, _, leaf = name.rpartition(".")
        parent = importlib.import_module(parent_name)
        monkeypatch.setattr(parent, leaf, None, raising=False)
        monkeypatch.setitem(sys.modules, name, None)
        del sys.modules[name]
        return importlib.import_module(name)

    return load


class ClientFactory:
    def __init__(self, client):
        self.client = client
        self.calls = 0

    def __call__(self):
        self.calls += 1
        return self.client


class SupabaseFake:
    def __init__(self):
        self.calls = []
        self.rows = [{"ticker": "NVDA", "value": 0.75}]

    def table(self, name):
        self.calls.append(("table", name))
        return self

    def insert(self, record):
        self.calls.append(("insert", record))
        return self

    def select(self, columns):
        self.calls.append(("select", columns))
        return self

    def eq(self, column, value):
        self.calls.append(("eq", column, value))
        return self

    def gte(self, column, value):
        self.calls.append(("gte", column, value))
        return self

    def order(self, column, *, desc):
        self.calls.append(("order", column, desc))
        return self

    def limit(self, count):
        self.calls.append(("limit", count))
        return self

    def execute(self):
        self.calls.append(("execute",))
        return SimpleNamespace(data=self.rows)


class ClickHouseFake:
    def __init__(self):
        self.writes = []
        self.queries = []
        self.frame = pd.DataFrame([{
            "date": date.today(), "open": 100.0, "high": 103.0,
            "low": 99.0, "close": 102.0, "volume": 1000,
        }])

    def insert_df(self, table, frame):
        self.writes.append((table, frame.copy()))

    def query(self, query, *, parameters):
        self.queries.append((query, parameters))
        return SimpleNamespace(
            row_count=1, first_row=[date.today()], df=lambda: self.frame.copy(),
        )


@pytest.mark.parametrize("writer,table", [
    ("insert_prediction", "predictions"),
    ("insert_anomaly", "anomalies"),
    ("insert_sentiment", "sentiment_scores"),
])
def test_supabase_writes_respect_read_only_mode(
    writer, table, settings, load_module, monkeypatch,
):
    database = load_module("app.core.database")
    client = SupabaseFake()
    factory = ClientFactory(client)
    monkeypatch.setattr(database, "get_supabase_client", factory)
    record = {"ticker": "NVDA", "confidence": 0.75}

    assert asyncio.run(getattr(database, writer)(record)) is None

    if settings.read_only_mode:
        assert client.calls == []
        assert factory.calls == 0
    else:
        assert client.calls == [("table", table), ("insert", record), ("execute",)]
        assert factory.calls == 1


@pytest.mark.parametrize("writer,table", [
    ("ch_write_ohlcv", "ohlcv"),
    ("ch_write_sentiment", "news_sentiment"),
    ("ch_write_backtest", "backtest_results"),
])
def test_clickhouse_writes_respect_read_only_mode(
    writer, table, settings, load_module, monkeypatch,
):
    store = load_module("app.core.ch_store")
    client = ClickHouseFake()
    factory = ClientFactory(client)
    monkeypatch.setattr(store, "get_ch_client", factory)
    payloads = {
        "ch_write_ohlcv": pd.DataFrame(
            [{"Open": 100.0, "High": 103.0, "Low": 99.0, "Close": 102.0, "Volume": 1000}],
            index=pd.DatetimeIndex(["2026-01-02"], name="Date"),
        ),
        "ch_write_sentiment": [{
            "published_at": datetime(2026, 1, 2), "headline": "Sample headline",
            "source": "fixture", "sentiment": "positive", "score": 0.75,
        }],
        "ch_write_backtest": {
            "metrics": {"total_return": 0.12, "n_trades": 3},
            "test_period": {"start": "2026-01-02", "end": "2026-01-05"},
        },
    }

    assert getattr(store, writer)("NVDA", payloads[writer]) is None

    if settings.read_only_mode:
        assert client.writes == []
        assert factory.calls == 0
    else:
        assert factory.calls == 1
        assert len(client.writes) == 1
        actual_table, frame = client.writes[0]
        assert actual_table == table
        assert frame["ticker"].tolist() == ["NVDA"]
        column, expected = {
            "ohlcv": ("close", 102.0),
            "news_sentiment": ("score", 0.75),
            "backtest_results": ("total_return", 0.12),
        }[table]
        assert frame[column].tolist() == [expected]


@pytest.mark.parametrize("reader,table", [
    ("get_anomaly_history", "anomalies"),
    ("get_sentiment_history", "sentiment_scores"),
])
def test_supabase_reads_remain_available(reader, table, load_module, monkeypatch):
    database = load_module("app.core.database")
    client = SupabaseFake()
    monkeypatch.setattr(database, "get_supabase_client", ClientFactory(client))

    result = asyncio.run(getattr(database, reader)("nvda"))

    assert result == [{"ticker": "NVDA", "value": 0.75}]
    assert client.calls[:3] == [("table", table), ("select", "*"), ("eq", "ticker", "NVDA")]
    assert client.calls[-1] == ("execute",)


@pytest.mark.parametrize("reader,args", [
    ("ch_read_ohlcv", ("NVDA", 2)),
    ("ch_is_fresh", ("NVDA", 2)),
    ("ch_read_sentiment", ("NVDA",)),
    ("ch_read_backtest_history", ("NVDA",)),
])
def test_clickhouse_reads_remain_available(reader, args, load_module, monkeypatch):
    store = load_module("app.core.ch_store")
    client = ClickHouseFake()
    monkeypatch.setattr(store, "get_ch_client", ClientFactory(client))

    result = getattr(store, reader)(*args)

    if reader == "ch_is_fresh":
        assert result is True
    elif reader == "ch_read_ohlcv":
        assert result["Close"].tolist() == [102.0]
        assert result.index[0].date() == date.today()
    else:
        pd.testing.assert_frame_equal(result, client.frame)
    assert len(client.queries) == 1
    assert client.queries[0][1]["ticker"] == "NVDA"
    assert client.writes == []


def test_redis_caching_remains_available(load_module, monkeypatch):
    redis_client = load_module("app.core.redis_client")

    class RedisFake:
        def __init__(self):
            self.values = {}
            self.ttls = {}

        async def setex(self, key, ttl, value):
            self.values[key] = value
            self.ttls[key] = ttl

        async def get(self, key):
            return self.values.get(key)

    client = RedisFake()
    monkeypatch.setattr(redis_client, "get_redis", ClientFactory(client))

    async def round_trip():
        await redis_client.cache_set("prediction:NVDA", {"confidence": 0.75}, 300)
        return await redis_client.cache_get("prediction:NVDA")

    assert asyncio.run(round_trip()) == {"confidence": 0.75}
    assert client.ttls == {"prediction:NVDA": 300}


class SchedulerFake:
    def __init__(self):
        self.jobs = []
        self.running = False
        self.starts = 0
        self.shutdowns = 0

    def add_job(self, callback, trigger, **kwargs):
        self.jobs.append((callback, trigger, kwargs))

    def start(self):
        self.starts += 1
        self.running = True

    def shutdown(self):
        self.shutdowns += 1
        self.running = False


@pytest.fixture
def main_module(load_module, monkeypatch):
    from fastapi import APIRouter

    # The real API router imports unrelated model/services; keep lifespan real.
    router = ModuleType("app.api.router")
    router.api_router = APIRouter()
    monkeypatch.setitem(sys.modules, "app.api.router", router)
    main = load_module("app.main")
    monkeypatch.setattr(main, "scheduler", SchedulerFake())
    return main


def test_startup_does_not_create_models_directory_in_read_only_mode(
    main_module, settings, tmp_path,
):
    async def startup():
        async with main_module.app.router.lifespan_context(main_module.app):
            assert (tmp_path / "models").exists() is (not settings.read_only_mode)

    asyncio.run(startup())
    assert (tmp_path / "models").exists() is (not settings.read_only_mode)


def test_lifespan_schedules_ingestion_only_when_writable(main_module, settings):
    from app.services.scheduler_service import run_daily_ingestion

    scheduler = main_module.scheduler

    async def startup():
        async with main_module.app.router.lifespan_context(main_module.app):
            if settings.read_only_mode:
                assert scheduler.jobs == []
                assert scheduler.starts == 0
                assert not scheduler.running
            else:
                assert scheduler.jobs == [(run_daily_ingestion, "cron", {"hour": 9, "minute": 0})]
                assert scheduler.starts == 1
                assert scheduler.running

    asyncio.run(startup())
    assert not scheduler.running
    assert scheduler.shutdowns == (0 if settings.read_only_mode else 1)


def test_ingest_ticker_skips_dependency_imports_and_work_when_read_only(
    settings, load_module, monkeypatch,
):
    ingestion = load_module("app.services.ingestion_service")
    calls = []
    imports = []
    frame = pd.DataFrame([{"Close": 102.0}])
    record = {"ticker": "NVDA", "anomaly_score": 0.75}

    async def fetch(ticker, *, period_years):
        calls.append(("fetch", ticker, period_years))
        return frame

    def anomaly(data, ticker, *, days):
        assert data is frame
        calls.append(("anomaly", ticker, days))
        return [record]

    def sentiment(ticker):
        calls.append(("sentiment", ticker))
        return 0.75, ["Sample headline"]

    async def insert_anomaly(value):
        calls.append(("persist_anomaly", value))

    async def insert_sentiment(value):
        calls.append(("persist_sentiment", value))

    def write_sentiment(ticker, records):
        calls.append(("persist_headlines", ticker, records))

    dependencies = {
        "app.data.fetcher": {"fetch_stock_data": fetch},
        "app.services.isolation_forest": {"get_anomaly_history_from_df": anomaly},
        "app.services.finbert_service": {"get_finbert_score": sentiment},
    }
    for name, attributes in dependencies.items():
        module = ModuleType(name)
        module.__dict__.update(attributes)
        monkeypatch.setitem(sys.modules, name, module)
    database = load_module("app.core.database")
    store = load_module("app.core.ch_store")
    monkeypatch.setattr(database, "insert_anomaly", insert_anomaly)
    monkeypatch.setattr(database, "insert_sentiment", insert_sentiment)
    monkeypatch.setattr(store, "ch_write_sentiment", write_sentiment)
    original_import = builtins.__import__

    def track_import(name, *args, **kwargs):
        if name in dependencies:
            imports.append(name)
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", track_import)
    assert asyncio.run(ingestion.ingest_ticker("NVDA")) is None

    if settings.read_only_mode:
        assert calls == []
        assert imports == []
    else:
        assert calls[:4] == [
            ("fetch", "NVDA", 2), ("anomaly", "NVDA", 5),
            ("persist_anomaly", record), ("sentiment", "NVDA"),
        ]
        assert calls[4] == ("persist_sentiment", {
            "ticker": "NVDA", "finbert_score": 0.75, "news_count": 1,
            "top_headlines": ["Sample headline"],
        })
        assert len(calls) == 6
        _, ticker, records = calls[5]
        assert ticker == "NVDA"
        assert len(records) == 1
        assert records[0]["headline"] == "Sample headline"
        assert records[0]["sentiment"] == "positive"
        assert records[0]["score"] == 0.75


def test_daily_ingestion_does_not_dispatch_tickers_when_read_only(
    settings, load_module, monkeypatch,
):
    ingestion = load_module("app.services.ingestion_service")
    tickers = []

    async def ingest(ticker):
        tickers.append(ticker)

    monkeypatch.setattr(ingestion, "ingest_ticker", ingest)
    assert asyncio.run(ingestion.run_daily_ingestion()) is None
    assert tickers == ([] if settings.read_only_mode else ["NVDA", "AAPL"])
