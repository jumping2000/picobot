# Changelog

All notable changes to PicoBot are listed here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [0.8.1] - 2026-10-30

### Added

- `telegram.reply_format` in `config/config.yaml` (`markdown` default, `markdownv2`, `html`) chooses how replies are formatted on Telegram. In every mode the model's Markdown is converted: tables become an aligned fixed-width block, `**bold**` and headings become bold, lists use "•", and long replies are split without breaking a block or a formatting. Scheduled-task messages are formatted too and, like replies, fall back to plain text if Telegram rejects them.

### Changed

- The current date and time are now the first instruction of the router and of every team and agent, in Italian
  with the weekday ("Oggi è venerdì 30 ottobre 2026, ore 13:35 (Europe/Rome)…"). Before, agno appended them in
  English at the end of the system prompt, which for the teams comes after members, memories and the session
  summary, so weaker models could miss the date when answering about "today".

## [0.8.0] - 2026-10-30

### Added

- Admins can install and remove skills from Telegram and the CLI chat. `/skill_add <link>` takes an `https://` URL
  (a `.zip` URL is downloaded, any other URL is cloned as a git repository); on Telegram a `.zip` attachment with
  caption `/skill_add` works too, and the CLI chat also accepts a local path. `/skill_remove <name>` removes a
  skill. If the skill is already installed the bot asks before replacing it. The new `ADMIN_USER_IDS` key (comma
  separated Telegram ids, in `.env`) says who is an admin: empty means the commands are off for everyone, and
  `ALLOW_ALL_USERS=true` alone makes nobody an admin. Hosts on local or private networks are refused, git does not
  follow redirects from chat, and every install and removal is logged with user, channel, source and outcome.
- Settings can live in `config/config.yaml`, split into blocks (`memory:`, `web:`, `code:`, …) whose keys have the
  same names as before. Copy `config/config_example.yaml`, which lists every key with its default and a comment, and
  change only what you need. The example sets `voice.stt_url` to `http://stt:8000`, so voice messages are on: leave
  it empty if you do not run the `stt` service. Secrets stay in `.env` and can be referenced as `${NAME}`. An unknown key, a key in the
  wrong block, a wrong value or a key reserved for `.env` stops the startup with a message naming `block.key`.

### Changed

- `./skills` is now mounted read-write in both compose files and the image contains `git`. Existing installs must
  run `sudo chown -R 1000 skills` once on the host; the container user (UID 1000) cannot write to it otherwise,
  and the chat commands answer with that hint. `git clone` in `picobot skills add` now has a 120 s timeout and never
  asks for credentials.
- `.env.example` now lists only the keys that must stay in `.env` (LLM keys and models, Telegram token and ids,
  `ADMIN_USER_IDS`, `API_TOKENS`, `CLI_USER_ID`). Environment variables keep working and win over `config.yaml`, so
  an existing `.env` behaves as before; to move a setting into the YAML file, remove its line from `.env`. The log
  warns when a key is set in both.
- In `compose.yaml` the `stt` service now starts only with the `stt` profile, as in `compose-build.yaml`. If you use
  voice messages, add `COMPOSE_PROFILES=stt` to `.env` (or `--profile stt` to `docker compose`).
- Documentation: the two compose files (`compose.yaml` with prebuilt images, `compose-build.yaml` for local
  builds) are now described everywhere, with the current date and time given to the agents, the cascading web
  search and the ticker hints in the architecture page, and new manual checks for 0.7.x and 0.8.0.

## [0.7.4] - 2026-10-29

### Fixed

- Finance and Analyst no longer guess the Yahoo symbols of market indices. Before, "how is Piazza Affari doing"
  tried `^FTMIE` and `FTSE.MI` (both not found) one after another. Their instructions now list the symbols of the
  main indices (FTSE MIB is `FTSEMIB.MI`), the exchange suffixes for non-US stocks, and tell them to say so when a
  ticker is not found instead of trying others.
- Web searches no longer fail at random with "No results found". Before, each search asked several engines at
  once, Wikipedia and Grokipedia always first and the others in random order, and most of them answer without
  results; whether it worked depended on DuckDuckGo being picked in time. Now Web and Researcher ask one engine at
  a time and move to the next only when the previous one finds nothing: DuckDuckGo, Yahoo, Startpage, Mojeek for
  the web; DuckDuckGo, Bing, Yahoo for news. When none finds anything the agent gets a message instead of an
  error. Brave (always rate limited) and the two encyclopedias are no longer used.

## [0.7.3] - 2026-10-29

### Fixed

- The agents now know today's date and time (in `TIMEZONE`). Before, "today's news" searched around the model's
  training date, and to find out the date the bot asked to run Python code. The router and every team and agent
  get the current date and time in their system prompt (a few tokens per call); Coder and Analyst are told not to
  run code to get them.

## [0.7.2] - 2026-10-29

### Changed

- Web search no longer depends on DuckDuckGo alone: Web and Researcher use DDGS in `auto` mode, which rotates
  between several engines (Bing, Brave, Google, Yahoo, DuckDuckGo…), so a DuckDuckGo block (403/202) no longer
  ends in "No results found.". New `REGION` setting (default `it-it`) for the region of the results.

## [0.7.1] - 2026-10-28

### Added

- Scheduled tasks in plain words: "every weekday at 8am send me AAPL quotes", from Telegram or the CLI, creates
  a real task (same limits as `/schedule`) and the bot answers with its id and next run time. "Which tasks do I
  have?" lists them. A scheduled run cannot create other tasks.
- Request trace: with `TRACE_ENABLED=true` every request writes one JSON line to `data/trace.jsonl` with the
  teams, agents and tools it went through (texts cut to 200 characters), plus a summary line in the log. `/trace`
  on Telegram and the CLI shows the path of your last request. Off by default; `TRACE_MAX_MB` (5) rotates the file.

### Changed

- A task created from the CLI is delivered to Telegram when `CLI_USER_ID` is an allowed Telegram id, so the CLI
  and Telegram share one task list and the result reaches your chat.

## [0.7.0] - 2026-10-25

### Added

- `/riassumi <link> [instructions]` summarizes a web page (articles and blogs) on Telegram, CLI and API
  (`POST /v1/summarize` with a `url` field instead of `file`). Only the main article text is kept, with no menus
  or footer. The page goes through the same summary workflow as documents and is recorded in the session for
  follow-up questions.
- Links to `localhost`, private networks and cloud metadata are refused, also after a redirect. Without a proxy,
  the IP the connection actually reaches is checked too. Behind a proxy (`HTTPS_PROXY`, `HTTP_PROXY`,
  `ALL_PROXY`), the proxy must deny private destinations itself.
- MCP servers: `${NAME}` placeholders in `config/mcp_config.json`, filled from `.env` or the environment, so
  secrets stay out of the JSON. A server with an undefined variable is skipped with a warning that names the
  variable, never the value.
- MCP servers: `headers` for remote servers (for example an API key).
- Manual acceptance checklist in English (`docs/en/manual-qa.md`).

### Changed

- The Italian manual acceptance checklist moved from `docs/manual-qa.md` to `docs/it/manual-qa.md`.
- New dependencies: `trafilatura` (article extraction) and `python-dotenv` (declared explicitly).

### Fixed

- Code sandbox on Windows: generated Node and Python code now gets `SYSTEMROOT`. Without it Node aborted at
  startup and Python could not import `asyncio`.
- The test suite runs on Windows: no more hang in the Word end-to-end test when Node is installed. Tests that
  need POSIX shells or symlinks are skipped there.
- Docker build from a Windows checkout: `.gitattributes` keeps `deps/` and `*.sh` files with LF line endings, so
  `deps/setup.sh` no longer fails with `set: pipefail: invalid option name`.

## [0.6.0] - 2026-10-23

### Added

- Voice messages on Telegram: voice notes and audio files are transcribed, echoed back to the user and handled
  like a written message.
- Optional `stt` service (compose profile `stt`): faster-whisper behind an OpenAI-compatible endpoint, with size
  and duration limits, one transcription at a time, a non-root image and a benchmark script.
- STT client and settings (`STT_URL`, `STT_TIMEOUT_S`, `MAX_VOICE_S`).
- CI/CD pipeline: tests, Docker build check and image publishing to GHCR, also for the `picobot-stt` image.
- Bilingual documentation (English and Italian) in `docs/en` and `docs/it`, and the MIT license.

### Fixed

- `stt`: the audio duration is read from the file header before decoding; dependencies are locked.
- Docker: the final `uv sync` no longer removes the libraries installed from `deps/pip.txt`.

## [0.5.0] - 2026-10-23

### Added

- Router with two teams: SimpleTeam (quotes, searches, scripts) and ComplexTeam (documents, complex tasks), with
  the Writer as the member that produces files.
- Explicit commands `/simple`, `/complex` and `/riassumi`, and the `target` field in the API.
- Uploaded documents go through the router, which decides between a summary and another task.
- Per-user profile and private entity memory (projects, people); `/memory` and `/forget` cover memories,
  profile and entities.
- `save_text_file` tool; documents up to 100,000 characters are summarized in a single call.

### Fixed

- Agno telemetry is off by default.
- Scripts, HTML and JSON files can be delivered to the user.

## [0.4.0] - 2026-10-23

### Added

- Skills: skill registry, skills available to the ComplexTeam, hot reload and the `/skills` command.
- `picobot skills list|add|remove|validate|deps` admin CLI, with safe installation from a folder, zip or git.
- MCP servers shared by the ComplexTeam, with an `enabled` flag per server.
- Word, PowerPoint and Excel files: `run_node`, a cap on code runs per request and unique script names.
- File delivery with checks (`deliver_file`) on Telegram, CLI and API (`GET /v1/files/{id}`, kept for 24 hours).
- Extension points for system, Python and Node dependencies (`deps/`) and a hardened Docker image.

### Fixed

- The `NODE_PATH` check in the Dockerfile really stops the build.
- Skill zip size is checked before extraction.

## [0.3.0] - 2026-10-23

Baseline, rebuilt from the v0.3 archive.

### Added

- Multi-agent assistant on Agno 3 with Telegram, CLI and REST API channels.
- Router on a cheap model with Finance, Web and Coder specialists; ComplexTeam on a strong model.
- Document summaries (PDF, DOCX, TXT, MD, CSV, JSON, LOG) recorded in the session for follow-up questions.
- Long-term memory, cron scheduler, and Python code execution only after human confirmation.
