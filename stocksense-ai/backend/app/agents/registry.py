"""Load and validate the seven agent templates.

Templates are the single source of truth for each agent's tool allowlist and
artifact contract.  Loading fails at import time if a template is malformed,
duplicated, references an unknown handoff target, names a tool outside the
recorded moomoo inventory, or binds a write capability to the wrong agent — the
API must not boot with bad policy.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"
INVENTORY_PATH = Path(__file__).resolve().parent / "moomoo_tools.json"
MCP_TOOL_PREFIX = "mcp__moomoo__"

AGENT_IDS: tuple[str, ...] = (
    "supervisor",
    "data_steward",
    "technical",
    "news",
    "risk_reviewer",
    "executor",
    "auditor",
)

# Logical write capability -> the one moomoo tool that implements it.
WRITE_CAPABILITY_TOOLS: dict[str, str] = {
    "place_paper_order": "sim_trade_input_order",
    "cancel_paper_order": "sim_trade_cancel_order",
}

KNOWN_SCHEMAS: frozenset[str] = frozenset(
    {
        "Universe",
        "RunRecord",
        "Dataset",
        "TechnicalSignal",
        "SentimentSignal",
        "OrderIntent",
        "PortfolioSnapshot",
        "RiskVerdict",
        "ExecutionRecord",
        "AuditReport",
    }
)

ACCEPTANCE_HOOKS: frozenset[str] = frozenset(f"A{n}" for n in range(1, 13))

# Agents allowed to hold a write capability.  Only the Executor submits orders.
WRITE_AGENTS: frozenset[str] = frozenset({"executor"})


def normalize_tool(name: str) -> str:
    text = name.strip().lower()
    if text.startswith(MCP_TOOL_PREFIX):
        text = text[len(MCP_TOOL_PREFIX):]
    return text


@lru_cache
def load_moomoo_inventory() -> frozenset[str]:
    payload = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
    tools = [normalize_tool(t) for t in payload["tools"]]
    if len(tools) != len(set(tools)):
        raise RuntimeError("moomoo tool inventory contains duplicates")
    if payload["total"] != len(tools):
        raise RuntimeError(
            f"moomoo tool inventory declares {payload['total']} tools but lists {len(tools)}"
        )
    if any(t.startswith(MCP_TOOL_PREFIX) for t in tools):
        raise RuntimeError("moomoo tool inventory must use short names, not the MCP prefix")
    return frozenset(tools)


class Handoff(BaseModel):
    model_config = ConfigDict(extra="forbid")

    to: str
    when: str = Field(min_length=1)


class ToolPolicy(BaseModel):
    """Read tools plus logical write capabilities ([] means write: none)."""

    model_config = ConfigDict(extra="forbid")

    read: list[str] = Field(min_length=1)
    write: list[str] = Field(default_factory=list)

    @field_validator("read", "write")
    @classmethod
    def _stripped_unique(cls, v: list[str]) -> list[str]:
        cleaned = [normalize_tool(item) for item in v]
        if any(not item for item in cleaned):
            raise ValueError("tool entries must be non-empty")
        if len(cleaned) != len(set(cleaned)):
            raise ValueError("duplicate tool entries")
        return cleaned

    @field_validator("write")
    @classmethod
    def _known_write_capabilities(cls, v: list[str]) -> list[str]:
        unknown = [w for w in v if w not in WRITE_CAPABILITY_TOOLS]
        if unknown:
            raise ValueError(
                f"unknown write capabilities {unknown}; expected {sorted(WRITE_CAPABILITY_TOOLS)}"
            )
        return v


class AgentTemplate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str = Field(min_length=1)
    mission: str = Field(min_length=1)
    cadence: str = Field(min_length=1)
    tools: ToolPolicy
    input_schemas: list[str] = Field(min_length=1)
    output_schema: str
    outputs: list[str] = Field(min_length=1)
    hard_rules: list[str] = Field(min_length=1)
    failure: str = Field(min_length=1)
    acceptance_hook: list[str] = Field(min_length=1)
    handoffs: list[Handoff] = Field(default_factory=list)
    system_prompt: str = Field(min_length=1)
    # Derived from tools.read + bound write tools; accepted for API consumers.
    allowed_tools: list[str] = Field(default_factory=list)

    @field_validator("id")
    @classmethod
    def _known_id(cls, v: str) -> str:
        if v not in AGENT_IDS:
            raise ValueError(f"unknown agent id {v!r}; expected one of {AGENT_IDS}")
        return v

    @field_validator("input_schemas", "hard_rules", "outputs")
    @classmethod
    def _stripped_entries(cls, v: list[str]) -> list[str]:
        cleaned = [item.strip() for item in v]
        if any(not item for item in cleaned):
            raise ValueError("entries must be non-empty")
        return cleaned

    @field_validator("input_schemas")
    @classmethod
    def _known_input_schemas(cls, v: list[str]) -> list[str]:
        unknown = [s for s in v if s not in KNOWN_SCHEMAS]
        if unknown:
            raise ValueError(f"unknown input schemas {unknown}")
        return v

    @field_validator("output_schema")
    @classmethod
    def _known_output_schema(cls, v: str) -> str:
        if v not in KNOWN_SCHEMAS:
            raise ValueError(f"unknown output schema {v!r}")
        return v

    @field_validator("acceptance_hook")
    @classmethod
    def _known_hooks(cls, v: list[str]) -> list[str]:
        unknown = [h for h in v if h not in ACCEPTANCE_HOOKS]
        if unknown:
            raise ValueError(f"unknown acceptance hooks {unknown}")
        return v

    @model_validator(mode="after")
    def _derive_and_check_tools(self) -> "AgentTemplate":
        bound_writes = [WRITE_CAPABILITY_TOOLS[w] for w in self.tools.write]
        derived = self.tools.read + bound_writes
        if self.allowed_tools and self.allowed_tools != derived:
            raise ValueError(
                f"{self.id}: allowed_tools {self.allowed_tools} != derived {derived}"
            )
        self.allowed_tools = derived

        if self.tools.write and self.id not in WRITE_AGENTS:
            raise ValueError(f"{self.id}: write capability is reserved for {sorted(WRITE_AGENTS)}")
        if not self.tools.write and self.id in WRITE_AGENTS:
            raise ValueError(f"{self.id}: executor must bind its paper-order write capabilities")

        overlap = set(self.tools.read) & set(bound_writes)
        if overlap:
            raise ValueError(f"{self.id}: tools both read and written: {sorted(overlap)}")

        inventory = load_moomoo_inventory()
        unknown = [t for t in self.tools.read if t not in inventory]
        if unknown:
            raise ValueError(f"{self.id}: tools not in the moomoo inventory snapshot: {unknown}")
        return self


@lru_cache
def load_templates() -> tuple[AgentTemplate, ...]:
    paths = sorted(TEMPLATE_DIR.glob("*.yaml"))
    if not paths:
        raise RuntimeError(f"no agent templates found in {TEMPLATE_DIR}")

    templates = tuple(
        AgentTemplate.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
        for path in paths
    )

    ids = [t.id for t in templates]
    if len(ids) != len(set(ids)):
        raise RuntimeError(f"duplicate agent ids: {ids}")
    if set(ids) != set(AGENT_IDS):
        raise RuntimeError(f"template ids {sorted(ids)} != required {sorted(AGENT_IDS)}")

    for template in templates:
        for handoff in template.handoffs:
            if handoff.to not in AGENT_IDS:
                raise RuntimeError(f"{template.id} hands off to unknown agent {handoff.to!r}")

    order = {agent_id: index for index, agent_id in enumerate(AGENT_IDS)}
    return tuple(sorted(templates, key=lambda t: order[t.id]))


def get_template(agent_id: str) -> AgentTemplate | None:
    for template in load_templates():
        if template.id == agent_id:
            return template
    return None
