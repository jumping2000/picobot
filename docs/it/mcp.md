# Server MCP

🇮🇹 Italiano · 🇬🇧 [English](../en/mcp.md) · ⬅️ [Indice](index.md)

PicoBot collega i server [Model Context Protocol](https://modelcontextprotocol.io/) elencati in
`config/mcp_config.json` (montato in sola lettura su `/app/config`). Ogni server connesso è condiviso da **tutti i
membri del ComplexTeam** (Researcher, Analyst, Writer, Critic).

## Formato

Formato Claude Desktop, più il flag opzionale `enabled`:

```json
{
  "mcpServers": {
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/app/workspace"]
    },
    "mio-server-python": {
      "command": "uvx",
      "args": ["qualche-server-mcp"],
      "env": {"QUALCHE_API_KEY": "..."},
      "enabled": false
    },
    "remoto": {
      "url": "https://mcp.example.com/mcp",
      "transport": "streamable-http"
    }
  }
}
```

| Chiave | Significato |
|---|---|
| `command` + `args` | Server stdio avviato come sottoprocesso (timeout 30 s) |
| `env` | Variabili d'ambiente aggiuntive per quel server |
| `url` + `transport` | Server remoto; `transport` di default è `streamable-http` |
| `enabled` | `false` salta il server (default `true`) |

Nell'immagine ci sono `npx` (server Node) e `uvx` (server Python).

## Comportamento

- I server vengono connessi all'avvio; **le modifiche richiedono il riavvio** (`docker compose restart picobot`).
- Un server che fallisce o non espone tool viene saltato con un avviso; il bot parte comunque.
- Nel log compare `MCP: server '<nome>' connesso (N tool).` per ogni server connesso; la riga di avvio riporta il
  totale (`mcp=N`).
- Un file JSON non valido disattiva MCP e registra un errore.

> [!WARNING]
> **I tool MCP non chiedono conferma**, a differenza del codice generato. Un server con accesso in scrittura
> (filesystem, e-mail, database) può agire sulla sola decisione degli agenti. Configura solo server fidati, con il
> perimetro minimo (il server filesystem di esempio vede solo `/app/workspace`).
