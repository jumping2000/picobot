# PicoBot v0.4 — collaudo manuale

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
