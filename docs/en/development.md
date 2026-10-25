# Development

🇬🇧 English · 🇮🇹 [Italiano](../it/development.md) · ⬅️ [Index](index.md)

## Setup

```bash
uv sync --group dev
```

Python ≥ 3.11. Main dependencies: `agno>=3.1,<4`, `python-telegram-bot==21.10`, `fastapi`, `uvicorn`,
`apscheduler>=3.10,<4`, `fastmcp>=4,<5`, `yfinance`, `ddgs`, `pypdf`, `python-docx`
(see [`pyproject.toml`](../../pyproject.toml)).

## Tests

```bash
uv run --group dev pytest tests            # all
uv run --group dev pytest tests/test_teams.py -q
```

The suite uses a **fake LLM** ([`tests/fake_llm.py`](../../tests/fake_llm.py)): no API key and no network calls to
model providers.

| File | Area |
|---|---|
| `test_core.py` | Call cost, cheap vs strong model, code confirmation gate |
| `test_teams.py`, `test_explicit.py` | Team structure and prompts, explicit routing (`target`) |
| `test_learning.py` | Profile, entities, read-only views, `/memory` and `/forget` |
| `test_privacy.py` | Agno telemetry off by default |
| `test_channels.py` | API auth, validation, uploads, per-user isolation; Telegram fail-closed |
| `test_files.py`, `test_documents_tools.py` | File delivery and its refusals, document tools |
| `test_sandbox_node.py` | Node execution, clean env, run cap |
| `test_skills.py`, `test_skills_cli.py` | Skill registry and admin CLI |
| `test_mcp.py` (+ `mcp_probe_server.py`) | MCP loading |
| `test_e2e_office.py` | End to end: document → router → ComplexTeam → file |
| `test_docker_static.py` | Static checks on Dockerfile and compose |
| `test_context_config.py` | Settings |

Manual acceptance checklist with a real model: [manual-qa.md](manual-qa.md).

## Project layout

```
picobot/
├── src/picobot/          # application package (see architecture.md → Source map)
├── tests/                # pytest suite with fake LLM
├── stt/                  # transcription service (FastAPI + faster-whisper), own pyproject and tests
├── config/mcp_config.json
├── deps/                 # apt/pip/npm extension points + setup.sh
├── docs/                 # this documentation (en/, it/), manual QA, design specs
├── .github/workflows/    # CI/CD (test, Docker build, GHCR)
├── Dockerfile, docker-compose.yaml, .env.example
└── pyproject.toml
```

## Extending

| Goal | Where |
|---|---|
| Change an agent's behavior | [`prompts.py`](../../src/picobot/prompts.py) (text only) |
| Add a member or tool to a team | [`agents.py`](../../src/picobot/agents.py) |
| New channel | Build a `RunCtx` and call `PicoBotService.ask()` — see `channels/cli.py` for the smallest example |
| New capability without code | A [skill](skills.md) or an [MCP server](mcp.md) |
| New system/Python/Node library | `deps/*.txt`, then rebuild |
| New setting | Field in `Settings` ([`config.py`](../../src/picobot/config.py)) + `.env.example` + [configuration.md](configuration.md) |

Conventions in the codebase: code comments and user-facing strings are in Italian; tools that run code must go
through `_execute()` in `tools/sandbox.py`, which enforces confirmation and limits.

## Docker image

Build steps ([`Dockerfile`](../../Dockerfile)):

1. `python:3.11-slim` + Node.js, npm, curl; `uv`/`uvx` copied from `ghcr.io/astral-sh/uv`.
2. Bot dependencies (cached layer, metadata only).
3. Extension points: `deps/apt.txt` → `deps/pip.txt` → `deps/npm.txt` (fails if `NODE_PATH` ≠ `npm root -g`) → `deps/setup.sh`.
4. Source code, non-root user `picobot` (UID 1000); only `data/` and `workspace/` are writable.
5. `HEALTHCHECK` on `/health`; command `python -m picobot serve`.

## CI/CD

Workflow: [`.github/workflows/release_ci-cd.yml`](../../.github/workflows/release_ci-cd.yml).

| Job | When | What |
|---|---|---|
| `prepare` | Always | Reads the version; fails if `pyproject.toml`, `__init__.py` and the release tag disagree |
| `test` | Always | pytest on Python 3.11, 3.12, 3.13 (with the Node packages of `deps/npm.txt`) + CLI smoke test |
| `docker-check` | Push to `main`, pull request | amd64 build without push + smoke test of the image (Python, Node and pip deps) |
| `build-docker` | Release published, manual run | Trivy scan (repo), multi-arch build and push to GHCR, smoke test, Trivy scan (image), SBOM, reports attached to the release |
| `notify` | Release, manual run | E-mail with the result, **only if** the SMTP secrets are set |

Image: `ghcr.io/jumping2000/picobot`. Tags: version (`0.6.0`), minor (`0.6`), `sha-<commit>`, and `latest` for
non-prerelease releases.
The same jobs test, check and publish the transcription image `ghcr.io/jumping2000/picobot-stt` (tests:
`uv run --directory stt --group dev pytest tests`).

Optional secrets for the e-mail: `SMTP_SERVER`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `NOTIFICATION_EMAIL`.
Pushing to GHCR uses the built-in `GITHUB_TOKEN`; no extra secret is needed.

> [!NOTE]
> On the first push, GitHub creates the package as **private**. To let anyone pull it, open the package page
> (*Packages → picobot → Package settings*) and change the visibility to public.

## Versioning and releases

The version is defined in `pyproject.toml` and `src/picobot/__init__.py` (`__version__`, exposed by `/health`).
Keep them aligned: CI refuses to publish if they disagree.

To release:

1. Update the version in both files and commit to `main`.
2. Create a GitHub release with tag `v<version>` (e.g. `v0.6.0`).
3. CI publishes the image and attaches `trivy-fs-report.txt`, `trivy-image-report.txt` and `sbom.spdx.json`.

A manual run (*Actions → PicoBot CI/CD Pipeline → Run workflow*) rebuilds and pushes the current version without
moving `latest`.
