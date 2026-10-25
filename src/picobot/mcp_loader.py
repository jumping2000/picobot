"""Carica i server MCP da config/mcp_config.json (formato Claude Desktop, piu' il flag opzionale "enabled").

Un MCPTools per server, condiviso da tutti i membri del ComplexTeam. Le modifiche richiedono il riavvio.
I segreti restano in .env: nel JSON si scrivono come ${NOME} (valore da .env o dall'ambiente).
"""
import json
import logging
import os
import re
import shlex
from pathlib import Path

from agno.tools.mcp import MCPTools
from dotenv import dotenv_values

logger = logging.getLogger(__name__)
_VAR = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


def _expand(value, env: dict):
    """Sostituisce ${NOME} in tutte le stringhe della config di un server."""
    if isinstance(value, str):
        def sub(m: re.Match) -> str:
            if env.get(m.group(1)) is None:
                raise ValueError(f"variabile d'ambiente {m.group(1)} non definita")
            return env[m.group(1)]
        return _VAR.sub(sub, value)
    if isinstance(value, list):
        return [_expand(v, env) for v in value]
    if isinstance(value, dict):
        return {k: _expand(v, env) for k, v in value.items()}
    return value


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

    env = {**dotenv_values(".env"), **os.environ}  # come Settings: .env della cartella corrente, l'ambiente vince
    connected: list[MCPTools] = []
    for name, cfg in servers.items():
        if not cfg.get("enabled", True):
            logger.info("MCP: server '%s' disabilitato (enabled=false), salto.", name)
            continue
        try:
            cfg = _expand(cfg, env)
            if "url" in cfg:
                tool = MCPTools(url=cfg["url"], name=name, transport=cfg.get("transport", "streamable-http"),
                                headers=cfg.get("headers"))
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
