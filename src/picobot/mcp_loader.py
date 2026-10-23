"""Carica i server MCP da config/mcp_config.json (formato Claude Desktop)."""
import json
import logging
import shlex
from pathlib import Path

from agno.tools.mcp import MCPTools

logger = logging.getLogger(__name__)


async def load_mcp_tools(path: Path) -> list[MCPTools]:
    """Connette i server MCP; quelli che falliscono vengono saltati (il bot parte comunque)."""
    if not path.exists():
        logger.info("MCP: nessun file %s, salto.", path)
        return []
    try:
        servers = json.loads(path.read_text(encoding="utf-8")).get("mcpServers", {})
    except (OSError, json.JSONDecodeError) as e:
        logger.error("MCP: config non valida (%s): %s", path, e)
        return []

    connected: list[MCPTools] = []
    for name, cfg in servers.items():
        try:
            if "url" in cfg:
                tool = MCPTools(url=cfg["url"], name=name, transport=cfg.get("transport", "streamable-http"))
            else:
                command = shlex.join([cfg["command"], *cfg.get("args", [])])
                tool = MCPTools(command=command, name=name, env=cfg.get("env"), timeout_seconds=30)
            await tool.connect()
            if not tool.functions:  # connect() non solleva: 0 tool = connessione fallita
                raise RuntimeError("nessun tool esposto (connessione fallita?)")
            connected.append(tool)
            logger.info("MCP: server '%s' connesso (%d tool).", name, len(tool.functions))
        except Exception as e:  # noqa: BLE001
            logger.warning("MCP: server '%s' non disponibile, salto: %s", name, e)
    return connected


async def close_mcp_tools(tools: list[MCPTools]) -> None:
    for t in tools:
        try:
            await t.close()
        except Exception as e:  # noqa: BLE001
            logger.debug("MCP close: %s", e)
