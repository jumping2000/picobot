# Risoluzione problemi

🇮🇹 Italiano · 🇬🇧 [English](../en/troubleshooting.md) · ⬅️ [Indice](index.md)

I messaggi sono riportati come compaiono nel log (`docker compose logs picobot`) o nelle risposte del bot.

## Avvio

| Messaggio | Causa | Soluzione |
|---|---|---|
| `OPENROUTER_API_KEY (o OPENAI_API_KEY) non configurata.` | Manca la chiave LLM | Impostala in `.env` |
| `TELEGRAM_ALLOWED_USER_IDS vuoto: nessuno sarebbe autorizzato...` | Telegram attivo senza utenti autorizzati | Aggiungi il tuo id, o avvia con `--no-telegram` |
| `Nessun canale attivo: configura TELEGRAM_BOT_TOKEN e/o API_TOKENS.` | Né Telegram né API configurati | Configurane almeno uno |
| `API_TOKENS non configurato: API disattivata.` (avviso) | API senza token | Imposta `API_TOKENS` o ignora |
| `API esposta senza TLS...` (avviso) | API su indirizzo non locale senza certificati | Imposta `API_SSL_CERTFILE`/`API_SSL_KEYFILE` |
| `PermissionError` su `/app/data` o `/app/workspace` | Cartelle dell'host non scrivibili da UID 1000 | `sudo chown -R 1000 data workspace` |

## Telegram

| Sintomo | Soluzione |
|---|---|
| Il bot non risponde | Cerca `Accesso negato: user_id=...` nel log e aggiungi quell'id a `TELEGRAM_ALLOWED_USER_IDS` |
| "Richiesta scaduta o non tua." su un bottone | La conferma è scaduta (`CONFIRM_TIMEOUT_S`) o l'ha chiesta un altro utente |
| "Formato non supportato" | Sono accettati solo PDF, DOCX, TXT, MD, CSV, JSON, LOG |
| "File troppo grande" | Aumenta `MAX_UPLOAD_MB` |
| "Nessun testo estraibile (PDF scansionato? serve OCR)." | PDF scansionato senza livello di testo: l'OCR non è incluso |
| "PDF protetto da password." | Rimuovi prima la password |

## Codice e file

| Sintomo | Causa / soluzione |
|---|---|
| "Esecuzione NON consentita in questo contesto..." | Nessuna conferma possibile: task programmato, o API senza `"approve_code": true` |
| "limite raggiunto (6 esecuzioni approvate per richiesta)" | Aumenta `CODE_MAX_RUNS` o semplifica la richiesta |
| "Timeout: esecuzione interrotta dopo 30s." | Aumenta `CODE_TIMEOUT_S` |
| Lo script Node va in abort mentre crea un `.pptx` | Aumenta `CODE_NODE_MEM_MB` (≥ 1024; default 1536) |
| `Cannot find module 'docx'` / `pptxgenjs` | Pacchetto assente da `deps/npm.txt`: `uv run picobot skills deps --write`, poi ricostruisci |
| "Rifiutato: il file deve stare dentro outputs/" | Gli agenti devono scrivere i file da consegnare in `workspace/outputs/` |
| "Rifiutato: estensione non ammessa" | Aggiungi l'estensione a `OUTPUT_EXTENSIONS` |
| Le formule Excel non mostrano valori | Normale senza LibreOffice: si calcolano all'apertura in Excel |
| `404` dell'API su `/v1/files/{id}` | Token/utente sbagliato, o file più vecchio di `OUTBOX_TTL_H` |

## Skill e MCP

| Sintomo | Soluzione |
|---|---|
| `Skill '<nome>' ignorata: ...` | Lancia `uv run picobot skills validate`; il nome della cartella deve essere uguale a `name` in `SKILL.md` |
| Una nuova skill non viene vista | Si ricarica alla richiesta successiva; controlla che sia in `./skills` sull'host |
| `skill '<nome>' gia' installata: usa --force` | Aggiungi `--force` per sostituirla |
| `MCP: server '<nome>' non disponibile, salto` | Controlla comando/URL; provalo a mano nel container; riavvia dopo le modifiche |
| `MCP: config non valida` | JSON non valido in `config/mcp_config.json` |

## Scheduler

| Messaggio | Soluzione |
|---|---|
| `Cron non valido (...)` | Usa 5 campi: `min ora giorno mese giorno_sett` |
| `Intervallo minimo 30 minuti (controllo costi).` | Distanzia le esecuzioni, o abbassa `SCHEDULE_MIN_INTERVAL_MIN` |
| `Massimo 10 schedule per utente.` | Elimina dei task o aumenta `MAX_SCHEDULES_PER_USER` |
| Il task non parte mai | I task girano solo in `picobot serve`: controlla che il processo sia attivo e che `TIMEZONE` sia corretto |

## Ripartire da zero

```bash
docker compose down
rm data/picobot.db data/telegram_state.pkl   # ATTENZIONE: cancella sessioni, memorie, profili e schedule
docker compose up -d
```
