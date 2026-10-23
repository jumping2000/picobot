"""MCP: flag enabled, server rotti saltati, un server condiviso da tutti i membri del ComplexTeam."""
import asyncio
import json
import sys
from pathlib import Path

import pytest

import fake_llm
from picobot.agents import build_complex_team
from picobot.config import Settings
from picobot.mcp_loader import close_mcp_tools, load_mcp_tools
from picobot.skills import SkillRegistry

pytest.importorskip("fastmcp")
PROBE = str(Path(__file__).with_name("mcp_probe_server.py"))


def write_cfg(tmp_path, servers):
    p = tmp_path / "mcp.json"
    p.write_text(json.dumps({"mcpServers": servers}))
    return p


def test_loader_enabled_and_broken_skipped(tmp_path):
    cfg = write_cfg(tmp_path, {
        "probe": {"command": sys.executable, "args": [PROBE]},
        "rotto": {"command": "comando-inesistente-xyz"},
        "off": {"command": sys.executable, "args": [PROBE], "enabled": False},
    })

    async def go():
        tools = await load_mcp_tools(cfg)
        try:
            return [(t.name, list(t.functions)) for t in tools]
        finally:
            await close_mcp_tools(tools)
    assert asyncio.run(go()) == [("probe", ["add"])]


def test_all_complexteam_members_call_shared_mcp(tmp_path):
    s = Settings(skills_dir=tmp_path / "skills", data_dir=tmp_path / "data", workspace_dir=tmp_path / "ws")
    cfg = write_cfg(tmp_path, {"probe": {"command": sys.executable, "args": [PROBE]}})

    async def go():
        tools = await load_mcp_tools(cfg)
        assert len(tools) == 1
        try:
            ct = build_complex_team(s, SkillRegistry(s), mcp_tools=tools)
            results = {}
            for member in ct.members:
                fake_llm.LOG.clear()
                await member.arun("somma 2 e 3")
                results[member.name] = [m["content"] for b in fake_llm.LOG for m in b["messages"] if m["role"] == "tool"]
            return results
        finally:
            await close_mcp_tools(tools)
    results = asyncio.run(go())
    assert set(results) == {"Researcher", "Analyst", "Writer", "Critic"}
    assert all(any("5" in str(r) for r in res) for res in results.values()), results
