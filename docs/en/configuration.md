# Configuration

🇬🇧 English · 🇮🇹 [Italiano](../it/configuration.md) · ⬅️ [Index](index.md)

PicoBot reads its settings from environment variables or from `.env` (via `pydantic-settings`, case-insensitive).
Source of truth: [`src/picobot/config.py`](../../src/picobot/config.py). Booleans accept `true`/`false`.

## LLM

| Variable | Default | Description |
|---|---|---|
| `OPENROUTER_API_KEY` | — | API key. **Required** (or `OPENAI_API_KEY`) |
| `OPENAI_API_KEY` | — | Used only if `OPENROUTER_API_KEY` is empty |
| `OPENROUTER_BASE_URL` | `https://openrouter.ai/api/v1` | OpenAI-compatible endpoint |
| `LLM_MODEL_ID` | `openai/gpt-4o-mini` | Cheap model: router, SimpleTeam, document summaries, memory |
| `LLM_STRONG_MODEL_ID` | *(empty)* | Strong model, ComplexTeam only. Empty = `LLM_MODEL_ID` |

## Telegram

| Variable | Default | Description |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | — | Bot token. Empty = Telegram disabled |
| `TELEGRAM_ALLOWED_USER_IDS` | — | Comma-separated numeric IDs. Empty = **nobody** (the bot refuses to start) |
| `ALLOW_ALL_USERS` | `false` | Authorizes every Telegram user. Avoid on a public bot |
| `ADMIN_USER_IDS` | — | Comma-separated numeric ids allowed to install/remove skills from chat (`/skill_add`, `/skill_remove`). Empty = commands off for everyone; `ALLOW_ALL_USERS=true` alone makes nobody an admin |

## REST API

| Variable | Default | Description |
|---|---|---|
| `API_TOKENS` | — | Comma-separated `token:user_id` pairs. Empty = API disabled |
| `API_ENABLED` | `true` | Global API switch |
| `API_HOST` | `127.0.0.1` (`0.0.0.0` in the image) | Bind address inside the process |
| `API_PORT` | `8000` | Port |
| `API_SSL_CERTFILE` / `API_SSL_KEYFILE` | — | Direct HTTPS with Uvicorn (both required) |
| `API_BIND` | `127.0.0.1` | **Compose variable**: host interface the port is published on. `0.0.0.0` exposes it |

## CLI

| Variable | Default | Description |
|---|---|---|
| `CLI_USER_ID` | `cli` | User ID of the CLI. Set it to your Telegram ID to share memory |

## Session, memory and cost

| Variable | Default | Description |
|---|---|---|
| `HISTORY_RUNS` | `6` | Previous runs included in the router context |
| `ENABLE_MEMORY` | `true` | Long-term memories (agentic: the router decides when to save) |
| `ENABLE_LEARNING` | `true` | Structured profile and entities |
| `ENABLE_SESSION_SUMMARIES` | `false` | Session summaries: **+1 LLM call per run** |
| `ENABLE_CRITIC` | `true` | Adds the Critic to the ComplexTeam |
| `TEAM_MAX_ITERATIONS` | `8` | Defined but not used by the current code |
| `AGNO_TELEMETRY` | `false` | PicoBot turns Agno telemetry off unless you set it to `true` |

## Web search

| Variable | Default | Description |
|---|---|---|
| `REGION` | `it-it` | Region of web search results (e.g. `us-en`, `uk-en`) |

## Generated code

| Variable | Default | Description |
|---|---|---|
| `CODE_TIMEOUT_S` | `30` | Wall-clock timeout per execution |
| `CODE_MAX_OUTPUT` | `4000` | Characters of stdout/stderr returned to the agent |
| `CODE_MAX_RUNS` | `6` | Approved executions per request |
| `CODE_NODE_MEM_MB` | `1536` | Address-space limit for Node (pptxgenjs aborts below ~1 GB). Python: fixed 768 MB |
| `CONFIRM_TIMEOUT_S` | `120` | Seconds to answer a confirmation; no answer = refused |
| `NODE_PATH` | `/usr/local/lib/node_modules` in the image | Global Node packages visible to scripts |

## Delivered files

| Variable | Default | Description |
|---|---|---|
| `MAX_OUTPUT_MB` | `20` | Max size of a delivered file |
| `MAX_OUTPUT_FILES` | `5` | Max files per request |
| `OUTPUT_EXTENSIONS` | `docx,pptx,xlsx,csv,txt,md,pdf,html,json,py` | Deliverable extensions |
| `OUTBOX_TTL_H` | `24` | Hours an API file stays downloadable |

## Skills

| Variable | Default | Description |
|---|---|---|
| `ENABLE_SKILLS` | `true` | Enables skills in the ComplexTeam |
| `SKILLS_DIR` | `/app/skills` | Skills folder (the host CLI falls back to `./skills`) |
| `SKILLS_LIST_MAX` | `50` | Max entries returned by `list_skills` |
| `SKILLS_ROUTER_HINT_MAX` | `15` | Skill names shown to the router |

## Documents

| Variable | Default | Description |
|---|---|---|
| `MAX_UPLOAD_MB` | `15` | Max uploaded document size |
| `DOC_CHUNK_CHARS` | `100000` | Below this size a summary is a single call; above it, parallel map + reduce |
| `DOC_MAX_CHARS` | `400000` | Extracted text is truncated here |

## Voice messages (STT)

| Variable | Default | Description |
|---|---|---|
| `STT_URL` | *(empty = off)* | Transcription service, e.g. `http://stt:8000` |
| `STT_TIMEOUT_S` | `180` | Max wait for a transcript |
| `MAX_VOICE_S` | `300` | Max voice duration, checked before downloading |

The variables of the `stt` container (`STT_MODEL`, `STT_BEAM_SIZE`, …) are described in [voice.md](voice.md).

## Scheduler

| Variable | Default | Description |
|---|---|---|
| `TIMEZONE` | `Europe/Rome` | Time zone of cron expressions |
| `SCHEDULE_MIN_INTERVAL_MIN` | `30` | Minimum interval between two runs (cost control) |
| `MAX_SCHEDULES_PER_USER` | `10` | Tasks per user |

## Request trace

| Variable | Default | Description |
|---|---|---|
| `TRACE_ENABLED` | `false` | One JSON line per request in `data/trace.jsonl` (teams, agents, tools, results); `/trace` shows the last one |
| `TRACE_MAX_MB` | `5` | Above this size `trace.jsonl` becomes `trace.jsonl.1` |

## Paths

| Variable | Default | Description |
|---|---|---|
| `DATA_DIR` | `/app/data` | Database (`picobot.db`), Telegram state, inbox, outbox |
| `WORKSPACE_DIR` | `/app/workspace` | `scripts/` and `outputs/` of the agents |
| `MCP_CONFIG_PATH` | `/app/config/mcp_config.json` | MCP servers |

## Startup checks

`picobot serve` stops with an error if:

- no LLM key is set;
- Telegram is enabled but `TELEGRAM_ALLOWED_USER_IDS` is empty and `ALLOW_ALL_USERS` is not `true`;
- no channel is active (neither Telegram nor API).

It logs a warning (without stopping) if `API_TOKENS` is empty (the API is disabled) or if the API listens on a
non-local address without TLS.
