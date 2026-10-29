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
| `Non posso scrivere nella cartella delle skill...` (da `/skill_add` o `/skill_remove`) | `./skills` non scrivibile da UID 1000, o mount rimasto `:ro` nel compose | `sudo chown -R 1000 skills`; se il compose ha ancora `:ro`, toglilo e rilancia `docker compose up -d` |

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
| `Solo un amministratore può installare o rimuovere skill.` | Metti il tuo id in `ADMIN_USER_IDS` (`.env`) e applica con `docker compose up -d` (un semplice `restart` non rilegge `.env`); con la chiave vuota i comandi sono spenti |
| `il repository risponde con un redirect...` | Da chat git non segue i redirect HTTP: usa l'URL attuale del repository (per esempio `github.com` senza `www.`, o con `.git` alla fine su GitLab) |
| `MCP: server '<nome>' non disponibile, salto` | Controlla comando/URL; provalo a mano nel container; riavvia dopo le modifiche |
| `MCP: config non valida` | JSON non valido in `config/mcp_config.json` |

## Scheduler

| Messaggio | Soluzione |
|---|---|
| `Cron non valido (...)` | Usa 5 campi: `min ora giorno mese giorno_sett` |
| `Intervallo minimo 30 minuti (controllo costi).` | Distanzia le esecuzioni, o abbassa `SCHEDULE_MIN_INTERVAL_MIN` |
| `Massimo 10 schedule per utente.` | Elimina dei task o aumenta `MAX_SCHEDULES_PER_USER` |
| Il task non parte mai | I task girano solo in `picobot serve`: controlla che il processo sia attivo e che `TIMEZONE` sia corretto |

## Capire il percorso di una richiesta

Con `trace.trace_enabled: true` in `config/config.yaml` (poi `docker compose restart`), ogni richiesta lascia una riga JSON in `data/trace.jsonl`,
e `/trace` mostra la tua ultima:

```text
2026-10-26T08:00 telegram | 4.2s | 1830 token | completed
Richiesta: fammi un documento Word sulla storia di Siena
PicoBot (0.9s, 410 tok)
  - delegate_task_to_member({"member_id": "complexteam", ...}) -> File creato e consegnato.
  ComplexTeam (3.1s, 980 tok)
    - list_skills({"query": "word"}) -> - docx: Crea e modifica documenti Word...
    Writer (2.0s, 440 tok)
      - run_node({"code": "const docx = require('docx')..."}) -> exit=0
      - deliver_file({"path": "outputs/siena.docx"}) -> Consegnato: siena.docx (8123 byte).
File: siena.docx
```

Si vede quale team ha scelto il router, quali agenti hanno lavorato e dove si ferma una catena di tool (per esempio
`exit=1 ... Cannot find module 'docx'`). Ogni riga va anche nel log del processo (`docker compose logs picobot`).
Per seguirle dal vivo: `tail -f data/trace.jsonl`.

> [!NOTE]
> Il file contiene i testi delle richieste e dei tool, troncati a 200 caratteri. Resta in `data/` e oltre
> `TRACE_MAX_MB` (5 MB) diventa `trace.jsonl.1`, sovrascrivendo il precedente.

## Ripartire da zero

```bash
docker compose down
rm data/picobot.db data/telegram_state.pkl   # ATTENZIONE: cancella sessioni, memorie, profili e schedule
docker compose up -d
```
