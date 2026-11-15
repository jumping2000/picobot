# Risoluzione problemi

🇮🇹 Italiano · 🇬🇧 [English](../en/troubleshooting.md) · ⬅️ [Indice](index.md)

I messaggi sono riportati come compaiono nel log (`docker compose logs picobot`) o nelle risposte del bot.

## Avvio

| Messaggio | Causa | Soluzione |
|---|---|---|
| `OPENROUTER_API_KEY (o OPENAI_API_KEY) non configurata.` | Manca la chiave LLM | Impostala in `.env` |
| `TELEGRAM_ALLOWED_USER_IDS vuoto: nessuno sarebbe autorizzato...` | Telegram attivo senza utenti autorizzati | Aggiungi il tuo id, o avvia con `--no-telegram` |
| `Nessun canale attivo: configura TELEGRAM_BOT_TOKEN, API_TOKENS e/o AGENTMAIL_API_KEY + email.inbox_id.` | Né Telegram né API né email configurati | Configurane almeno uno |
| `API_TOKENS non configurato: API disattivata.` (avviso) | API senza token | Imposta `API_TOKENS` o ignora |
| `API esposta senza TLS...` (avviso) | API su indirizzo non locale senza certificati | Imposta `API_SSL_CERTFILE`/`API_SSL_KEYFILE` |
| `Configurazione non valida: config/config.yaml: <blocco>.<chiave>: ...` | Chiave sconosciuta o nel blocco sbagliato, valore non valido, `${NOME}` non definito, chiave riservata a `.env`, chiave ripetuta, file non UTF-8 | Correggi la chiave indicata (confronta con `config/config_example.yaml`), poi `docker compose restart` |
| `<CHIAVE> (ambiente/.env) prevale su <blocco>.<chiave> (config/config.yaml)` (avviso) | La stessa impostazione è sia in `.env` sia nello YAML: vince `.env` | Togli la riga da `.env`, poi `docker compose up -d` (`restart` non rilegge `.env`) |
| `ADMIN_USER_IDS non valido: ...` | `ADMIN_USER_IDS` non è un elenco di id numerici separati da virgole | Correggilo in `.env`, poi `docker compose up -d` |
| Il container `stt` non parte, o resta `Exited (0)` | Profilo `stt` non attivo, oppure container creato dall'altro file compose | `COMPOSE_PROFILES=stt` in `.env` (o `--profile stt`), poi `docker compose up -d`; con `compose-build.yaml` aggiungi sempre `-f compose-build.yaml` |
| `PermissionError` su `/app/data` o `/app/workspace` | Cartelle dell'host non scrivibili da UID 1000 | `sudo chown -R 1000 data workspace` |
| `Non posso scrivere nella cartella delle skill...` (da `/skill_add` o `/skill_remove`) | `./skills` non scrivibile da UID 1000, o mount rimasto `:ro` nel compose | `sudo chown -R 1000 skills`; se il compose ha ancora `:ro`, toglilo e rilancia `docker compose up -d` |

## Telegram

| Sintomo | Soluzione |
|---|---|
| Il bot non risponde | Cerca `Accesso negato: user_id=...` nel log e aggiungi quell'id a `TELEGRAM_ALLOWED_USER_IDS` |
| "Richiesta scaduta o non tua." su un bottone | La conferma è scaduta (`CONFIRM_TIMEOUT_S`) o l'ha chiesta un altro utente |
| Il bottone non arriva, o il codice è "rifiutato" anche se hai premuto Conferma | Lancia `/selftest` (admin). Nel log: `Conferma richiesta` = bottone inviato; `Click conferma` = click ricevuto; `Click conferma ignorato ... token sconosciuto o scaduto` = il click è arrivato dopo il timeout; nessuna riga `Click` = Telegram non l'ha consegnato. Se il modello non chiama mai `run_python`, il bottone non c'è: guarda i tool in `/trace` |
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
`exit=1 ... Cannot find module 'docx'`). Il riepilogo di ogni richiesta (`Richiesta: ...`) va comunque nel log del
processo, anche con il trace spento (vedi [Log](#log)).
Per seguirle dal vivo: `tail -f data/trace.jsonl`.

> [!NOTE]
> Il file contiene i testi delle richieste e dei tool, troncati a 200 caratteri. Resta in `data/` e oltre
> `TRACE_MAX_MB` (5 MB) diventa `trace.jsonl.1`, sovrascrivendo il precedente.

## Log

Il log del processo (`docker compose logs picobot`) si regola con il blocco `logging` di `config/config.yaml`
(`log_level`, `log_format`) o con `LOG_LEVEL` / `LOG_FORMAT`. Ogni riga emessa durante una richiesta porta
l'id della richiesta, il canale e l'utente:

```text
2026-11-15 08:15:40,199 INFO    picobot.tools.sandbox [d21f4fdb telegram/220808358] Codice: ... esecuzione 1/6 exit=0 durata=0.4s
2026-11-15 08:15:52,031 INFO    picobot.service [d21f4fdb telegram/220808358] Richiesta: target=auto esito=completed durata=12.3s token=5120 file=1 percorso=PicoBot > ComplexTeam > Writer tool=[delegate_task_to_member, run_node, deliver_file]
```

Fuori da una richiesta (avvio, polling email) i tre campi valgono `-`.

| Livello | Cosa contiene |
|---|---|
| `DEBUG` | Ogni chiamata a un tool riuscita (nome, nomi dei parametri, durata), la fine dell'output del codice fallito |
| `INFO` | Avvio, esito di ogni richiesta, esecuzioni e rifiuti del codice, conferme annullate o scadute, schedule, email |
| `WARNING` | Problemi recuperabili: tool fallito, richiesta in errore, server MCP non disponibile, casella email non leggibile |
| `ERROR` | Funzionalità perse ed eccezioni non gestite (con traceback) |

Best practice:

- **Sviluppo**: `log_level: DEBUG`, `log_format: text`.
- **Produzione**: `log_level: INFO`, `log_format: json`. `compose.yaml` ruota i log Docker (5 file da 10 MB).
  Per raggruppare una richiesta: `docker compose logs --no-log-prefix picobot | jq -c 'select(.req=="d21f4fdb")'`.
- `WARNING` solo se i log sono troppi: si perdono gli esiti delle richieste.
- `DEBUG` in produzione solo per diagnosi, poi si torna a `INFO`.
- Nei log non finiscono segreti, codice, argomenti dei tool né testo dei messaggi. `httpx`, `httpcore`, `openai`
  e `apscheduler` restano almeno a `WARNING` anche in `DEBUG`: i primi due hanno il token Telegram negli URL,
  `openai` scrive i prompt.

Per cambiare livello o formato: modifica `config/config.yaml` e `docker compose restart` (oppure `.env` e
`docker compose up -d`).

## Ripartire da zero

```bash
docker compose down
rm data/picobot.db data/telegram_state.pkl   # ATTENZIONE: cancella sessioni, memorie, profili e schedule
docker compose up -d
```
