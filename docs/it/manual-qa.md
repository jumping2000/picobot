# PicoBot v0.8 — collaudo manuale

🇮🇹 Italiano · 🇬🇧 [English](../en/manual-qa.md) · ⬅️ [Indice](index.md)

Prerequisiti: `.env` con chiave LLM reale, `TELEGRAM_BOT_TOKEN`, il tuo id in `TELEGRAM_ALLOWED_USER_IDS`, `API_TOKENS`;
skill `docx`, `pptx`, `xlsx` installate in `./skills`; `docker compose up -d` (o `docker compose -f compose-build.yaml up -d --build`) completato senza errori.

| # | Prova | Atteso | Esito |
|---|---|---|---|
| 1 | Telegram: "fammi un documento Word di una pagina sulla storia di Siena" | il ComplexTeam usa la skill docx; arrivano i bottoni con il codice Node; dopo "Conferma" arriva `*.docx` che si apre in Word | |
| 2 | Telegram: "crea una presentazione PowerPoint di 3 slide su PicoBot" | come 1, file `*.pptx` apribile | |
| 3 | Telegram: "crea un Excel con 12 mesi e una colonna totale con formula" | file `*.xlsx` apribile; la risposta avvisa che le formule si calcolano all'apertura | |
| 4 | Host: `uv run picobot skills add <cartella o zip di una nuova skill>`, poi `/skills` su Telegram; poi `uv run picobot skills remove <nome>` e di nuovo `/skills` | la skill compare e sparisce senza riavviare il container; una richiesta pertinente la usa | |
| 5 | Abilita in `config/mcp_config.json` un server reale (es. filesystem via `npx`), riavvia, chiedi al ComplexTeam di usarlo | nel log "MCP: server '...' connesso (N tool)"; la risposta usa il tool | |
| 6 | Richiesta che produce codice lungo (es. report pptx di 8 slide) | prima arriva l'allegato `codice.js`, poi i bottoni; "Annulla" -> nessun file creato | |
| 7 | Host: `uv run picobot skills add skill.zip` con uno zip valido; poi con uno zip contenente `../x` | il primo installa; il secondo e' rifiutato senza residui in `skills/` | |
| 8 | API: `POST /v1/chat` con `approve_code: true` chiedendo un docx; poi `GET /v1/files/<id>` con il token giusto e con un altro token | download ok; con l'altro token 404 | |
| 9 | Nuova libreria per una skill: aggiungi una riga a `deps/pip.txt` (o `uv run picobot skills deps --write`), `docker compose -f compose-build.yaml up -d --build` | la build completa; il pacchetto e' importabile dal codice dell'Analyst | |
| 10 | Telegram: "seguo AAPL e ENI", poi "quotazione dei miei titoli" | quotazioni di AAPL ed ENI senza ripeterli; `/memory` mostra il profilo | |
| 11 | `/simple quotazione MSFT` e `/complex scrivi una relazione su X` | rispondono senza passare dal router; una domanda successiva ne ha il contesto | |
| 12 | Invio di un PDF senza didascalia; poi lo stesso con didascalia "/riassumi in 3 punti" | entrambi riassunti; il secondo senza passare dal router | |
| 13 | Rispondi con `/riassumi breve` a un PDF inviato prima | riassunto breve | |
| 14 | Invio di un PDF con didascalia "fammi una presentazione PowerPoint da questo PDF" | il ComplexTeam legge il documento, il Writer produce il `.pptx` dopo la conferma | |
| 15 | "lavoro al progetto Harbor con Sara", poi `/forget` e conferma, poi `/memory` | dopo /forget nessuna memoria, profilo o entita' | |

**Messaggi vocali (v0.6)** — prerequisiti: `voice.stt_url: http://stt:8000` in `config/config.yaml`, `COMPOSE_PROFILES=stt` in `.env` e `docker compose up -d`, `stt` healthy (modello scaricato).

| # | Prova | Atteso | Esito |
|---|---|---|---|
| 16 | Vocale in italiano "quotazione di AAPL" | eco "🎤 quotazione di AAPL", poi la stessa risposta della frase scritta | |
| 17 | Vocale in inglese "what is the weather in London" | eco corretta, lingua `en` (log di `stt`), risposta in inglese | |
| 18 | Vocale muto (qualche secondo di silenzio) | "Non ho capito il vocale, puoi ripeterlo o scriverlo?"; nessuna risposta del router | |
| 19 | `docker compose stop stt`, poi un vocale, poi un messaggio scritto | "Trascrizione non disponibile al momento…"; il messaggio scritto riceve risposta | |
| 20 | File mp3 con didascalia "riassumi" | eco della trascrizione, poi un riassunto del contenuto | |
| 21 | `docker compose --profile stt run --rm stt python bench.py /models/<it>.ogg /models/<en>.ogg` | tabella con tempi e RTF per `base`/`small` × beam 1/5; annota qui la scelta di `STT_MODEL` e `STT_BEAM_SIZE` | |

**Pagine web**

| # | Prova | Atteso | Esito |
|---|---|---|---|
| 22 | Telegram: `/riassumi https://microservices.io/post/architecture/2026/09/29/architecting-with-llms.html in 5 punti`; poi una domanda sul riassunto | riassunto in 5 punti dell'articolo, senza menu; la domanda successiva ne ha il contesto | |
| 23 | `/riassumi http://192.168.1.1/` e `/riassumi <link a un PDF online esistente>` | "Indirizzo non consentito (rete locale o privata)." e "Il link non è una pagina HTML..." | |
| 24 | CLI e API: `/riassumi <link>` e `POST /v1/summarize -F url=<link>` | riassunto come su Telegram | |

**Date, ricerca web e ticker (v0.7.3–0.7.4)**

| # | Prova | Atteso | Esito |
|---|---|---|---|
| 25 | Telegram: "che giorno è oggi?" | data e ora corrette nel fuso `scheduler.timezone`, senza proporre di eseguire codice | |
| 26 | Telegram: "notizie di oggi su Piazza Affari" | le query nel log (`primp`) contengono la data di oggi, non una data passata; una richiesta per motore, prima DuckDuckGo | |
| 27 | Telegram: "come va il FTSE MIB?" | quotazione da `FTSEMIB.MI` al primo tentativo; nel log nessun 404 di yfinance su simboli inventati | |

**Task a parole e traccia (v0.7.1)**

| # | Prova | Atteso | Esito |
|---|---|---|---|
| 28 | Telegram: "ogni giorno feriale alle 8 mandami la quotazione di AAPL", poi "quali task ho?" | il bot risponde con id e prossima esecuzione; l'elenco lo mostra; `/unschedule <id>` lo elimina | |
| 29 | `trace.trace_enabled: true` in `config/config.yaml`, `docker compose restart`, una richiesta, poi `/trace` | `/trace` mostra team, agenti e tool dell'ultima richiesta; una riga in `data/trace.jsonl` | |

**Skill da chat (v0.8)** — prerequisiti: `sudo chown -R 1000 skills` sull'host, `ADMIN_USER_IDS=<il tuo id>` in `.env`, `docker compose up -d`.

| # | Prova | Atteso | Esito |
|---|---|---|---|
| 30 | Da admin: `/skill_add https://github.com/<org>/<repo-con-una-skill>.git`, poi `/skills` | risposta con nome, descrizione ed eventuali dipendenze; `/skills` la elenca senza riavvio | |
| 31 | Da admin: uno `.zip` allegato con didascalia `/skill_add` di una skill già presente, poi "Annulla" | domanda Conferma/Annulla; con "Annulla" la skill resta quella di prima | |
| 32 | `/skill_add https://192.168.1.10/x.zip` e `/skill_add http://example.org/x.zip` | "Indirizzo non consentito…" e "Solo link https://"; nulla cambia in `skills/` | |
| 33 | `/skill_remove <nome>`, poi `/skills` | "Rimossa: <nome>"; non compare più | |
| 34 | Da un utente autorizzato ma non admin: `/skill_add <link>` e `/skill_remove <nome>` | "Solo un amministratore può installare o rimuovere skill."; nessun download | |
| 35 | `/complex` con una richiesta che usa la skill installata al passo 30 | il ComplexTeam la usa | |
| 36 | `docker compose logs picobot` | righe `skill_add` / `skill_remove` con utente, canale, sorgente (senza credenziali né query) ed esito | |

**Configurazione in `config/config.yaml` (v0.8)**

| # | Prova | Atteso | Esito |
|---|---|---|---|
| 37 | Senza `config/config.yaml`: `docker compose up -d` | tutto come prima | |
| 38 | `cp config/config_example.yaml config/config.yaml`, `docker compose restart` | nessun warning "prevale su" nel log (se non hai le stesse chiavi in `.env`); comportamento identico, salvo i vocali accesi (`voice.stt_url`) | |
| 39 | `memory.history_runs: 10` e `web.region: us-en`, `docker compose restart`; poi la stessa chiave anche in `.env` | valori attivi; con la chiave anche in `.env` il log mostra "… (ambiente/.env) prevale su memory.history_runs …" | |
| 40 | `histroy_runs: 10` nel blocco `memory`, `docker compose restart` | il container non parte; `docker compose logs` mostra `Configurazione non valida: config/config.yaml: memory.histroy_runs: chiave sconosciuta` | |
