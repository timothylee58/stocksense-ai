"""Phase 1–3 agent run loop: shadow, paper, audit and reconciliation."""
from __future__ import annotations

import asyncio
import functools
import json
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import pandas as pd
import pytest

import app.agents.runtime as runtime_module
from app.agents.artifacts import Bar, RiskVerdict
from app.agents.bindings import AgentBindings, PolicyViolation, _parse_ts, require_tool
from app.agents.journal import Journal
from app.agents.reconciliation import drop_demo_order_rows, reconcile
from app.agents.runtime import AgentRuntime
from app.agents.signals import intent_hash
from app.schemas.risk import (
    KillSwitchState,
    OrderExecution,
    OrderIntent,
    PortfolioPosition,
    PortfolioSnapshot,
    RiskLimits,
)
from app.services import decision_ledger
from app.services.risk_gate import evaluate_order

NOW = datetime.now(timezone.utc)
SESSION = date(2026, 11, 18)


def run_async(fn):
    """Repo convention: async behaviour driven through asyncio.run in sync tests."""

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        return asyncio.run(fn(*args, **kwargs))

    return wrapper


def _bars(n: int = 120, start: float = 100.0) -> list[Bar]:
    idx = pd.date_range(end="2026-11-18", periods=n, freq="B")
    bars = []
    for i, stamp in enumerate(idx):
        close = start + i * 0.1
        bars.append(Bar(
            ts=stamp.to_pydatetime().replace(tzinfo=timezone.utc),
            open=close - 0.2,
            high=close + 0.5,
            low=close - 0.5,
            close=close,
            volume=1_000_000.0,
        ))
    return bars


class FakeBindings(AgentBindings):
    def __init__(
        self,
        *,
        health_ok: bool = True,
        quote_age_s: float = 1.0,
        xgb=("BUY", 0.8),
        lstm=("UP", 0.7),
        news=(0.4, ["headline one", "headline two"]),
        atr: float | None = 2.0,
        price: float = 100.0,
        positions: list[PortfolioPosition] | None = None,
    ):
        self.health_ok = health_ok
        self.quote_age_s = quote_age_s
        self.xgb = xgb
        self.lstm = lstm
        self.news_value = news
        self.atr = atr
        self.price = price
        self.positions = positions or []
        self.calls: list[tuple] = []
        self.placed: list[OrderIntent] = []
        self.orders: list[dict] = []
        self._cash = 100_000.0

    def _portfolio(self) -> PortfolioSnapshot:
        return PortfolioSnapshot(
            account_id="DEMO-PAPER",
            equity=100_000.0,
            cash=self._cash,
            day_pnl=0.0,
            peak_equity=100_000.0,
            positions=[p.model_copy() for p in self.positions],
        )

    async def health(self, agent_id: str) -> dict:
        self.calls.append(("health", agent_id))
        return {"ok": self.health_ok, "reason": "" if self.health_ok else "gateway down"}

    async def dataset(self, agent_id: str, symbol: str) -> dict:
        self.calls.append(("dataset", agent_id, symbol))
        return {
            "valid": True,
            "quote": {
                "price": self.price,
                "prev_close": self.price - 1,
                "ts": NOW - timedelta(seconds=self.quote_age_s),
                "source": "moomoo",
                "delayed": False,
            },
            "bars": _bars(),
            "source": "moomoo",
        }

    async def news(self, agent_id: str, symbol: str):
        self.calls.append(("news", agent_id, symbol))
        return self.news_value

    async def ml(self, agent_id: str, symbol: str, bars):
        self.calls.append(("ml", agent_id, symbol))
        return {"xgboost": self.xgb, "lstm": self.lstm, "atr": self.atr}

    async def portfolio(self, agent_id: str) -> PortfolioSnapshot:
        self.calls.append(("portfolio", agent_id))
        return self._portfolio()

    async def open_orders(self, agent_id: str) -> list[dict]:
        self.calls.append(("open_orders", agent_id))
        return list(self.orders)

    async def place_order(self, agent_id: str, intent: OrderIntent, decision_id: str) -> OrderExecution:
        self.calls.append(("place_order", agent_id, decision_id))
        self.placed.append(intent)
        order_id = f"BROKER-{len(self.placed)}"
        side_qty = intent.quantity if intent.side.value == "BUY" else -intent.quantity
        existing = next((p for p in self.positions if p.ticker == intent.ticker), None)
        total = (existing.quantity if existing else 0.0) + side_qty
        self.positions = [p for p in self.positions if p.ticker != intent.ticker]
        if total > 0:
            self.positions.append(PortfolioPosition(
                ticker=intent.ticker, quantity=total, market_value=total * intent.price,
            ))
        self._cash += -side_qty * intent.price
        self.orders.append({
            "order_id": order_id,
            "ticker": intent.ticker,
            "remark": f"stocksense:{intent.idempotency_key}",
            "status": "filled",
        })
        return OrderExecution(status="filled", order_id=order_id, message="filled", dry_run=False)


@pytest.fixture
def ledger(monkeypatch, tmp_path):
    monkeypatch.setattr(
        decision_ledger,
        "get_settings",
        lambda: SimpleNamespace(decision_ledger_jsonl=str(tmp_path / "ledger.jsonl")),
    )
    monkeypatch.setattr(decision_ledger, "get_ch_client", lambda: None)

    async def no_kill():
        return KillSwitchState()

    monkeypatch.setattr(runtime_module, "get_kill_switch", no_kill)
    return tmp_path / "ledger.jsonl"


def _runtime(bindings: FakeBindings, tmp_path, phase: str = "shadow") -> AgentRuntime:
    return AgentRuntime(
        phase=phase,
        bindings=bindings,
        journal=Journal(tmp_path / "journal.jsonl"),
        symbols=["AAPL", "NVDA"],
    )


def _events(runtime: AgentRuntime, run_id: str) -> list[dict]:
    return [e["event_type"] for e in runtime.journal.read(run_id=run_id)]


@run_async
async def test_shadow_logs_decisions_and_places_no_orders(ledger, tmp_path):
    bindings = FakeBindings()
    runtime = _runtime(bindings, tmp_path)
    summary = await runtime.run_session(session_date=SESSION)

    assert summary["run"]["status"] == "completed"
    assert summary["decisions"] == 2
    assert summary["executions"] == []
    assert bindings.placed == []
    assert not any(call[0] == "place_order" for call in bindings.calls)

    run_id = summary["run"]["run_id"]
    events = _events(runtime, run_id)
    for expected in ("run_started", "dataset", "technical", "sentiment", "evaluation",
                     "risk_verdict", "execution_skipped", "audit", "run_finished"):
        assert expected in events

    rows = [json.loads(line) for line in ledger.read_text().splitlines()]
    assert len(rows) == 2
    assert all(row["event_type"] == "decision" and row["dry_run"] == 1 for row in rows)
    assert runtime.journal.verify()[0] is True


@run_async
async def test_second_run_same_key_is_idempotent(ledger, tmp_path):
    bindings = FakeBindings()
    runtime = _runtime(bindings, tmp_path)
    first = await runtime.run_session(session_date=SESSION)
    calls_after_first = len(bindings.calls)
    second = await runtime.run_session(session_date=SESSION)

    assert second["reused"] is True
    assert second["run"]["run_id"] == first["run"]["run_id"]
    assert len(bindings.calls) == calls_after_first


@run_async
async def test_health_failure_aborts_before_any_decision(ledger, tmp_path):
    bindings = FakeBindings(health_ok=False)
    runtime = _runtime(bindings, tmp_path)
    summary = await runtime.run_session(session_date=SESSION)

    assert summary["run"]["status"] == "aborted"
    assert "health" in summary["run"]["halt_reason"]
    assert summary["decisions"] == 0
    assert bindings.placed == []
    assert not any(call[0] == "dataset" for call in bindings.calls)


@run_async
async def test_five_shadow_sessions_produce_zero_orders(ledger, tmp_path):
    bindings = FakeBindings()
    runtime = _runtime(bindings, tmp_path)
    dates = [date(2026, 11, 9) + timedelta(days=i) for i in range(5)]
    summaries = [await runtime.run_session(session_date=d) for d in dates]

    assert all(s["run"]["status"] == "completed" for s in summaries)
    assert len({s["run"]["run_id"] for s in summaries}) == 5
    assert bindings.placed == []
    assert runtime.journal.verify()[0] is True


@run_async
async def test_stale_quote_is_denied(ledger, tmp_path):
    bindings = FakeBindings(quote_age_s=120)
    runtime = _runtime(bindings, tmp_path)
    summary = await runtime.run_session(session_date=SESSION)

    assert summary["decisions"] == 0
    assert [n["status"] for n in summary["run"]["per_name_status"]] == ["denied", "denied"]
    datasets = [e for e in runtime.journal.read(run_id=summary["run"]["run_id"])
                if e["event_type"] == "dataset"]
    assert all(e["payload"]["valid"] is False and e["payload"]["deny_reason"] == "STALE_QUOTE"
               for e in datasets)


@run_async
async def test_paper_phase_executes_one_limit_order(ledger, tmp_path):
    bindings = FakeBindings()
    runtime = _runtime(bindings, tmp_path, phase="paper")
    summary = await runtime.run_session(session_date=SESSION)

    assert summary["run"]["status"] == "completed"
    assert summary["decisions"] == 2
    assert len(summary["executions"]) == 2
    assert len(bindings.placed) == 2
    assert all(intent.dry_run is False for intent in bindings.placed)
    assert all(intent.order_type.value == "LIMIT" for intent in bindings.placed)
    # A10: the decision id is the order tag carried to the broker.
    decision_ids = {e["payload"]["decision_id"] for e in runtime.journal.read(
        run_id=summary["run"]["run_id"]) if e["event_type"] == "risk_verdict"}
    assert {i.idempotency_key for i in bindings.placed} == decision_ids
    assert {o["remark"] for o in bindings.orders} == {f"stocksense:{d}" for d in decision_ids}

    rows = [json.loads(line) for line in ledger.read_text().splitlines()]
    assert {r["event_type"] for r in rows} == {"decision", "execution"}


@run_async
async def test_duplicate_execution_is_blocked(ledger, tmp_path):
    bindings = FakeBindings()
    runtime = _runtime(bindings, tmp_path, phase="paper")
    intent = OrderIntent(
        ticker="AAPL", side="BUY", quantity=10, price=100.0,
        dry_run=False, quote_ts=NOW, idempotency_key="dec-fixed",
    )
    verdict = RiskVerdict(approved=True, intent_hash=intent_hash(intent))
    portfolio = bindings._portfolio()
    decision = evaluate_order("dec-fixed", intent, portfolio, RiskLimits())

    first = await runtime._execute("run-x", "dec-fixed", intent, verdict, decision)
    second = await runtime._execute("run-x", "dec-fixed", intent, verdict, decision)

    assert first["status"] == "filled"
    assert second["status"] == "duplicate"
    assert len(bindings.placed) == 1


@run_async
async def test_signal_without_a_position_never_shorts(ledger, tmp_path):
    bindings = FakeBindings(xgb=("SELL", 0.9), lstm=("DOWN", 0.8), news=(-0.6, ["bad news"]))
    runtime = _runtime(bindings, tmp_path, phase="paper")
    summary = await runtime.run_session(session_date=SESSION)

    assert summary["decisions"] == 0
    assert [n["status"] for n in summary["run"]["per_name_status"]] == ["no_trade", "no_trade"]
    assert bindings.placed == []


@run_async
async def test_kill_switch_blocks_new_buys(ledger, tmp_path, monkeypatch):
    async def active_kill():
        return KillSwitchState(enabled=True, reason="ops halt")

    monkeypatch.setattr(runtime_module, "get_kill_switch", active_kill)
    bindings = FakeBindings()
    runtime = _runtime(bindings, tmp_path, phase="paper")
    summary = await runtime.run_session(session_date=SESSION)

    assert summary["decisions"] == 2
    assert summary["executions"] == []
    assert [n["status"] for n in summary["run"]["per_name_status"]] == ["rejected", "rejected"]
    assert bindings.placed == []


@run_async
async def test_ledger_outage_fails_closed(ledger, tmp_path, monkeypatch):
    monkeypatch.setattr(decision_ledger, "record_decision", lambda decision, actor: "unavailable")
    bindings = FakeBindings()
    runtime = _runtime(bindings, tmp_path, phase="paper")
    summary = await runtime.run_session(session_date=SESSION)

    assert summary["run"]["status"] == "aborted"
    assert "ledger" in summary["run"]["halt_reason"].lower()
    assert bindings.placed == []


@run_async
async def test_journal_tamper_is_detected(ledger, tmp_path):
    journal = Journal(tmp_path / "tamper.jsonl")
    journal.append(run_id="r1", strategy_version="s1.0", event_type="a", payload={"x": 1})
    journal.append(run_id="r1", strategy_version="s1.0", event_type="b", payload={"x": 2})
    assert journal.verify()[0] is True

    path = tmp_path / "tamper.jsonl"
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    rows[1]["payload"]["x"] = 99
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    ok, breaks = journal.verify()
    assert ok is False
    assert any("hash mismatch" in b for b in breaks)


def test_reconciliation_matches_and_flags_breaks():
    ledger_rows = [
        {"event_type": "execution", "order_id": "B1", "status": "filled"},
        {"event_type": "decision", "order_id": "", "status": "approved"},
    ]
    ok = reconcile(ledger_rows, [{"order_id": "B1"}])
    assert ok["ok"] is True and ok["matched"] == 1

    bad = reconcile(ledger_rows, [{"order_id": "B2"}])
    assert bad["ok"] is False
    assert bad["missing_at_broker"] == ["B1"]
    assert bad["untracked_at_ledger"] == ["B2"]


def test_demo_fills_are_dropped_from_real_reconciliation():
    rows = [
        {"event_type": "execution", "order_id": "DEMO-ABC", "status": "filled"},
        {"event_type": "execution", "order_id": "3116213", "status": "submitted"},
        {"event_type": "decision", "order_id": "", "status": "approved"},
    ]
    kept = drop_demo_order_rows(rows)
    assert [r["order_id"] for r in kept] == ["3116213", ""]
    assert reconcile(kept, [{"order_id": "3116213"}])["ok"] is True


def test_live_tools_are_refused_by_the_binding_guard():
    with pytest.raises(PolicyViolation) as live:
        require_tool("executor", "trading_order_place")
    assert live.value.code == "LIVE_TOOL_DENIED"

    with pytest.raises(PolicyViolation) as not_allowed:
        require_tool("technical", "sim_trade_input_order")
    assert not_allowed.value.code == "NOT_IN_ALLOWLIST"


def test_naive_broker_timestamp_is_read_as_local_time():
    # The fetcher emits local wall-clock strings; reading them as UTC made
    # every quote look hours in the future and the gate rejected it.
    for text in ("2026-11-19 13:34:57", "2026-11-19 13:34:57.040648"):
        parsed = _parse_ts(text)
        expected = datetime.strptime(
            text, "%Y-%m-%d %H:%M:%S.%f" if "." in text else "%Y-%m-%d %H:%M:%S"
        ).astimezone(timezone.utc)
        assert parsed == expected
    assert _parse_ts("2026-11-19T13:34:57+08:00") == datetime(2026, 11, 19, 5, 34, 57, tzinfo=timezone.utc)


def test_max_open_positions_blocks_a_sixth_name():
    positions = [
        PortfolioPosition(ticker=t, quantity=1, market_value=100.0)
        for t in ("AAPL", "MSFT", "AMD", "GOOGL", "META")
    ]
    portfolio = PortfolioSnapshot(
        account_id="TEST", equity=100_000.0, cash=100_000.0, peak_equity=100_000.0,
        positions=positions,
    )
    intent = OrderIntent(ticker="NVDA", side="BUY", quantity=1, price=100.0)
    decision = evaluate_order("d", intent, portfolio, RiskLimits(max_open_positions=5))
    assert decision.approved is False
    assert "MAX_OPEN_POSITIONS_EXCEEDED" in decision.reason_codes
