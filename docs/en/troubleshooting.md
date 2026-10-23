# Troubleshooting

🇬🇧 English · 🇮🇹 [Italiano](../it/troubleshooting.md) · ⬅️ [Index](index.md)

Log messages and errors are in Italian; the original text is quoted so you can search the logs
(`docker compose logs picobot`).

## Startup

| Message | Cause | Fix |
|---|---|---|
| `OPENROUTER_API_KEY (o OPENAI_API_KEY) non configurata.` | No LLM key | Set it in `.env` |
| `TELEGRAM_ALLOWED_USER_IDS vuoto: nessuno sarebbe autorizzato...` | Telegram enabled with no authorized users | Add your ID, or start with `--no-telegram` |
| `Nessun canale attivo: configura TELEGRAM_BOT_TOKEN e/o API_TOKENS.` | Neither Telegram nor API configured | Configure at least one |
| `API_TOKENS non configurato: API disattivata.` (warning) | API without tokens | Set `API_TOKENS` or ignore |
| `API esposta senza TLS...` (warning) | API on a non-local address without certificates | Set `API_SSL_CERTFILE`/`API_SSL_KEYFILE` |
| `PermissionError` on `/app/data` or `/app/workspace` | Host folders not writable by UID 1000 | `sudo chown -R 1000 data workspace` |

## Telegram

| Symptom | Fix |
|---|---|
| The bot does not answer | Check `Accesso negato: user_id=...` in the logs and add that ID to `TELEGRAM_ALLOWED_USER_IDS` |
| "Richiesta scaduta o non tua." on a button | The confirmation expired (`CONFIRM_TIMEOUT_S`) or was requested by another user |
| "Formato non supportato" | Only PDF, DOCX, TXT, MD, CSV, JSON, LOG are accepted |
| "File troppo grande" | Raise `MAX_UPLOAD_MB` |
| "Nessun testo estraibile (PDF scansionato? serve OCR)." | Scanned PDF without a text layer: OCR is not included |
| "PDF protetto da password." | Remove the password first |

## Code and files

| Symptom | Cause / fix |
|---|---|
| "Esecuzione NON consentita in questo contesto..." | No confirmation possible: scheduled task, or API without `"approve_code": true` |
| "limite raggiunto (6 esecuzioni approvate per richiesta)" | Raise `CODE_MAX_RUNS` or simplify the request |
| "Timeout: esecuzione interrotta dopo 30s." | Raise `CODE_TIMEOUT_S` |
| Node script aborts while creating a `.pptx` | Raise `CODE_NODE_MEM_MB` (≥ 1024; default 1536) |
| `Cannot find module 'docx'` / `pptxgenjs` | Package missing from `deps/npm.txt`: `uv run picobot skills deps --write`, then rebuild |
| "Rifiutato: il file deve stare dentro outputs/" | Agents must write deliverables in `workspace/outputs/` |
| "Rifiutato: estensione non ammessa" | Add the extension to `OUTPUT_EXTENSIONS` |
| Excel formulas show no values | Expected without LibreOffice: they are computed when the file is opened in Excel |
| API `404` on `/v1/files/{id}` | Wrong token/user, or the file is older than `OUTBOX_TTL_H` |

## Skills and MCP

| Symptom | Fix |
|---|---|
| `Skill '<name>' ignorata: ...` | Run `uv run picobot skills validate`; folder name must equal `name` in `SKILL.md` |
| A new skill is not seen | It is reloaded at the next request; check that it is in `./skills` on the host |
| `skill '<name>' gia' installata: usa --force` | Add `--force` to replace it |
| `MCP: server '<name>' non disponibile, salto` | Check command/URL; try it by hand inside the container; restart after changes |
| `MCP: config non valida` | Invalid JSON in `config/mcp_config.json` |

## Scheduler

| Message | Fix |
|---|---|
| `Cron non valido (...)` | Use 5 fields: `min hour day month weekday` |
| `Intervallo minimo 30 minuti (controllo costi).` | Space runs out more, or lower `SCHEDULE_MIN_INTERVAL_MIN` |
| `Massimo 10 schedule per utente.` | Delete tasks or raise `MAX_SCHEDULES_PER_USER` |
| Task never runs | Tasks run only in `picobot serve`; check that the process is up and `TIMEZONE` is right |

## Resetting

```bash
docker compose down
rm data/picobot.db data/telegram_state.pkl   # WARNING: deletes sessions, memories, profiles and schedules
docker compose up -d
```
