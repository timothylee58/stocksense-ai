"""Agent artifact contracts and template/inventory consistency.

These tests pin the canonical template shape (agent -> tools -> artifact ->
failure -> acceptance hook) so the seven agents cannot drift silently.
"""
from datetime import date, datetime, timezone

import pytest
from pydantic import ValidationError

from app.agents import policy
from app.agents.artifacts import (
    AuditReport,
    Dataset,
    Direction,
    ExecutionRecord,
    Fill,
    ProvenanceRef,
    Quote,
    RiskVerdict,
    RunRecord,
    SentimentSignal,
    TechnicalSignal,
    Universe,
)
from app.agents.registry import (
    AGENT_IDS,
    WRITE_CAPABILITY_TOOLS,
    AgentTemplate,
    load_moomoo_inventory,
    load_templates,
)

NOW = datetime(2026, 11, 19, 14, 30, tzinfo=timezone.utc)
PROV = [ProvenanceRef(kind="dataset", ref="dataset:AAPL:2026-11-19")]


def _template(**overrides):
    base = dict(
        id="technical",
        name="Technical Analyst",
        mission="m",
        cadence="c",
        tools={"read": ["quote_history_kline"], "write": []},
        input_schemas=["Dataset"],
        output_schema="TechnicalSignal",
        outputs=["TechnicalSignal{...}"],
        hard_rules=["Paper/SIMULATE only."],
        failure="insufficient_data",
        acceptance_hook=["A7"],
        system_prompt="p",
    )
    base.update(overrides)
    return AgentTemplate(**base)


def test_unknown_read_tool_fails_template_validation():
    with pytest.raises(ValidationError):
        _template(tools={"read": ["quote_made_up_tool"], "write": []})


def test_write_capability_is_reserved_for_executor():
    with pytest.raises(ValidationError):
        _template(tools={"read": ["quote_history_kline"], "write": ["place_paper_order"]})
    with pytest.raises(ValidationError):
        _template(id="executor", tools={"read": ["sim_trade_position_list"], "write": []})


def test_allowed_tools_cannot_disagree_with_tools_block():
    with pytest.raises(ValidationError):
        _template(allowed_tools=["quote_history_kline", "sim_trade_input_order"])


def test_unknown_output_schema_fails_template_validation():
    with pytest.raises(ValidationError):
        _template(output_schema="MysterySignal")


def test_inventory_is_pinned():
    inventory = load_moomoo_inventory()
    assert len(inventory) == 104
    for name in ("quote_stock_quote", "quote_history_kline", "news_search",
                 "sim_trade_input_order", "trading_order_place"):
        assert name in inventory


def test_every_allowlisted_read_tool_exists_in_inventory():
    inventory = load_moomoo_inventory()
    for template in load_templates():
        for tool in template.tools.read:
            assert tool in inventory, (template.id, tool)


def test_allowed_tools_are_derived_from_tools_block():
    for template in load_templates():
        derived = template.tools.read + [
            WRITE_CAPABILITY_TOOLS[cap] for cap in template.tools.write
        ]
        assert template.allowed_tools == derived


def test_live_account_namespace_is_denied_for_every_agent():
    for agent_id in AGENT_IDS:
        for tool in ("account_positions", "account_funds", "mcp__moomoo__Account_Orders_Active"):
            verdict = policy.check_tool(agent_id, tool)
            assert not verdict.allowed
            assert verdict.code == policy.LIVE_TOOL_DENIED


def test_templates_cover_all_known_output_schemas():
    templates = load_templates()
    assert {t.output_schema for t in templates} >= {
        "RunRecord",
        "Dataset",
        "TechnicalSignal",
        "SentimentSignal",
        "RiskVerdict",
        "ExecutionRecord",
        "AuditReport",
    }
    assert all(t.input_schemas for t in templates)


def test_run_record_requires_halt_reason_when_aborted():
    ok = RunRecord(
        run_id="run-1",
        session_date=date(2026, 11, 19),
        strategy_version="v1",
        status="completed",
    )
    assert ok.per_name_status == []
    with pytest.raises(ValidationError):
        RunRecord(
            run_id="run-1",
            session_date=date(2026, 11, 19),
            strategy_version="v1",
            status="aborted",
            halt_reason=None,
        )


def test_universe_rejects_non_us_symbols_and_duplicates():
    universe = Universe(session_date=date(2026, 11, 19), symbols=["nvda", "AAPL"])
    assert universe.symbols == ["NVDA", "AAPL"]
    with pytest.raises(ValidationError):
        Universe(session_date=date(2026, 11, 19), symbols=["MY.1155"])
    with pytest.raises(ValidationError):
        Universe(session_date=date(2026, 11, 19), symbols=["AAPL", "AAPL"])


def _dataset(**overrides):
    base = dict(
        symbol="AAPL",
        quote=Quote(symbol="AAPL", price=200.0, ts=NOW, source="moomoo"),
        bars=[],
        age_s=5.0,
        source="moomoo",
        valid=True,
        deny_reason=None,
    )
    base.update(overrides)
    return Dataset(**base)


def test_dataset_freshness_and_deny_rules():
    assert _dataset().valid
    with pytest.raises(ValidationError):
        _dataset(age_s=61.0)
    with pytest.raises(ValidationError):
        _dataset(valid=False)
    denied = _dataset(valid=False, age_s=120.0, deny_reason="ENTITLEMENT_DENIED")
    assert denied.deny_reason == "ENTITLEMENT_DENIED"
    with pytest.raises(ValidationError):
        _dataset(deny_reason="STALE_QUOTE")
    with pytest.raises(ValidationError):
        _dataset(deny_reason="BECAUSE_I_SAID_SO", valid=False)


def test_technical_signal_insufficient_data_is_neutral():
    signal = TechnicalSignal(
        symbol="AAPL", features={"rsi_14": 55.0}, direction=Direction.UP,
        confidence=0.6, provenance=PROV,
    )
    assert signal.status == "ok"
    with pytest.raises(ValidationError):
        TechnicalSignal(
            symbol="AAPL", direction=Direction.UP, confidence=0.6,
            status="insufficient_data", provenance=PROV,
        )
    neutral = TechnicalSignal(
        symbol="AAPL", direction=Direction.NEUTRAL, confidence=0.0,
        status="insufficient_data", provenance=PROV,
    )
    assert neutral.confidence == 0.0
    with pytest.raises(ValidationError):
        TechnicalSignal(
            symbol="AAPL", direction=Direction.UP, confidence=1.5, provenance=PROV,
        )
    with pytest.raises(ValidationError):
        TechnicalSignal(symbol="AAPL", direction=Direction.UP, confidence=0.5, provenance=[])


def test_sentiment_zero_headlines_is_neutral():
    with pytest.raises(ValidationError):
        SentimentSignal(
            symbol="AAPL", score=0.4, n_headlines=0,
            direction=Direction.UP, confidence=0.5, provenance=PROV,
        )
    neutral = SentimentSignal(
        symbol="AAPL", score=0.0, n_headlines=0,
        direction=Direction.NEUTRAL, confidence=0.0, provenance=PROV,
    )
    assert neutral.score == 0.0


def test_risk_verdict_consistency():
    veto = RiskVerdict(approved=False, reasons=["STALE_QUOTE"], intent_hash="intent-1")
    assert veto.limits_hit == []
    with pytest.raises(ValidationError):
        RiskVerdict(approved=False, reasons=[], intent_hash="intent-1")
    with pytest.raises(ValidationError):
        RiskVerdict(approved=True, reasons=["STALE_QUOTE"], intent_hash="intent-1")
    with pytest.raises(ValidationError):
        RiskVerdict(approved=True, intent_hash="")


def test_execution_filled_requires_fills():
    with pytest.raises(ValidationError):
        ExecutionRecord(intent_id="intent-1", order_id="ord-1", status="filled", fills=[])
    filled = ExecutionRecord(
        intent_id="intent-1",
        order_id="ord-1",
        status="filled",
        fills=[Fill(qty=10, price=200.0, ts=NOW)],
    )
    assert filled.fills[0].qty == 10
    duplicate = ExecutionRecord(intent_id="intent-1", status="duplicate")
    assert duplicate.order_id == ""


def test_audit_report_requires_explicit_hash_chain():
    report = AuditReport(run_id="run-1", decisions=2, executions=2, hash_chain_ok=True)
    assert report.breaks == []
    with pytest.raises(ValidationError):
        AuditReport(run_id="run-1", decisions=1, executions=1)
