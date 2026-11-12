# Channels: Telegram, email and CLI

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
| `/schedule <cron> \| <request> [\| codice]` | Create a recurring task, e.g. `/schedule 0 8 * * 1-5 \| AAPL and MSFT quotes`; with `\| codice` it may run code (one-time confirmation) |
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

## Email

PicoBot can have an [AgentMail](https://docs.agentmail.to/) inbox: people on an allow-list write to it and get the
answer in the same thread, like a Telegram message. The inbox is read by **polling**, not instantly.

### Configuration

- `.env`: `AGENTMAIL_API_KEY` and `EMAIL_ALLOWED_SENDERS` (comma-separated `address[:user_id]`).
- `config/config.yaml`: `email.inbox_id` (the inbox address) and `email.poll_interval_s` (default 60).
- The channel starts only with the key **and** `inbox_id`; `picobot serve --no-email` turns it off. Email can be
  the only channel. With no email configuration PicoBot works as before.

Details in [configuration.md](configuration.md).

### Allowed senders

Only the addresses in `EMAIL_ALLOWED_SENDERS` are served; the comparison ignores case and the display name. A mail
from anyone else is not answered, never reaches the agents and is logged only with the sender. An empty list means
nobody can write (sending mail stays possible).

An entry can be linked to an existing user with `address:id`, e.g. `io@jumpi.top:123456789,colleague@example.com`.
With `:id` the user_id is that id (typically your Telegram ID, the same as `CLI_USER_ID`): memory, profile and
schedules are shared across channels. Without `:id` the user_id is the lowercased address.

### What happens to a mail

1. Every `email.poll_interval_s` seconds the inbox is read; mails are processed **one at a time**, in arrival order.
2. The request is `subject + body`, sent to the router as a Telegram message would be.
3. The reply goes to the same thread, with the files created by the agents attached.
4. Ignored without an answer: mail from PicoBot itself, auto-replies (`Auto-Submitted`, out-of-office) and inline
   images such as signatures.

**Session per thread.** Each email thread is one session (`mail-<thread>-<sender hash>`), so a reply such as "add
November too" has the context of the exchange. This holds even when PicoBot opened the thread (`send_email`, or the
notification of a schedule): the sent mail is recorded in the session of the recipient, if the recipient is an
allowed sender. Long-term memory follows the user_id, as on the other channels.

**Mails seen.** The processed ids are kept in the `picobot_email_seen` table of `picobot.db` (30 days). On the first
start the past is not processed, only mail that arrives afterwards. A mail is marked as seen right after it is
processed and **before** the reply is sent: if sending fails (network, plan limit) the request is not run again and
the mail stays unanswered (see the log). A crash during processing repeats that mail after a restart.

**Errors.** A `DocumentError` is answered with its message, any other exception with "Errore interno durante
l'elaborazione. Riprova tra poco."; if AgentMail does not answer, the round is skipped and retried.

### Attachments

Treated like documents sent to Telegram: **PDF, DOCX, TXT, MD, CSV, JSON, LOG** up to `MAX_UPLOAD_MB`.

- The **first** supported attachment within the limit is downloaded to `data/inbox/` and the prompt becomes
  `[Documento caricato: name] <text>`; the file is **always deleted** afterwards.
- The others (unsupported format, too large, or after the first) are listed at the end of the reply as ignored.
- If the subject or the first line of the body starts with `/riassumi [instructions]`, the attachment gets a direct
  summary, as on Telegram. Other commands (`/new`, `/schedules`, ...) do not exist by email: write in plain words.
- Replies carry the files created by the agents. AgentMail accepts at most **6 MB per mail** (attachments counted in
  base64): beyond that the reply goes without attachments and says so ("Allegati oltre 6 MB: non inviati.").

### Code

By email there is nobody to ask for confirmation, so mail is pre-approved: with `code.allow_code: true` (default) an
allowed sender can make PicoBot run code in the sandbox **without confirmation**; with `false` no code runs. See
[security.md](security.md): keep the sender list short.

### Scheduled tasks

A schedule created from an email (`channel: email`) delivers its result as a **new mail** to the address that
created it, with subject `[Schedule #id] <prompt>`; replying to it continues the conversation with its context.
Schedules are created, listed and deleted in plain words (the agents have the tools), not with `/schedule`.

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
