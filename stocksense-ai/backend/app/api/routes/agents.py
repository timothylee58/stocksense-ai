"""Agent templates and the machine-checkable moomoo tool allowlist."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.agents.policy import check_tool, manifest
from app.agents.registry import load_templates, get_template

router = APIRouter()


class ToolCheckRequest(BaseModel):
    agent_id: str = Field(min_length=1, max_length=40)
    tool: str = Field(min_length=1, max_length=120)


@router.get("/agents")
async def list_agents():
    policy = manifest()
    agents = [
        {
            "id": t.id,
            "name": t.name,
            "cadence": t.cadence,
            "tools": t.tools.model_dump(),
            "allowed_tools": t.allowed_tools,
            "output_schema": t.output_schema,
            "acceptance_hook": t.acceptance_hook,
            "handoffs": [h.to for h in t.handoffs],
        }
        for t in load_templates()
    ]
    return {"count": len(agents), "manifest_sha256": policy["sha256"], "agents": agents}


@router.get("/agents/policy")
async def agent_policy():
    """Full allowlist manifest; pin the sha256 in an agent harness."""
    return manifest()


@router.post("/agents/check-tool")
async def check_agent_tool(body: ToolCheckRequest):
    """Allow/deny one tool call before it reaches the moomoo MCP server."""
    return check_tool(body.agent_id, body.tool).model_dump()


@router.get("/agents/{agent_id}")
async def get_agent(agent_id: str):
    template = get_template(agent_id)
    if template is None:
        raise HTTPException(status_code=404, detail=f"unknown agent {agent_id!r}")
    payload = template.model_dump()
    payload["manifest_sha256"] = manifest()["sha256"]
    return payload
