# PicoBot v0.6 — collaudo manuale

Prerequisiti: `.env` con chiave LLM reale, `TELEGRAM_BOT_TOKEN`, il tuo id in `TELEGRAM_ALLOWED_USER_IDS`, `API_TOKENS`;
skill `docx`, `pptx`, `xlsx` installate in `./skills`; `docker compose up -d --build` completato senza errori.

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
| 9 | Nuova libreria per una skill: aggiungi una riga a `deps/pip.txt` (o `uv run picobot skills deps --write`), `docker compose build && docker compose up -d` | la build completa; il pacchetto e' importabile dal codice dell'Analyst | |
| 10 | Telegram: "seguo AAPL e ENI", poi "quotazione dei miei titoli" | quotazioni di AAPL ed ENI senza ripeterli; `/memory` mostra il profilo | |
| 11 | `/simple quotazione MSFT` e `/complex scrivi una relazione su X` | rispondono senza passare dal router; una domanda successiva ne ha il contesto | |
| 12 | Invio di un PDF senza didascalia; poi lo stesso con didascalia "/riassumi in 3 punti" | entrambi riassunti; il secondo senza passare dal router | |
| 13 | Rispondi con `/riassumi breve` a un PDF inviato prima | riassunto breve | |
| 14 | Invio di un PDF con didascalia "fammi una presentazione PowerPoint da questo PDF" | il ComplexTeam legge il documento, il Writer produce il `.pptx` dopo la conferma | |
| 15 | "lavoro al progetto Harbor con Sara", poi `/forget` e conferma, poi `/memory` | dopo /forget nessuna memoria, profilo o entita' | |

**Messaggi vocali (v0.6)** — prerequisiti: `STT_URL=http://stt:8000`, `docker compose --profile stt up -d --build`, `stt` healthy (modello scaricato).

| # | Prova | Atteso | Esito |
|---|---|---|---|
| 16 | Vocale in italiano "quotazione di AAPL" | eco "🎤 quotazione di AAPL", poi la stessa risposta della frase scritta | |
| 17 | Vocale in inglese "what is the weather in London" | eco corretta, lingua `en` (log di `stt`), risposta in inglese | |
| 18 | Vocale muto (qualche secondo di silenzio) | "Non ho capito il vocale, puoi ripeterlo o scriverlo?"; nessuna risposta del router | |
| 19 | `docker compose stop stt`, poi un vocale, poi un messaggio scritto | "Trascrizione non disponibile al momento…"; il messaggio scritto riceve risposta | |
| 20 | File mp3 con didascalia "riassumi" | eco della trascrizione, poi un riassunto del contenuto | |
| 21 | `docker compose --profile stt run --rm stt python bench.py /models/<it>.ogg /models/<en>.ogg` | tabella con tempi e RTF per `base`/`small` × beam 1/5; annota qui la scelta di `STT_MODEL` e `STT_BEAM_SIZE` | |
