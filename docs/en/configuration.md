# Configuration

🇬🇧 English · 🇮🇹 [Italiano](../it/configuration.md) · ⬅️ [Index](index.md)

PicoBot reads its settings from two files. Source of truth: [`src/picobot/config.py`](../../src/picobot/config.py).

- **`.env`**: keys and secrets, i.e. the [keys listed below](#keys-in-env). Only there: in the YAML they are an error.
- **`config/config.yaml`**: everything else, split into blocks (`memory:`, `web:`, `code:`, …). Start from
  [`config/config_example.yaml`](../../config/config_example.yaml): `cp config/config_example.yaml config/config.yaml`,
  then change only what you need. The example holds the code defaults, except `voice.stt_url`
  (`http://stt:8000`), which turns voice messages on: if you do not run the `stt` service, leave it empty. The
  keys fixed by the Dockerfile (see below) are commented out in it.
  Without `config.yaml` the defaults apply, as in earlier versions.

**Precedence**, strongest first: environment variables, `.env`, `config/config.yaml`, defaults. Environment variable
names still work (`HISTORY_RUNS=10` in `.env` counts as `memory.history_runs: 10`) and **win over the YAML**: to move
a setting into the YAML file, remove its line from `.env`. When a key is set in both, the log shows a warning at
startup such as `HISTORY_RUNS (ambiente/.env) prevale su memory.history_runs (config/config.yaml)`.

**Secrets in the YAML:** a value can be written as `${NAME}` and is taken from `.env` or the environment, as in
`mcp_config.json`.

**Errors:** an unknown block or key (including a valid key in the wrong block), a value of the wrong type, an
undefined `${NAME}` or a key reserved for `.env` stop the startup, with a message such as
`Configurazione non valida: config/config.yaml: memory.histroy_runs: chiave sconosciuta`.

The file is read only at startup: after a change run `docker compose restart`. A change to `.env` needs
`docker compose up -d` instead, because `restart` does not re-read `env_file`.

> **In the Docker image** the `Dockerfile` sets `DATA_DIR`, `WORKSPACE_DIR`, `SKILLS_DIR`, `API_HOST=0.0.0.0` and
> `NODE_PATH`. They are environment variables, so they win: in the container `paths.data_dir`, `paths.workspace_dir`,
> `skills.skills_dir`, `api.api_host` and `code.node_path` in the YAML have no effect.

Booleans accept `true`/`false`. Environment variables are case-insensitive; in the YAML, blocks and keys are written
in lowercase, as in the tables.

## Keys in `.env`

| Variable | Default | Description |
|---|---|---|
| `OPENROUTER_API_KEY` | — | API key. **Required** (or `OPENAI_API_KEY`) |
| `OPENAI_API_KEY` | — | Used only if `OPENROUTER_API_KEY` is empty |
| `OPENROUTER_BASE_URL` | `https://openrouter.ai/api/v1` | OpenAI-compatible endpoint |
| `LLM_MODEL_ID` | `openai/gpt-4o-mini` | Cheap model: router, SimpleTeam, document summaries, memory |
| `LLM_STRONG_MODEL_ID` | *(empty)* | Strong model, ComplexTeam only. Empty = `LLM_MODEL_ID` |
| `TELEGRAM_BOT_TOKEN` | — | Bot token. Empty = Telegram disabled |
| `TELEGRAM_ALLOWED_USER_IDS` | — | Comma-separated numeric IDs. Empty = **nobody** (the bot refuses to start) |
| `ADMIN_USER_IDS` | — | Comma-separated numeric ids allowed to install/remove skills from chat (`/skill_add`, `/skill_remove`). Empty = commands off for everyone; `ALLOW_ALL_USERS=true` alone makes nobody an admin |
| `API_TOKENS` | — | Comma-separated `token:user_id` pairs. Empty = API disabled |
| `CLI_USER_ID` | `cli` | User ID of the CLI. Set it to your Telegram ID to share memory |

Two variables that PicoBot does not read from `config.yaml` also stay in `.env`:

| Variable | Default | Description |
|---|---|---|
| `API_BIND` | `127.0.0.1` | **Compose variable**: host interface the port is published on. `0.0.0.0` exposes it |
| `AGNO_TELEMETRY` | `false` | PicoBot turns Agno telemetry off unless you set it to `true` |

## Blocks of `config/config.yaml`

Each table is a block. The **Variable** column is the equivalent environment variable name, still valid.

### `telegram`

| Key | Variable | Default | Description |
|---|---|---|---|
| `telegram.allow_all_users` | `ALLOW_ALL_USERS` | `false` | Authorizes every Telegram user. Avoid on a public bot |

### `paths`

| Key | Variable | Default | Description |
|---|---|---|---|
| `paths.data_dir` | `DATA_DIR` | `/app/data` | Database (`picobot.db`), Telegram state, inbox, outbox. Fixed by the Dockerfile in the container |
| `paths.workspace_dir` | `WORKSPACE_DIR` | `/app/workspace` | `scripts/` and `outputs/` of the agents. Fixed by the Dockerfile in the container |
| `paths.mcp_config_path` | `MCP_CONFIG_PATH` | `/app/config/mcp_config.json` | MCP servers |

### `memory` (session, memory and cost)

| Key | Variable | Default | Description |
|---|---|---|---|
| `memory.history_runs` | `HISTORY_RUNS` | `6` | Previous runs included in the router context |
| `memory.enable_memory` | `ENABLE_MEMORY` | `true` | Long-term memories (agentic: the router decides when to save) |
| `memory.enable_learning` | `ENABLE_LEARNING` | `true` | Structured profile and entities |
| `memory.enable_session_summaries` | `ENABLE_SESSION_SUMMARIES` | `false` | Session summaries: **+1 LLM call per run** |
| `memory.enable_critic` | `ENABLE_CRITIC` | `true` | Adds the Critic to the ComplexTeam |
| `memory.team_max_iterations` | `TEAM_MAX_ITERATIONS` | `3` | Defined but not used by the current code |

### `web`

| Key | Variable | Default | Description |
|---|---|---|---|
| `web.region` | `REGION` | `it-it` | Region of web search results (e.g. `us-en`, `uk-en`) |

### `code` (generated code)

| Key | Variable | Default | Description |
|---|---|---|---|
| `code.code_timeout_s` | `CODE_TIMEOUT_S` | `30` | Wall-clock timeout per execution |
| `code.code_max_output` | `CODE_MAX_OUTPUT` | `4000` | Characters of stdout/stderr returned to the agent |
| `code.confirm_timeout_s` | `CONFIRM_TIMEOUT_S` | `120` | Seconds to answer a confirmation; no answer = refused |
| `code.code_node_mem_mb` | `CODE_NODE_MEM_MB` | `1536` | Address-space limit for Node (pptxgenjs aborts below ~1 GB). Python: fixed 768 MB |
| `code.code_max_runs` | `CODE_MAX_RUNS` | `6` | Approved executions per request |
| `code.node_path` | `NODE_PATH` | *(empty)*; `/usr/local/lib/node_modules` in the image | Global Node packages visible to scripts. Fixed by the Dockerfile in the container |

### `outputs` (delivered files)

| Key | Variable | Default | Description |
|---|---|---|---|
| `outputs.max_output_mb` | `MAX_OUTPUT_MB` | `20` | Max size of a delivered file |
| `outputs.max_output_files` | `MAX_OUTPUT_FILES` | `5` | Max files per request |
| `outputs.output_extensions` | `OUTPUT_EXTENSIONS` | `docx,pptx,xlsx,csv,txt,md,pdf,html,json,py` | Deliverable extensions |
| `outputs.outbox_ttl_h` | `OUTBOX_TTL_H` | `24` | Hours an API file stays downloadable |

### `trace` (request trace)

| Key | Variable | Default | Description |
|---|---|---|---|
| `trace.trace_enabled` | `TRACE_ENABLED` | `false` | One JSON line per request in `data/trace.jsonl` (teams, agents, tools, results); `/trace` shows the last one |
| `trace.trace_max_mb` | `TRACE_MAX_MB` | `5` | Above this size `trace.jsonl` becomes `trace.jsonl.1` |

### `skills`

| Key | Variable | Default | Description |
|---|---|---|---|
| `skills.enable_skills` | `ENABLE_SKILLS` | `true` | Enables skills in the ComplexTeam |
| `skills.skills_dir` | `SKILLS_DIR` | `/app/skills` | Skills folder (the host CLI falls back to `./skills`). Fixed by the Dockerfile in the container |
| `skills.skills_list_max` | `SKILLS_LIST_MAX` | `50` | Max entries returned by `list_skills` |
| `skills.skills_router_hint_max` | `SKILLS_ROUTER_HINT_MAX` | `15` | Skill names shown to the router |

### `documents`

| Key | Variable | Default | Description |
|---|---|---|---|
| `documents.max_upload_mb` | `MAX_UPLOAD_MB` | `15` | Max uploaded document size |
| `documents.doc_chunk_chars` | `DOC_CHUNK_CHARS` | `100000` | Below this size a summary is a single call; above it, parallel map + reduce |
| `documents.doc_max_chars` | `DOC_MAX_CHARS` | `400000` | Extracted text is truncated here |

### `voice` (voice messages, STT)

| Key | Variable | Default | Description |
|---|---|---|---|
| `voice.stt_url` | `STT_URL` | *(empty = off)* | Transcription service, e.g. `http://stt:8000` |
| `voice.stt_timeout_s` | `STT_TIMEOUT_S` | `180` | Max wait for a transcript |
| `voice.max_voice_s` | `MAX_VOICE_S` | `300` | Max voice duration, checked before downloading |

The variables of the `stt` container (`STT_MODEL`, `STT_BEAM_SIZE`, …) belong to the compose file and are described
in [voice.md](voice.md).

### `scheduler`

| Key | Variable | Default | Description |
|---|---|---|---|
| `scheduler.timezone` | `TIMEZONE` | `Europe/Rome` | Time zone of cron expressions |
| `scheduler.schedule_min_interval_min` | `SCHEDULE_MIN_INTERVAL_MIN` | `30` | Minimum interval between two runs (cost control) |
| `scheduler.max_schedules_per_user` | `MAX_SCHEDULES_PER_USER` | `10` | Tasks per user |

### `api`

| Key | Variable | Default | Description |
|---|---|---|---|
| `api.api_enabled` | `API_ENABLED` | `true` | Global API switch |
| `api.api_host` | `API_HOST` | `127.0.0.1` (`0.0.0.0` in the image) | Bind address inside the process. Fixed by the Dockerfile in the container |
| `api.api_port` | `API_PORT` | `8000` | Port |
| `api.api_ssl_certfile` / `api.api_ssl_keyfile` | `API_SSL_CERTFILE` / `API_SSL_KEYFILE` | — | Direct HTTPS with Uvicorn (both required) |

## Startup checks

PicoBot stops with an error if:

- `config/config.yaml` is invalid (see above; this applies to `picobot skills` too);
- no LLM key is set;
- Telegram is enabled but `TELEGRAM_ALLOWED_USER_IDS` is empty and `ALLOW_ALL_USERS` is not `true`;
- Telegram is enabled and `ADMIN_USER_IDS` is not a list of numeric ids;
- no channel is active (neither Telegram nor API).

It logs a warning (without stopping) if `API_TOKENS` is empty (the API is disabled), if the API listens on a
non-local address without TLS, or if a `config.yaml` key is also set in `.env` or the environment.
