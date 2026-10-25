# PicoBot v0.6 — manual acceptance checklist

🇬🇧 English · 🇮🇹 [Italiano](../it/manual-qa.md) · ⬅️ [Index](index.md)

Prerequisites: `.env` with a real LLM key, `TELEGRAM_BOT_TOKEN`, your id in `TELEGRAM_ALLOWED_USER_IDS`, `API_TOKENS`;
skills `docx`, `pptx`, `xlsx` installed in `./skills`; `docker compose up -d --build` completed without errors.

PicoBot's own messages are in Italian: the expected texts below are quoted as the bot writes them, with a
translation in brackets.

| # | Test | Expected | Result |
|---|---|---|---|
| 1 | Telegram: "make a one-page Word document about the history of Siena" | the ComplexTeam uses the docx skill; the buttons with the Node code arrive; after "Conferma" (Confirm) a `*.docx` arrives that opens in Word | |
| 2 | Telegram: "create a 3-slide PowerPoint presentation about PicoBot" | like 1, an openable `*.pptx` file | |
| 3 | Telegram: "create an Excel file with 12 months and a total column with a formula" | an openable `*.xlsx` file; the reply warns that formulas are calculated when the file is opened | |
| 4 | Host: `uv run picobot skills add <folder or zip of a new skill>`, then `/skills` on Telegram; then `uv run picobot skills remove <name>` and `/skills` again | the skill appears and disappears without restarting the container; a relevant request uses it | |
| 5 | Enable a real server in `config/mcp_config.json` (e.g. filesystem via `npx`), restart, ask the ComplexTeam to use it | the log shows "MCP: server '...' connesso (N tool)" (connected); the reply uses the tool | |
| 6 | A request that produces long code (e.g. an 8-slide pptx report) | the `codice.js` attachment arrives first, then the buttons; "Annulla" (Cancel) -> no file created | |
| 7 | Host: `uv run picobot skills add skill.zip` with a valid zip; then with a zip containing `../x` | the first one installs; the second is refused, with nothing left in `skills/` | |
| 8 | API: `POST /v1/chat` with `approve_code: true` asking for a docx; then `GET /v1/files/<id>` with the right token and with another token | download works; with the other token, 404 | |
| 9 | New library for a skill: add a line to `deps/pip.txt` (or `uv run picobot skills deps --write`), `docker compose build && docker compose up -d` | the build completes; the package can be imported by the Analyst's code | |
| 10 | Telegram: "I follow AAPL and ENI", then "quotes of my stocks" | quotes for AAPL and ENI without repeating them; `/memory` shows the profile | |
| 11 | `/simple quote MSFT` and `/complex write a report on X` | they answer without going through the router; a follow-up question has their context | |
| 12 | Send a PDF without a caption; then the same one with the caption "/riassumi in 3 points" | both are summarized; the second without going through the router | |
| 13 | Reply with `/riassumi short` to a PDF sent earlier | a short summary | |
| 14 | Send a PDF with the caption "make a PowerPoint presentation from this PDF" | the ComplexTeam reads the document; the Writer produces the `.pptx` after confirmation | |
| 15 | "I'm working on the Harbor project with Sara", then `/forget` and confirm, then `/memory` | after /forget, no memories, profile or entities | |

**Voice messages (v0.6)** — prerequisites: `STT_URL=http://stt:8000`, `docker compose --profile stt up -d --build`, `stt` healthy (model downloaded).

| # | Test | Expected | Result |
|---|---|---|---|
| 16 | Voice message in Italian "quotazione di AAPL" | echo "🎤 quotazione di AAPL", then the same reply as for the written sentence | |
| 17 | Voice message in English "what is the weather in London" | correct echo, language `en` (in the `stt` log), reply in English | |
| 18 | Silent voice message (a few seconds of silence) | "Non ho capito il vocale, puoi ripeterlo o scriverlo?" (I didn't understand the voice message, can you repeat or write it?); no reply from the router | |
| 19 | `docker compose stop stt`, then a voice message, then a written message | "Trascrizione non disponibile al momento…" (Transcription not available right now); the written message gets a reply | |
| 20 | mp3 file with the caption "summarize" | echo of the transcription, then a summary of the content | |
| 21 | `docker compose --profile stt run --rm stt python bench.py /models/<it>.ogg /models/<en>.ogg` | a table with times and RTF for `base`/`small` × beam 1/5; write down here the chosen `STT_MODEL` and `STT_BEAM_SIZE` | |

**Web pages**

| # | Test | Expected | Result |
|---|---|---|---|
| 22 | Telegram: `/riassumi https://microservices.io/post/architecture/2026/09/29/architecting-with-llms.html in 5 points`; then a question about the summary | a 5-point summary of the article, without menus; the follow-up question has its context | |
| 23 | `/riassumi http://192.168.1.1/` and `/riassumi <link to an existing online PDF>` | "Indirizzo non consentito (rete locale o privata)." (Address not allowed: local or private network) and "Il link non è una pagina HTML..." (The link is not an HTML page) | |
| 24 | CLI and API: `/riassumi <link>` and `POST /v1/summarize -F url=<link>` | a summary as on Telegram | |
