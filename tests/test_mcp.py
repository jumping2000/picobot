"""MCP: flag enabled, server rotti saltati, un server condiviso da tutti i membri del ComplexTeam."""

import asyncio
import json
import sys
from pathlib import Path

import fake_llm
import pytest

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
    cfg = write_cfg(
        tmp_path,
        {
            "probe": {"command": sys.executable, "args": [PROBE]},
            "rotto": {"command": "comando-inesistente-xyz"},
            "off": {"command": sys.executable, "args": [PROBE], "enabled": False},
        },
    )

    async def go():
        tools = await load_mcp_tools(cfg)
        try:
            return [(t.name, list(t.functions)) for t in tools]
        finally:
            await close_mcp_tools(tools)

    assert asyncio.run(go()) == [("probe", ["add"])]


def test_all_complexteam_members_call_shared_mcp(tmp_path):
    s = Settings(
        skills_dir=tmp_path / "skills",
        data_dir=tmp_path / "data",
        workspace_dir=tmp_path / "ws",
    )
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
                results[member.name] = [
                    m["content"]
                    for b in fake_llm.LOG
                    for m in b["messages"]
                    if m["role"] == "tool"
                ]
            return results
        finally:
            await close_mcp_tools(tools)

    results = asyncio.run(go())
    assert set(results) == {"Researcher", "Analyst", "Writer", "Critic"}
    assert all(any("5" in str(r) for r in res) for res in results.values()), results


class FakeMCPTools:  # sostituisce la connessione reale: registra cosa riceve dal loader
    def __init__(self, **kw):
        self.kw, self.name, self.functions = kw, kw["name"], {"f": None}

    async def connect(self):
        pass

    async def close(self):
        pass


def load_with_fake(monkeypatch, cfg):
    monkeypatch.setattr("picobot.mcp_loader.MCPTools", FakeMCPTools)
    return {t.name: t.kw for t in asyncio.run(load_mcp_tools(cfg))}


def test_http_server_gets_headers_with_secret_from_env(monkeypatch, tmp_path):
    monkeypatch.setenv("LLMBASE_API_KEY", "s3cret")
    cfg = write_cfg(tmp_path, {"llmbase": {"url": "http://h:5555/mcp/",
                                           "headers": {"X-API-Key": "${LLMBASE_API_KEY}"}}})
    kw = load_with_fake(monkeypatch, cfg)["llmbase"]
    assert (kw["url"], kw["headers"]) == ("http://h:5555/mcp/", {"X-API-Key": "s3cret"})


def test_stdio_server_env_and_args_expanded(monkeypatch, tmp_path):
    monkeypatch.setenv("TOK", "abc")
    cfg = write_cfg(tmp_path, {"s": {"command": "srv", "args": ["--token=${TOK}"], "env": {"K": "${TOK}"}}})
    kw = load_with_fake(monkeypatch, cfg)["s"]
    assert (kw["command"], kw["env"]) == ("srv --token=abc", {"K": "abc"})


def test_missing_env_var_skips_only_that_server(monkeypatch, tmp_path, caplog):
    monkeypatch.delenv("MANCA_XYZ", raising=False)
    cfg = write_cfg(tmp_path, {"senza": {"url": "http://h/mcp", "headers": {"X-API-Key": "${MANCA_XYZ}"}},
                               "ok": {"url": "http://h2/mcp"}})
    assert list(load_with_fake(monkeypatch, cfg)) == ["ok"]
    assert "MANCA_XYZ" in caplog.text


def test_secret_read_from_dotenv_like_settings(monkeypatch, tmp_path):  # anche fuori da Docker
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SOLO_IN_DOTENV", raising=False)
    (tmp_path / ".env").write_text("SOLO_IN_DOTENV=dal-file\n")
    cfg = write_cfg(tmp_path, {"r": {"url": "http://h/mcp", "headers": {"X-API-Key": "${SOLO_IN_DOTENV}"}}})
    assert load_with_fake(monkeypatch, cfg)["r"]["headers"] == {"X-API-Key": "dal-file"}
