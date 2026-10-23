# Sviluppo

🇮🇹 Italiano · 🇬🇧 [English](../en/development.md) · ⬅️ [Indice](index.md)

## Ambiente

```bash
uv sync --group dev
```

Python ≥ 3.11. Dipendenze principali: `agno>=3.1,<4`, `python-telegram-bot==21.10`, `fastapi`, `uvicorn`,
`apscheduler>=3.10,<4`, `fastmcp>=4,<5`, `yfinance`, `ddgs`, `pypdf`, `python-docx`
(vedi [`pyproject.toml`](../../pyproject.toml)).

## Test

```bash
uv run --group dev pytest tests            # tutti
uv run --group dev pytest tests/test_teams.py -q
```

La suite usa un **LLM finto** ([`tests/fake_llm.py`](../../tests/fake_llm.py)): nessuna chiave API e nessuna
chiamata di rete verso i provider dei modelli.

| File | Area |
|---|---|
| `test_core.py` | Costo in chiamate, modello economico e forte, conferma del codice |
| `test_teams.py`, `test_explicit.py` | Struttura e prompt dei team, richiamo esplicito (`target`) |
| `test_learning.py` | Profilo, entità, viste in sola lettura, `/memory` e `/forget` |
| `test_privacy.py` | Telemetria di Agno spenta di default |
| `test_channels.py` | Autenticazione API, validazione, upload, isolamento per utente; Telegram fail-closed |
| `test_files.py`, `test_documents_tools.py` | Consegna dei file e rifiuti, tool sui documenti |
| `test_sandbox_node.py` | Esecuzione Node, ambiente ripulito, tetto di esecuzioni |
| `test_skills.py`, `test_skills_cli.py` | Registro delle skill e CLI di amministrazione |
| `test_mcp.py` (+ `mcp_probe_server.py`) | Caricamento MCP |
| `test_e2e_office.py` | End to end: documento → router → ComplexTeam → file |
| `test_docker_static.py` | Controlli statici su Dockerfile e compose |
| `test_context_config.py` | Impostazioni |

Collaudo manuale con un modello reale: [manual-qa.md](../manual-qa.md).

## Struttura del progetto

```
picobot/
├── src/picobot/          # pacchetto dell'applicazione (vedi architecture.md → Mappa dei sorgenti)
├── tests/                # suite pytest con LLM finto
├── config/mcp_config.json
├── deps/                 # punti di estensione apt/pip/npm + setup.sh
├── docs/                 # questa documentazione (en/, it/), collaudo manuale, spec di design
├── Dockerfile, docker-compose.yaml, .env.example
└── pyproject.toml
```

## Estendere

| Obiettivo | Dove |
|---|---|
| Cambiare il comportamento di un agente | [`prompts.py`](../../src/picobot/prompts.py) (solo testo) |
| Aggiungere un membro o un tool a un team | [`agents.py`](../../src/picobot/agents.py) |
| Nuovo canale | Costruisci un `RunCtx` e chiama `PicoBotService.ask()`; l'esempio più piccolo è `channels/cli.py` |
| Nuova capacità senza codice | Una [skill](skills.md) o un [server MCP](mcp.md) |
| Nuova libreria di sistema/Python/Node | `deps/*.txt`, poi ricostruisci l'immagine |
| Nuova impostazione | Campo in `Settings` ([`config.py`](../../src/picobot/config.py)) + `.env.example` + [configuration.md](configuration.md) |

Convenzioni del codice: commenti e messaggi per l'utente sono in italiano; i tool che eseguono codice devono passare
da `_execute()` in `tools/sandbox.py`, che applica conferma e limiti.

## Immagine Docker

Passi della build ([`Dockerfile`](../../Dockerfile)):

1. `python:3.11-slim` + Node.js, npm, curl; `uv`/`uvx` copiati da `ghcr.io/astral-sh/uv`.
2. Dipendenze del bot (layer in cache, solo metadati).
3. Punti di estensione: `deps/apt.txt` → `deps/pip.txt` → `deps/npm.txt` (fallisce se `NODE_PATH` ≠ `npm root -g`) → `deps/setup.sh`.
4. Codice sorgente, utente non root `picobot` (UID 1000); scrivibili solo `data/` e `workspace/`.
5. `HEALTHCHECK` su `/health`; comando `python -m picobot serve`.

## Versioni

La versione è definita in `pyproject.toml` e in `src/picobot/__init__.py` (`__version__`, esposta da `/health`).
Tienile allineate.
