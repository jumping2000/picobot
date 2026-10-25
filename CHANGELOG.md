# Changelog

All notable changes to PicoBot are listed here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [0.7.0]

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
