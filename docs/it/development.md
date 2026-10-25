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
├── stt/                  # servizio di trascrizione (FastAPI + faster-whisper), con pyproject e test propri
├── config/mcp_config.json
├── deps/                 # punti di estensione apt/pip/npm + setup.sh
├── docs/                 # questa documentazione (en/, it/), collaudo manuale, spec di design
├── .github/workflows/    # CI/CD (test, Docker build, GHCR)
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

## CI/CD

Workflow: [`.github/workflows/release_ci-cd.yml`](../../.github/workflows/release_ci-cd.yml).

| Job | Quando | Cosa fa |
|---|---|---|
| `prepare` | Sempre | Legge la versione; fallisce se `pyproject.toml`, `__init__.py` e il tag della release non coincidono |
| `test` | Sempre | pytest su Python 3.11, 3.12, 3.13 (con i pacchetti Node di `deps/npm.txt`) + smoke test della CLI |
| `docker-check` | Push su `main`, pull request | Build amd64 senza push + smoke test dell'immagine (Python, dipendenze Node e pip) |
| `build-docker` | Release pubblicata, avvio manuale | Scansione Trivy (repo), build multi-arch e push su GHCR, smoke test, scansione Trivy (immagine), SBOM, report allegati alla release |
| `notify` | Release, avvio manuale | Email con l'esito, **solo se** i secret SMTP sono configurati |

Immagine: `ghcr.io/jumping2000/picobot`. Tag: versione (`0.6.0`), minore (`0.6`), `sha-<commit>` e `latest` per
le release non prerelease.
Gli stessi job testano, controllano e pubblicano l'immagine di trascrizione `ghcr.io/jumping2000/picobot-stt`
(test: `uv run --directory stt --group dev pytest tests`).

Secret opzionali per l'email: `SMTP_SERVER`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `NOTIFICATION_EMAIL`.
Il push su GHCR usa il `GITHUB_TOKEN` integrato: non serve nessun altro secret.

> [!NOTE]
> Al primo push GitHub crea il pacchetto come **privato**. Per renderlo scaricabile da chiunque, apri la pagina del
> pacchetto (*Packages → picobot → Package settings*) e cambia la visibilità in pubblica.

## Versioni e release

La versione è definita in `pyproject.toml` e in `src/picobot/__init__.py` (`__version__`, esposta da `/health`).
Tienile allineate: la CI rifiuta di pubblicare se non coincidono.

Per fare una release:

1. Aggiorna la versione nei due file e fai commit su `main`.
2. Crea una release su GitHub con tag `v<versione>` (es. `v0.6.0`).
3. La CI pubblica l'immagine e allega `trivy-fs-report.txt`, `trivy-image-report.txt` e `sbom.spdx.json`.

Un avvio manuale (*Actions → PicoBot CI/CD Pipeline → Run workflow*) ricostruisce e pubblica la versione corrente
senza spostare `latest`.
