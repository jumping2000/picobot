# MCP servers

🇬🇧 English · 🇮🇹 [Italiano](../it/mcp.md) · ⬅️ [Index](index.md)

PicoBot connects [Model Context Protocol](https://modelcontextprotocol.io/) servers listed in
`config/mcp_config.json` (mounted read-only at `/app/config`). Each connected server is shared by **every member of
the ComplexTeam** (Researcher, Analyst, Writer, Critic).

## Format

Claude Desktop format, plus an optional `enabled` flag:

```json
{
  "mcpServers": {
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/app/workspace"]
    },
    "my-python-server": {
      "command": "uvx",
      "args": ["some-mcp-server"],
      "env": {"SOME_API_KEY": "${SOME_API_KEY}"},
      "enabled": false
    },
    "remote": {
      "url": "https://mcp.example.com/mcp",
      "transport": "streamable-http",
      "headers": {"X-API-Key": "${REMOTE_API_KEY}"}
    }
  }
}
```

| Key | Meaning |
|---|---|
| `command` + `args` | stdio server started as a subprocess (30 s timeout) |
| `env` | Extra environment variables for that server |
| `url` + `transport` | Remote server; `transport` defaults to `streamable-http` |
| `headers` | HTTP headers sent to a remote server (e.g. an API key) |
| `enabled` | `false` skips the server (default `true`) |

Keep secrets in `.env`, not in the JSON: write `${NAME}` in any string value and PicoBot replaces it with `NAME`
from `.env` (in the current directory, as for the other settings) or from the environment, which takes precedence.
Only the `${NAME}` form is supported. Put secrets in `headers` or `env`, not in `url`: connection errors are logged
with the URL. With an `http://` `url`, headers (keys included) travel in cleartext: use `https://` for remote
servers that need a secret, or keep them on a trusted network.

The image ships `npx` (Node servers) and `uvx` (Python servers).

## Behavior

- A server that references an undefined `${NAME}` is skipped with a warning naming the variable.
- Servers are connected at startup; **changes require a restart** (`docker compose restart picobot`).
- A server that fails or exposes no tools is skipped with a warning; the bot starts anyway.
- The log shows `MCP: server '<name>' connesso (N tool).` for every connected server; the startup line reports the
  total (`mcp=N`).
- An invalid JSON file disables MCP and logs an error.

> [!WARNING]
> **MCP tools do not ask for confirmation**, unlike generated code. A server with write access (filesystem, e-mail,
> databases) can act on the agents' decision alone. Configure only servers you trust, with minimal scope (the
> sample filesystem server only sees `/app/workspace`).
