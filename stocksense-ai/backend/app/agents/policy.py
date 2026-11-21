"""Machine-checkable agent tool allowlist.

Rules are deliberately simple so a reviewer (or another program) can replay them:

1. A tool is denied if its normalised name starts with any live prefix
   (``trading_``, ``crypto_``, ``grid_``, ``account_``).  Deny always wins.
   ``account_*`` is the live brokerage account namespace; agents may only use
   the ``sim_trade_*`` paper tools.
2. Otherwise a tool is allowed only if it matches one of the agent's patterns.
   Patterns are exact names or a trailing ``*`` prefix wildcard.
3. Unknown agents and unmatched tools are denied (default-deny).

Allowlists come from the agent templates.  Importing this module validates
every template's allowlist and raises ``RuntimeError`` if a pattern could reach
the live namespace, so the API cannot boot with an unsafe policy.
"""
from __future__ import annotations

import hashlib
import json

from pydantic import BaseModel

from app.agents.registry import (
    MCP_TOOL_PREFIX,
    WRITE_CAPABILITY_TOOLS,
    AgentTemplate,
    load_templates,
    normalize_tool,
)

LIVE_DENY_PREFIXES: tuple[str, ...] = ("trading_", "crypto_", "grid_", "account_")
LIVE_DENY_EXAMPLES: tuple[str, ...] = (
    "trading_order_place",
    "trading_order_cancel",
    "trading_order_replace",
    "crypto_order_place",
    "grid_strategy_start",
    "account_positions",
    "account_funds",
)

ALLOWED = "ALLOWED"
LIVE_TOOL_DENIED = "LIVE_TOOL_DENIED"
NOT_IN_ALLOWLIST = "NOT_IN_ALLOWLIST"
UNKNOWN_AGENT = "UNKNOWN_AGENT"


class ToolVerdict(BaseModel):
    agent_id: str
    tool: str
    allowed: bool
    code: str


def is_live_tool(name: str) -> bool:
    tool = normalize_tool(name)
    return any(tool.startswith(prefix) for prefix in LIVE_DENY_PREFIXES)


def _pattern_matches(tool: str, pattern: str) -> bool:
    pat = normalize_tool(pattern)
    if pat.endswith("*"):
        return tool.startswith(pat[:-1])
    return tool == pat


def _assert_pattern_safe(agent_id: str, pattern: str) -> None:
    pat = normalize_tool(pattern)
    literal = pat[:-1] if pat.endswith("*") else pat
    if not literal or pat == "*":
        raise RuntimeError(f"{agent_id}: wildcard allowlist entry {pattern!r} is forbidden")
    for deny in LIVE_DENY_PREFIXES:
        # Both directions: the pattern may name the deny prefix, or be broad
        # enough (e.g. "tr*") to cover it.
        if literal.startswith(deny) or deny.startswith(literal):
            raise RuntimeError(
                f"{agent_id}: allowlist pattern {pattern!r} can reach live tool namespace {deny!r}"
            )


def _build_allowlists(templates: tuple[AgentTemplate, ...]) -> dict[str, tuple[str, ...]]:
    allowlists: dict[str, tuple[str, ...]] = {}
    for template in templates:
        for pattern in template.allowed_tools:
            _assert_pattern_safe(template.id, pattern)
        allowlists[template.id] = tuple(template.allowed_tools)
    return allowlists


ALLOWLISTS: dict[str, tuple[str, ...]] = _build_allowlists(load_templates())


def check_tool(agent_id: str, tool: str) -> ToolVerdict:
    """Decide whether one agent may call one tool. Pure function."""
    if agent_id not in ALLOWLISTS:
        return ToolVerdict(agent_id=agent_id, tool=tool, allowed=False, code=UNKNOWN_AGENT)

    name = normalize_tool(tool)
    if is_live_tool(name):
        return ToolVerdict(agent_id=agent_id, tool=tool, allowed=False, code=LIVE_TOOL_DENIED)

    if any(_pattern_matches(name, pattern) for pattern in ALLOWLISTS[agent_id]):
        return ToolVerdict(agent_id=agent_id, tool=tool, allowed=True, code=ALLOWED)

    return ToolVerdict(agent_id=agent_id, tool=tool, allowed=False, code=NOT_IN_ALLOWLIST)


def manifest() -> dict:
    """Deterministic policy manifest with a content hash other systems can pin."""
    agents = {
        template.id: {
            "name": template.name,
            "allow": list(template.allowed_tools),
            "write": {
                cap: WRITE_CAPABILITY_TOOLS[cap] for cap in template.tools.write
            },
            "output_schema": template.output_schema,
            "acceptance_hook": list(template.acceptance_hook),
        }
        for template in load_templates()
    }
    payload: dict = {
        "schema_version": 2,
        "source": "moomoo",
        "tool_prefix": MCP_TOOL_PREFIX,
        "deny_prefixes": list(LIVE_DENY_PREFIXES),
        "deny_examples": list(LIVE_DENY_EXAMPLES),
        "write_capabilities": dict(WRITE_CAPABILITY_TOOLS),
        "agents": agents,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    payload["sha256"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return payload
