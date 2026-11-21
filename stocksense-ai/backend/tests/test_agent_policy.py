"""Round 2 — machine-checkable agent tool allowlist and templates."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.agents import policy
from app.agents.registry import AGENT_IDS, load_templates
from app.api.routes import agents as agents_route


def _client():
    app = FastAPI()
    app.include_router(agents_route.router, prefix="/api")
    return TestClient(app)


def test_all_seven_templates_load():
    templates = load_templates()
    assert tuple(t.id for t in templates) == AGENT_IDS
    for template in templates:
        assert template.allowed_tools
        assert any("simulate" in g.lower() or "paper" in g.lower() for g in template.hard_rules)
        assert template.system_prompt.strip()
        assert template.failure.strip()
        assert template.acceptance_hook


def test_every_agent_denies_live_tools():
    for agent_id in AGENT_IDS:
        for tool in policy.LIVE_DENY_EXAMPLES + (
            "trading_anything",
            "crypto_anything",
            "grid_anything",
            "mcp__moomoo__Trading_Order_Place",
        ):
            verdict = policy.check_tool(agent_id, tool)
            assert not verdict.allowed, (agent_id, tool)
            assert verdict.code == policy.LIVE_TOOL_DENIED


def test_executor_is_the_only_order_sender():
    for agent_id in AGENT_IDS:
        verdict = policy.check_tool(agent_id, "sim_trade_input_order")
        if agent_id == "executor":
            assert verdict.allowed and verdict.code == policy.ALLOWED
        else:
            assert not verdict.allowed and verdict.code == policy.NOT_IN_ALLOWLIST


def test_read_only_sim_tools_are_scoped():
    for agent_id in ("risk_reviewer", "auditor"):
        assert policy.check_tool(agent_id, "sim_trade_position_list").allowed
        assert policy.check_tool(agent_id, "sim_trade_history_order_list").allowed
    assert not policy.check_tool("risk_reviewer", "sim_trade_input_order").allowed
    assert not policy.check_tool("technical", "sim_trade_position_list").allowed


def test_default_deny_for_unknown_agent_and_tool():
    assert policy.check_tool("intruder", "quote_x").code == policy.UNKNOWN_AGENT
    verdict = policy.check_tool("executor", "quote_get_stock_quote")
    assert not verdict.allowed and verdict.code == policy.NOT_IN_ALLOWLIST


def test_tool_name_normalisation():
    assert policy.check_tool("executor", "MCP__MOOMOO__sim_trade_input_order").allowed
    assert policy.check_tool("technical", "  Quote_History_Kline  ").allowed


@pytest.mark.parametrize(
    "pattern", ["trading_*", "tr*", "crypto*", "*", "", "grid_", "account_*", "ac*"]
)
def test_unsafe_patterns_are_rejected(pattern):
    with pytest.raises(RuntimeError):
        policy._assert_pattern_safe("executor", pattern)


def test_manifest_is_deterministic_and_hashed():
    first = policy.manifest()
    second = policy.manifest()
    assert first == second
    assert len(first["sha256"]) == 64
    assert set(first["agents"]) == set(AGENT_IDS)
    assert first["deny_prefixes"] == list(policy.LIVE_DENY_PREFIXES)
    assert first["write_capabilities"] == {
        "place_paper_order": "sim_trade_input_order",
        "cancel_paper_order": "sim_trade_cancel_order",
    }
    assert first["agents"]["executor"]["write"] == first["write_capabilities"]
    for agent_id, entry in first["agents"].items():
        if agent_id != "executor":
            assert entry["write"] == {}


def test_only_executor_holds_write_capabilities():
    for template in load_templates():
        if template.id == "executor":
            assert set(template.tools.write) == {"place_paper_order", "cancel_paper_order"}
            assert "sim_trade_input_order" in template.allowed_tools
            assert "sim_trade_cancel_order" in template.allowed_tools
        else:
            assert template.tools.write == []
            assert not any(
                tool in ("sim_trade_input_order", "sim_trade_cancel_order")
                for tool in template.allowed_tools
            )


def test_acceptance_hooks_match_the_agent_contract():
    assert {t.id: t.acceptance_hook for t in load_templates()} == {
        "supervisor": ["A4", "A7"],
        "data_steward": ["A1", "A2"],
        "technical": ["A7"],
        "news": ["A3"],
        "risk_reviewer": ["A5", "A9"],
        "executor": ["A6", "A9"],
        "auditor": ["A8", "A10"],
    }


def test_agents_endpoints():
    client = _client()

    listed = client.get("/api/agents").json()
    assert listed["count"] == 7
    assert listed["manifest_sha256"] == policy.manifest()["sha256"]

    manifest = client.get("/api/agents/policy").json()
    assert manifest["sha256"] == listed["manifest_sha256"]

    allowed = client.post(
        "/api/agents/check-tool",
        json={"agent_id": "executor", "tool": "sim_trade_input_order"},
    ).json()
    assert allowed["allowed"] is True and allowed["code"] == policy.ALLOWED

    denied = client.post(
        "/api/agents/check-tool",
        json={"agent_id": "executor", "tool": "trading_order_place"},
    ).json()
    assert denied["allowed"] is False and denied["code"] == policy.LIVE_TOOL_DENIED

    detail = client.get("/api/agents/executor").json()
    assert detail["id"] == "executor"
    assert detail["manifest_sha256"] == listed["manifest_sha256"]
    assert client.get("/api/agents/nobody").status_code == 404
