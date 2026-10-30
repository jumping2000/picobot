# Channels: Telegram and CLI

🇬🇧 English · 🇮🇹 [Italiano](../it/channels.md) · ⬅️ [Index](index.md)

For the REST API see [api.md](api.md).

## Commands

Available on Telegram and in the CLI.

| Command | Description |
|---|---|
| `/help` (`/start`) | Command list |
| `/new` | New conversation (long-term memory is kept) |
| `/simple <request>` | Send directly to the SimpleTeam (quotes, searches, scripts) |
| `/complex <request>` | Send directly to the ComplexTeam (documents, complex tasks) |
| `/riassumi [instructions]` | Direct summary (Telegram: as a document caption or as a reply to a document) |
| `/riassumi <link> [instructions]` | Direct summary of a web page (articles, blogs) |
| `/memory` | Show memories, profile and entities |
| `/forget` | Delete memories, profile and entities (asks for confirmation) |
| `/schedule <cron> \| <request>` | Create a recurring task, e.g. `/schedule 0 8 * * 1-5 \| AAPL and MSFT quotes` |
| `/schedules` | List your scheduled tasks |
| `/unschedule <id>` | Delete a task |
| `/skills` | Installed skills |
| `/skill_add <link>` | Install a skill from an `https://` URL (zip or git repository); admins only. On Telegram also a `.zip` attachment with caption `/skill_add`; in the CLI also a local path. See [skills.md](skills.md#from-telegram-and-the-cli-chat) |
| `/skill_remove <name>` | Remove a skill; admins only |
| `/trace` | Path of your last request: teams, agents, tools and results (with `TRACE_ENABLED=true`) |

CLI only:

| Command | Description |
|---|---|
| `/file <path> [request]` | Use a local document; the router decides (summary or other) |
| `/riassumi <path> [instructions]` | Direct summary of a local document |
| `/quit` (`/exit`) | Exit |

## Telegram

### Access

Only the IDs in `TELEGRAM_ALLOWED_USER_IDS` are served; other users are ignored and logged
(`Accesso negato: user_id=...`). To find your ID, write to a bot such as `@userinfobot`.

### Messages and sessions

- Each chat has its own session ID, persisted in `data/telegram_state.pkl`; `/new` starts a new one.
- Requests in the same chat are processed one at a time; a "typing…" indicator is shown meanwhile.
- Answers are formatted according to `telegram.reply_format` (see configuration.md); tables become a fixed-width
  block. Long answers are split into several messages without breaking the formatting. If Telegram rejects a
  formatted message, it falls back to plain text.

### Documents

Supported formats: **PDF, DOCX, TXT, MD, CSV, JSON, LOG**, up to `MAX_UPLOAD_MB` (15 MB).

| What you send | What happens |
|---|---|
| Document without caption, or caption "summarize" | The router calls the summary workflow |
| Document with a caption request (e.g. "make a PowerPoint from this PDF") | The router delegates to the ComplexTeam, which reads it with `read_document` |
| Document with caption `/riassumi [instructions]` | Direct summary, no router |
| `/riassumi [instructions]` as a reply to a previous document | Direct summary of that document |

The file is downloaded to `data/inbox/` and **always deleted** after processing. The summary is recorded in the
session, so you can ask follow-up questions.

### Web pages

`/riassumi <link> [instructions]` downloads the page and summarizes its main text (no menus, ads or footer),
on Telegram, CLI and API. It is meant for articles and blogs: online PDFs, login or paywalled pages, pages
filled only by JavaScript and videos are not supported. Only `http`/`https`, max 5 MB, 20 s timeout. Links to
`localhost`, the private network or cloud metadata are refused, also after a redirect. Without a proxy, the IP the
connection actually reaches is checked too (against DNS rebinding): the response of a private host is discarded
unread, but the GET request still reaches it. With a proxy (`HTTPS_PROXY`/`HTTP_PROXY`/
`ALL_PROXY`, except `NO_PROXY`) the proxy resolves the name: configure it to deny private destinations. The
pre-check still resolves names from the container: if the container has no external DNS and only the proxy resolves
names, links fail with "host … sconosciuto" (unknown host).

### Voice messages

Voice notes and audio files (also sent as a document) are transcribed by the `stt` service: the bot first echoes
`🎤 <transcript>`, then answers as if you had typed it. Off unless `STT_URL` is set — see [voice.md](voice.md).

### Code confirmation

Before every execution PicoBot shows the **full code** and two buttons, **Conferma** (confirm) and **Annulla**
(cancel):

- code up to 1,500 characters is shown inline; longer code arrives first as an attachment (`codice.py` / `codice.js`);
- only the user who made the request can press the buttons;
- no answer within `CONFIRM_TIMEOUT_S` (120 s) means **refused**.

Files created by the agents arrive as Telegram documents after the answer.

## CLI

```bash
# Docker
docker compose exec -it picobot python -m picobot cli
# local
uv run picobot cli
```

- The user ID is `CLI_USER_ID` (default `cli`); use your Telegram ID to share memory.
- Code confirmations are a `Eseguire? [y/N]` prompt (`y`, `yes`, `s`, `si` = yes); timeout = refused.
- Delivered files are shown as paths (`File: /app/workspace/outputs/...`).
- `/schedule` only writes the task: it is executed by the `picobot serve` process.

```text
> /file ~/report.pdf make a 5-slide presentation
> /riassumi ~/contract.docx in 3 bullet points
> /simple EUR/USD rate
```
