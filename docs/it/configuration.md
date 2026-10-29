# Configurazione

🇮🇹 Italiano · 🇬🇧 [English](../en/configuration.md) · ⬅️ [Indice](index.md)

PicoBot legge le impostazioni da due file. Fonte di verità: [`src/picobot/config.py`](../../src/picobot/config.py).

- **`.env`**: chiavi e segreti, cioè le [chiavi elencate sotto](#chiavi-in-env). Solo lì: nello YAML sono un errore.
- **`config/config.yaml`**: tutto il resto, diviso in blocchi (`memory:`, `web:`, `code:`, …). Si parte da
  [`config/config_example.yaml`](../../config/config_example.yaml): `cp config/config_example.yaml config/config.yaml`,
  poi cambia solo ciò che ti serve. Il file di esempio ha i default del codice, quindi copiarlo non cambia nulla;
  le chiavi fissate dal Dockerfile (vedi sotto) vi sono commentate.
  Senza `config.yaml` valgono i default, come nelle versioni precedenti.

**Precedenza**, dal più forte: variabili d'ambiente, `.env`, `config/config.yaml`, default. I nomi delle variabili
d'ambiente funzionano ancora (`HISTORY_RUNS=10` in `.env` vale come `memory.history_runs: 10`), e **vincono sullo
YAML**: per spostare un parametro nel file YAML togli la riga da `.env`. Quando una chiave è definita in entrambi,
all'avvio il log mostra un avviso del tipo `HISTORY_RUNS (ambiente/.env) prevale su memory.history_runs (config/config.yaml)`.

**Segreti nello YAML:** un valore si può scrivere `${NOME}` e viene preso da `.env` o dall'ambiente, come in
`mcp_config.json`.

**Errori:** un blocco o una chiave sconosciuti (anche una chiave valida nel blocco sbagliato), un valore del tipo
sbagliato, un `${NOME}` non definito o una chiave riservata a `.env` impediscono l'avvio, con un messaggio come
`Configurazione non valida: config/config.yaml: memory.histroy_runs: chiave sconosciuta`.

Il file si legge solo all'avvio: dopo una modifica serve `docker compose restart`. Una modifica a `.env` invece
richiede `docker compose up -d`, perché `restart` non rilegge `env_file`.

> **Nell'immagine Docker** il `Dockerfile` imposta `DATA_DIR`, `WORKSPACE_DIR`, `SKILLS_DIR`, `API_HOST=0.0.0.0` e
> `NODE_PATH`. Sono variabili d'ambiente, quindi vincono: nel container `paths.data_dir`, `paths.workspace_dir`,
> `skills.skills_dir`, `api.api_host` e `code.node_path` dello YAML non hanno effetto.

I booleani accettano `true`/`false`. Le variabili d'ambiente non distinguono maiuscole e minuscole; nello YAML
blocchi e chiavi si scrivono in minuscolo, come nelle tabelle.

## Chiavi in `.env`

| Variabile | Default | Descrizione |
|---|---|---|
| `OPENROUTER_API_KEY` | — | Chiave API. **Obbligatoria** (o `OPENAI_API_KEY`) |
| `OPENAI_API_KEY` | — | Usata solo se `OPENROUTER_API_KEY` è vuota |
| `OPENROUTER_BASE_URL` | `https://openrouter.ai/api/v1` | Endpoint compatibile OpenAI |
| `LLM_MODEL_ID` | `openai/gpt-4o-mini` | Modello economico: router, SimpleTeam, riassunti, memoria |
| `LLM_STRONG_MODEL_ID` | *(vuoto)* | Modello forte, solo ComplexTeam. Vuoto = `LLM_MODEL_ID` |
| `TELEGRAM_BOT_TOKEN` | — | Token del bot. Vuoto = Telegram disattivato |
| `TELEGRAM_ALLOWED_USER_IDS` | — | Id numerici separati da virgola. Vuoto = **nessuno** (il bot non parte) |
| `ADMIN_USER_IDS` | — | Id numerici separati da virgola che possono installare/rimuovere skill da chat (`/skill_add`, `/skill_remove`). Vuoto = comandi spenti per tutti; `ALLOW_ALL_USERS=true` da solo non rende admin nessuno |
| `API_TOKENS` | — | Coppie `token:user_id` separate da virgola. Vuoto = API disattivata |
| `CLI_USER_ID` | `cli` | Id utente della CLI. Usa il tuo id Telegram per condividere la memoria |

Restano in `.env` anche due variabili che PicoBot non legge da `config.yaml`:

| Variabile | Default | Descrizione |
|---|---|---|
| `API_BIND` | `127.0.0.1` | **Variabile del compose**: interfaccia dell'host su cui viene pubblicata la porta. `0.0.0.0` la espone |
| `AGNO_TELEMETRY` | `false` | PicoBot spegne la telemetria di Agno, a meno che tu non la imposti a `true` |

## Blocchi di `config/config.yaml`

Ogni tabella è un blocco. La colonna **Variabile** è il nome della variabile d'ambiente equivalente, ancora valido.

### `telegram`

| Chiave | Variabile | Default | Descrizione |
|---|---|---|---|
| `telegram.allow_all_users` | `ALLOW_ALL_USERS` | `false` | Autorizza ogni utente Telegram. Da evitare su un bot pubblico |

### `paths`

| Chiave | Variabile | Default | Descrizione |
|---|---|---|---|
| `paths.data_dir` | `DATA_DIR` | `/app/data` | Database (`picobot.db`), stato Telegram, inbox, outbox. Nel container la fissa il Dockerfile |
| `paths.workspace_dir` | `WORKSPACE_DIR` | `/app/workspace` | `scripts/` e `outputs/` degli agenti. Nel container la fissa il Dockerfile |
| `paths.mcp_config_path` | `MCP_CONFIG_PATH` | `/app/config/mcp_config.json` | Server MCP |

### `memory` (sessione, memoria e costi)

| Chiave | Variabile | Default | Descrizione |
|---|---|---|---|
| `memory.history_runs` | `HISTORY_RUNS` | `6` | Run precedenti inclusi nel contesto del router |
| `memory.enable_memory` | `ENABLE_MEMORY` | `true` | Memorie a lungo termine (agentic: il router decide quando salvare) |
| `memory.enable_learning` | `ENABLE_LEARNING` | `true` | Profilo strutturato ed entità |
| `memory.enable_session_summaries` | `ENABLE_SESSION_SUMMARIES` | `false` | Riassunti di sessione: **+1 chiamata LLM per run** |
| `memory.enable_critic` | `ENABLE_CRITIC` | `true` | Aggiunge il Critic al ComplexTeam |
| `memory.team_max_iterations` | `TEAM_MAX_ITERATIONS` | `3` | Definita ma non usata dal codice attuale |

### `web`

| Chiave | Variabile | Default | Descrizione |
|---|---|---|---|
| `web.region` | `REGION` | `it-it` | Regione dei risultati della ricerca web (es. `us-en`, `uk-en`) |

### `code` (codice generato)

| Chiave | Variabile | Default | Descrizione |
|---|---|---|---|
| `code.code_timeout_s` | `CODE_TIMEOUT_S` | `30` | Timeout per esecuzione |
| `code.code_max_output` | `CODE_MAX_OUTPUT` | `4000` | Caratteri di stdout/stderr restituiti all'agente |
| `code.confirm_timeout_s` | `CONFIRM_TIMEOUT_S` | `120` | Secondi per rispondere a una conferma; nessuna risposta = rifiuto |
| `code.code_node_mem_mb` | `CODE_NODE_MEM_MB` | `1536` | Limite di memoria per Node (pptxgenjs va in abort sotto ~1 GB). Python: 768 MB fissi |
| `code.code_max_runs` | `CODE_MAX_RUNS` | `6` | Esecuzioni approvate per richiesta |
| `code.node_path` | `NODE_PATH` | *(vuoto)*; `/usr/local/lib/node_modules` nell'immagine | Pacchetti Node globali visibili agli script. Nel container la fissa il Dockerfile |

### `outputs` (file in uscita)

| Chiave | Variabile | Default | Descrizione |
|---|---|---|---|
| `outputs.max_output_mb` | `MAX_OUTPUT_MB` | `20` | Dimensione massima di un file consegnato |
| `outputs.max_output_files` | `MAX_OUTPUT_FILES` | `5` | File massimi per richiesta |
| `outputs.output_extensions` | `OUTPUT_EXTENSIONS` | `docx,pptx,xlsx,csv,txt,md,pdf,html,json,py` | Estensioni consegnabili |
| `outputs.outbox_ttl_h` | `OUTBOX_TTL_H` | `24` | Ore in cui un file resta scaricabile dall'API |

### `trace` (traccia delle richieste)

| Chiave | Variabile | Default | Descrizione |
|---|---|---|---|
| `trace.trace_enabled` | `TRACE_ENABLED` | `false` | Una riga JSON per richiesta in `data/trace.jsonl` (team, agenti, tool, esiti); `/trace` mostra l'ultima |
| `trace.trace_max_mb` | `TRACE_MAX_MB` | `5` | Oltre questa dimensione `trace.jsonl` diventa `trace.jsonl.1` |

### `skills`

| Chiave | Variabile | Default | Descrizione |
|---|---|---|---|
| `skills.enable_skills` | `ENABLE_SKILLS` | `true` | Abilita le skill nel ComplexTeam |
| `skills.skills_dir` | `SKILLS_DIR` | `/app/skills` | Cartella delle skill (sull'host la CLI ripiega su `./skills`). Nel container la fissa il Dockerfile |
| `skills.skills_list_max` | `SKILLS_LIST_MAX` | `50` | Voci massime restituite da `list_skills` |
| `skills.skills_router_hint_max` | `SKILLS_ROUTER_HINT_MAX` | `15` | Nomi di skill mostrati al router |

### `documents`

| Chiave | Variabile | Default | Descrizione |
|---|---|---|---|
| `documents.max_upload_mb` | `MAX_UPLOAD_MB` | `15` | Dimensione massima di un documento caricato |
| `documents.doc_chunk_chars` | `DOC_CHUNK_CHARS` | `100000` | Sotto questa soglia il riassunto è una sola chiamata; sopra, map in parallelo + riduzione |
| `documents.doc_max_chars` | `DOC_MAX_CHARS` | `400000` | Il testo estratto viene troncato qui |

### `voice` (messaggi vocali, STT)

| Chiave | Variabile | Default | Descrizione |
|---|---|---|---|
| `voice.stt_url` | `STT_URL` | *(vuoto = spento)* | Servizio di trascrizione, es. `http://stt:8000` |
| `voice.stt_timeout_s` | `STT_TIMEOUT_S` | `180` | Attesa massima della trascrizione |
| `voice.max_voice_s` | `MAX_VOICE_S` | `300` | Durata massima di un vocale, controllata prima del download |

Le variabili del container `stt` (`STT_MODEL`, `STT_BEAM_SIZE`, …) sono del compose e sono descritte in
[voice.md](voice.md).

### `scheduler`

| Chiave | Variabile | Default | Descrizione |
|---|---|---|---|
| `scheduler.timezone` | `TIMEZONE` | `Europe/Rome` | Fuso orario delle espressioni cron |
| `scheduler.schedule_min_interval_min` | `SCHEDULE_MIN_INTERVAL_MIN` | `30` | Intervallo minimo tra due esecuzioni (controllo costi) |
| `scheduler.max_schedules_per_user` | `MAX_SCHEDULES_PER_USER` | `10` | Task per utente |

### `api`

| Chiave | Variabile | Default | Descrizione |
|---|---|---|---|
| `api.api_enabled` | `API_ENABLED` | `true` | Interruttore generale dell'API |
| `api.api_host` | `API_HOST` | `127.0.0.1` (`0.0.0.0` nell'immagine) | Indirizzo di ascolto nel processo. Nel container lo fissa il Dockerfile |
| `api.api_port` | `API_PORT` | `8000` | Porta |
| `api.api_ssl_certfile` / `api.api_ssl_keyfile` | `API_SSL_CERTFILE` / `API_SSL_KEYFILE` | — | HTTPS diretto con Uvicorn (servono entrambi) |

## Controlli all'avvio

PicoBot si ferma con un errore se:

- `config/config.yaml` non è valido (vedi sopra; vale anche per `picobot skills`);
- manca la chiave LLM;
- Telegram è attivo ma `TELEGRAM_ALLOWED_USER_IDS` è vuoto e `ALLOW_ALL_USERS` non è `true`;
- Telegram è attivo e `ADMIN_USER_IDS` non è un elenco di id numerici;
- nessun canale è attivo (né Telegram né API).

Scrive un avviso (senza fermarsi) se `API_TOKENS` è vuoto (l'API viene disattivata), se l'API ascolta su un
indirizzo non locale senza TLS, o se una chiave di `config.yaml` è definita anche in `.env` o nell'ambiente.
