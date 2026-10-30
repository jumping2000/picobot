# PicoBot documentation

🇬🇧 English · 🇮🇹 [Italiano](../it/index.md) · ⬅️ [README](../../README.md)

PicoBot v0.8 is a self-hosted, multi-agent personal assistant built on [Agno 3](https://github.com/agno-agi/agno).
It is reachable through Telegram, an interactive CLI and a REST API, all served by one process.

## Guides

| Page | What you will find |
|---|---|
| [Getting started](getting-started.md) | Requirements, Docker (prebuilt images or local build) and local installation, first run |
| [Configuration](configuration.md) | `.env` keys and `config/config.yaml` blocks, with precedence and defaults |
| [Architecture](architecture.md) | Router, teams, workflow, scheduler, data layout, request lifecycle |
| [Channels](channels.md) | Telegram and CLI: commands, documents, confirmations |
| [REST API](api.md) | Endpoints, payloads, examples, error codes |
| [Skills](skills.md) | Agent Skills format, installing from chat (`/skill_add`) and the admin CLI, Docker dependencies |
| [MCP](mcp.md) | Connecting Model Context Protocol servers |
| [Voice messages](voice.md) | Telegram voice notes and audio, the `stt` transcription container |
| [Memory](memory.md) | Memories, structured profile, entities, `/memory` and `/forget` |
| [Scheduler](scheduler.md) | Recurring cron tasks and their limits |
| [Security](security.md) | Threat model, sandbox, authentication, known limits |
| [Development](development.md) | Project layout, tests, extension points |
| [Troubleshooting](troubleshooting.md) | Common errors and how to fix them |

## Glossary

| Term | Meaning |
|---|---|
| **Router** | The top-level Agno team (`PicoBot`). It answers directly or delegates; it is the only agent that writes memories, profile and entities |
| **SimpleTeam** | Cheap-model team: Web, Finance, Coder |
| **ComplexTeam** | Strong-model team: Researcher, Analyst, Writer, Critic (optional), with skills and MCP |
| **DocSummary** | Agno workflow that summarizes an uploaded document |
| **Skill** | A folder in Agent Skills format (`SKILL.md` + optional scripts and references) |
| **Workspace** | `workspace/`: the only directory where generated code runs; delivered files come from `workspace/outputs/` |
| **Outbox** | `data/outbox/`: per-user copies of delivered files, downloadable from the API for 24 hours |
| **HITL** | Human-in-the-loop: every code execution needs explicit approval |

## Other documents

- [Manual acceptance checklist](manual-qa.md)
- [Changelog](../../CHANGELOG.md)
