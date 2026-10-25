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
      "env": {"QUALCHE_API_KEY": "${QUALCHE_API_KEY}"},
      "enabled": false
    },
    "remoto": {
      "url": "https://mcp.example.com/mcp",
      "transport": "streamable-http",
      "headers": {"X-API-Key": "${REMOTO_API_KEY}"}
    }
  }
}
```

| Chiave | Significato |
|---|---|
| `command` + `args` | Server stdio avviato come sottoprocesso (timeout 30 s) |
| `env` | Variabili d'ambiente aggiuntive per quel server |
| `url` + `transport` | Server remoto; `transport` di default è `streamable-http` |
| `headers` | Header HTTP inviati a un server remoto (es. una chiave API) |
| `enabled` | `false` salta il server (default `true`) |

I segreti stanno in `.env`, non nel JSON: in qualsiasi stringa scrivi `${NOME}` e PicoBot lo sostituisce con `NOME`
preso dal `.env` (nella cartella corrente, come le altre impostazioni) o dall'ambiente, che ha la precedenza. È
supportata solo la forma `${NOME}`. Metti i segreti in `headers` o `env`, non nell'`url`: gli errori di connessione
finiscono nel log insieme all'URL. Con un `url` `http://` gli header, chiavi comprese, viaggiano in chiaro: per i
server remoti con un segreto usa `https://`, oppure tienili su una rete fidata.

Nell'immagine ci sono `npx` (server Node) e `uvx` (server Python).

## Comportamento

- Un server che usa una `${NOME}` non definita viene saltato con un avviso che riporta il nome della variabile.
- I server vengono connessi all'avvio; **le modifiche richiedono il riavvio** (`docker compose restart picobot`).
- Un server che fallisce o non espone tool viene saltato con un avviso; il bot parte comunque.
- Nel log compare `MCP: server '<nome>' connesso (N tool).` per ogni server connesso; la riga di avvio riporta il
  totale (`mcp=N`).
- Un file JSON non valido disattiva MCP e registra un errore.

> [!WARNING]
> **I tool MCP non chiedono conferma**, a differenza del codice generato. Un server con accesso in scrittura
> (filesystem, e-mail, database) può agire sulla sola decisione degli agenti. Configura solo server fidati, con il
> perimetro minimo (il server filesystem di esempio vede solo `/app/workspace`).
