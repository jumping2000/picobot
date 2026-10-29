# Configurazione

🇮🇹 Italiano · 🇬🇧 [English](../en/configuration.md) · ⬅️ [Indice](index.md)

PicoBot legge le impostazioni da variabili d'ambiente o da `.env` (con `pydantic-settings`, senza distinzione tra
maiuscole e minuscole). Fonte di verità: [`src/picobot/config.py`](../../src/picobot/config.py). I booleani
accettano `true`/`false`.

## LLM

| Variabile | Default | Descrizione |
|---|---|---|
| `OPENROUTER_API_KEY` | — | Chiave API. **Obbligatoria** (o `OPENAI_API_KEY`) |
| `OPENAI_API_KEY` | — | Usata solo se `OPENROUTER_API_KEY` è vuota |
| `OPENROUTER_BASE_URL` | `https://openrouter.ai/api/v1` | Endpoint compatibile OpenAI |
| `LLM_MODEL_ID` | `openai/gpt-4o-mini` | Modello economico: router, SimpleTeam, riassunti, memoria |
| `LLM_STRONG_MODEL_ID` | *(vuoto)* | Modello forte, solo ComplexTeam. Vuoto = `LLM_MODEL_ID` |

## Telegram

| Variabile | Default | Descrizione |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | — | Token del bot. Vuoto = Telegram disattivato |
| `TELEGRAM_ALLOWED_USER_IDS` | — | Id numerici separati da virgola. Vuoto = **nessuno** (il bot non parte) |
| `ALLOW_ALL_USERS` | `false` | Autorizza ogni utente Telegram. Da evitare su un bot pubblico |
| `ADMIN_USER_IDS` | — | Id numerici separati da virgola che possono installare/rimuovere skill da chat (`/skill_add`, `/skill_remove`). Vuoto = comandi spenti; `ALLOW_ALL_USERS=true` non rende admin nessuno |

## API REST

| Variabile | Default | Descrizione |
|---|---|---|
| `API_TOKENS` | — | Coppie `token:user_id` separate da virgola. Vuoto = API disattivata |
| `API_ENABLED` | `true` | Interruttore generale dell'API |
| `API_HOST` | `127.0.0.1` (`0.0.0.0` nell'immagine) | Indirizzo di ascolto nel processo |
| `API_PORT` | `8000` | Porta |
| `API_SSL_CERTFILE` / `API_SSL_KEYFILE` | — | HTTPS diretto con Uvicorn (servono entrambi) |
| `API_BIND` | `127.0.0.1` | **Variabile del compose**: interfaccia dell'host su cui viene pubblicata la porta. `0.0.0.0` la espone |

## CLI

| Variabile | Default | Descrizione |
|---|---|---|
| `CLI_USER_ID` | `cli` | Id utente della CLI. Usa il tuo id Telegram per condividere la memoria |

## Sessione, memoria e costi

| Variabile | Default | Descrizione |
|---|---|---|
| `HISTORY_RUNS` | `6` | Run precedenti inclusi nel contesto del router |
| `ENABLE_MEMORY` | `true` | Memorie a lungo termine (agentic: il router decide quando salvare) |
| `ENABLE_LEARNING` | `true` | Profilo strutturato ed entità |
| `ENABLE_SESSION_SUMMARIES` | `false` | Riassunti di sessione: **+1 chiamata LLM per run** |
| `ENABLE_CRITIC` | `true` | Aggiunge il Critic al ComplexTeam |
| `TEAM_MAX_ITERATIONS` | `8` | Definita ma non usata dal codice attuale |
| `AGNO_TELEMETRY` | `false` | PicoBot spegne la telemetria di Agno, a meno che tu non la imposti a `true` |

## Ricerca web

| Variabile | Default | Descrizione |
|---|---|---|
| `REGION` | `it-it` | Regione dei risultati della ricerca web (es. `us-en`, `uk-en`) |

## Codice generato

| Variabile | Default | Descrizione |
|---|---|---|
| `CODE_TIMEOUT_S` | `30` | Timeout per esecuzione |
| `CODE_MAX_OUTPUT` | `4000` | Caratteri di stdout/stderr restituiti all'agente |
| `CODE_MAX_RUNS` | `6` | Esecuzioni approvate per richiesta |
| `CODE_NODE_MEM_MB` | `1536` | Limite di memoria per Node (pptxgenjs va in abort sotto ~1 GB). Python: 768 MB fissi |
| `CONFIRM_TIMEOUT_S` | `120` | Secondi per rispondere a una conferma; nessuna risposta = rifiuto |
| `NODE_PATH` | `/usr/local/lib/node_modules` nell'immagine | Pacchetti Node globali visibili agli script |

## File in uscita

| Variabile | Default | Descrizione |
|---|---|---|
| `MAX_OUTPUT_MB` | `20` | Dimensione massima di un file consegnato |
| `MAX_OUTPUT_FILES` | `5` | File massimi per richiesta |
| `OUTPUT_EXTENSIONS` | `docx,pptx,xlsx,csv,txt,md,pdf,html,json,py` | Estensioni consegnabili |
| `OUTBOX_TTL_H` | `24` | Ore in cui un file resta scaricabile dall'API |

## Skill

| Variabile | Default | Descrizione |
|---|---|---|
| `ENABLE_SKILLS` | `true` | Abilita le skill nel ComplexTeam |
| `SKILLS_DIR` | `/app/skills` | Cartella delle skill (sull'host la CLI ripiega su `./skills`) |
| `SKILLS_LIST_MAX` | `50` | Voci massime restituite da `list_skills` |
| `SKILLS_ROUTER_HINT_MAX` | `15` | Nomi di skill mostrati al router |

## Documenti

| Variabile | Default | Descrizione |
|---|---|---|
| `MAX_UPLOAD_MB` | `15` | Dimensione massima di un documento caricato |
| `DOC_CHUNK_CHARS` | `100000` | Sotto questa soglia il riassunto è una sola chiamata; sopra, map in parallelo + riduzione |
| `DOC_MAX_CHARS` | `400000` | Il testo estratto viene troncato qui |

## Messaggi vocali (STT)

| Variabile | Default | Descrizione |
|---|---|---|
| `STT_URL` | *(vuoto = spento)* | Servizio di trascrizione, es. `http://stt:8000` |
| `STT_TIMEOUT_S` | `180` | Attesa massima della trascrizione |
| `MAX_VOICE_S` | `300` | Durata massima di un vocale, controllata prima del download |

Le variabili del container `stt` (`STT_MODEL`, `STT_BEAM_SIZE`, …) sono descritte in [voice.md](voice.md).

## Scheduler

| Variabile | Default | Descrizione |
|---|---|---|
| `TIMEZONE` | `Europe/Rome` | Fuso orario delle espressioni cron |
| `SCHEDULE_MIN_INTERVAL_MIN` | `30` | Intervallo minimo tra due esecuzioni (controllo costi) |
| `MAX_SCHEDULES_PER_USER` | `10` | Task per utente |

## Traccia delle richieste

| Variabile | Default | Descrizione |
|---|---|---|
| `TRACE_ENABLED` | `false` | Una riga JSON per richiesta in `data/trace.jsonl` (team, agenti, tool, esiti); `/trace` mostra l'ultima |
| `TRACE_MAX_MB` | `5` | Oltre questa dimensione `trace.jsonl` diventa `trace.jsonl.1` |

## Percorsi

| Variabile | Default | Descrizione |
|---|---|---|
| `DATA_DIR` | `/app/data` | Database (`picobot.db`), stato Telegram, inbox, outbox |
| `WORKSPACE_DIR` | `/app/workspace` | `scripts/` e `outputs/` degli agenti |
| `MCP_CONFIG_PATH` | `/app/config/mcp_config.json` | Server MCP |

## Controlli all'avvio

`picobot serve` si ferma con un errore se:

- manca la chiave LLM;
- Telegram è attivo ma `TELEGRAM_ALLOWED_USER_IDS` è vuoto e `ALLOW_ALL_USERS` non è `true`;
- nessun canale è attivo (né Telegram né API).

Scrive un avviso (senza fermarsi) se `API_TOKENS` è vuoto (l'API viene disattivata) o se l'API ascolta su un
indirizzo non locale senza TLS.
