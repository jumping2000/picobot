# PicoBot v0.4 — assistente multi-agente (Agno 3): Telegram, CLI, API REST

## Architettura (costo minimo)
```
Router (Team coordinate, modello ECONOMICO, con sessione + memoria + learning)
 |- risponde da solo a domande/conversazione ............ 1 chiamata LLM
 |- Finance  (yfinance)         modello economico
 |- Web      (DuckDuckGo)       modello economico
 |- Coder    (Python, HITL)     modello economico
 '- ComplexTeam (leader + Researcher, Analyst, Writer, Critic)   modello STRONG
      task complessi e creazione di documenti Word/PowerPoint/Excel
      tutti usano le SKILL installate e i server MCP configurati
      solo l'Analyst esegue codice (Python/Node, con conferma) e consegna file
Workflow DocSummary: estrazione testo (codice) -> map parallelo se lungo -> riduzione (modello economico)
  Il riassunto entra nella sessione del router: i follow-up funzionano e costano 1 chiamata.
Scheduler: cron su SQLite, stessi prompt dell'utente, esito sul canale che li ha creati
```
Un task schedulato non puo' eseguire codice ne' produrre file (nessun umano per confermare).

## Skill (solo ComplexTeam, per tutti gli utenti)
Le skill sono cartelle nel formato Agent Skills (`SKILL.md` con frontmatter `name` e `description`, piu' eventuali
`scripts/` e riferimenti). Stanno in `./skills` sull'host, montata in sola lettura nel container.
- **Installare** = copiare la cartella in `./skills/` (il nome della cartella deve essere uguale al `name`).
  **Cancellare** = eliminarla. Il bot le vede alla richiesta successiva, **senza riavvio**.
- Oppure la CLI admin, dall'host (fa i controlli e installa in modo atomico):
  ```bash
  uv run picobot skills add /percorso/docx          # cartella, .zip o repository git (git deve essere installato)
  uv run picobot skills add skill.zip --force       # sostituisce una skill gia' installata
  uv run picobot skills list | remove <nome> | validate
  ```
  Default `--dir`: `SKILLS_DIR` se esiste, altrimenti `./skills`.
- Gli agenti del ComplexTeam valutano da soli se una skill aiuta: chiamano `list_skills(compito)` e leggono quella
  pertinente con `get_skill_instructions`. Il router conosce solo i nomi (fino a 15) per sapere quando delegare.
- Gli script dentro le skill **non** vengono eseguiti direttamente: l'Analyst scrive il codice e lo lancia con
  `run_python`/`run_node`, e ogni esecuzione chiede la tua conferma (Telegram: bottoni; CLI: y/N; API: `approve_code`).
- Telegram e CLI: `/skills` mostra l'elenco (solo lettura). Le skill non si installano da chat o API.
- Le skill di esempio `docx`, `pptx`, `xlsx` hanno licenza "All rights reserved" (termini Anthropic): uso personale,
  non ridistribuirle; `skills/` e' in `.gitignore`. Senza LibreOffice nell'immagine, il bot **crea** i file ma salta
  validazione, ricalcolo formule (si calcolano all'apertura in Excel), anteprime e conversioni PDF.

## Dipendenze delle skill (punti di estensione)
`deps/apt.txt`, `deps/pip.txt`, `deps/npm.txt` (una dipendenza per riga, versione esatta, `# skill: <nome>` come commento)
e `deps/setup.sh` (hook libero, eseguito come root in build). Gia' presenti quelle delle skill di esempio
(`docx@9.9.0`, `pptxgenjs@4.0.1`, `openpyxl==3.1.5`).
```bash
uv run picobot skills deps            # dipendenze dichiarate dalle skill (requirements.txt, package.json, apt.txt) mancanti in deps/
uv run picobot skills deps --write    # le aggiunge a deps/*.txt (non installa nulla)
docker compose build && docker compose up -d
```

## MCP
`config/mcp_config.json` (formato Claude Desktop): un server per voce, `"enabled": false` per disattivarlo.
Ogni server e' condiviso da tutti i membri del ComplexTeam. I server non raggiungibili vengono saltati.
Le modifiche richiedono il riavvio. **I tool MCP non chiedono conferma**: configura solo server fidati.
Nell'immagine ci sono `npx` (server Node) e `uvx` (server Python).

## Canali
- **Telegram**: testo, documenti (PDF/DOCX/TXT/MD/CSV/JSON/LOG; la didascalia = istruzioni), conferme a bottoni.
  Il codice da confermare e' mostrato per intero (oltre 1500 caratteri arriva come allegato prima dei bottoni).
  I file creati dagli agenti arrivano come documenti dopo la risposta.
- **CLI**: `python -m picobot cli` (conferme y/N, `/file <percorso>`, i file creati sono indicati con il percorso).
- **API**: `Authorization: Bearer <token>`; `POST /v1/chat` (risponde con `files: [{id, name, size}]`),
  `GET /v1/files/{id}` (download per 24 ore), `POST /v1/summarize` (multipart), `GET|DELETE /v1/memory`,
  `GET|POST /v1/schedules`, `DELETE /v1/schedules/{id}`, `GET /health`. Docs: `/docs`.
  Il codice si esegue solo con `"approve_code": true` nella richiesta.
  HTTPS diretto, senza reverse proxy: `API_SSL_CERTFILE` + `API_SSL_KEYFILE`.
- Comandi (Telegram/CLI): `/help /new /memory /forget(con conferma) /schedule /schedules /unschedule /skills`.

```bash
curl -X POST localhost:8000/v1/chat -H "Authorization: Bearer $TOKEN" -H "content-type: application/json" \
     -d '{"message":"crea un docx di una pagina sulle quotazioni di AAPL", "approve_code": true}'
curl -OJ localhost:8000/v1/files/<id> -H "Authorization: Bearer $TOKEN"
```

## Costi
- Domande semplici: 1 chiamata, modello economico (invariato).
- Router: circa 6 token per nome di skill (massimo 15 nomi) a ogni chiamata.
- ComplexTeam: snippet skill fisso; `list_skills` circa 40 token per skill, una volta per task.
- Documenti Office: passano dal ComplexTeam (modello forte), quindi costano piu' di una domanda semplice.

## Sicurezza
Telegram fail-closed (senza ID autorizzati non parte); token API confrontati a tempo costante, API su 127.0.0.1 di default
(`API_BIND=0.0.0.0` per esporla). Codice generato: sempre dopo conferma, massimo 6 esecuzioni per richiesta, processo separato,
env ripulito (nessuna chiave), timeout, limiti CPU/RAM/dimensione file, cwd = `workspace/`. Nel container `src/`, il venv e
`skills/` sono di root e non modificabili dal codice generato. Limiti: il codice generato ha rete libera e gira con lo stesso
utente del bot (puo' leggere `data/`): l'isolamento reale e' il container. I file consegnati escono solo da `workspace/outputs/`.

## Avvio
```bash
cp .env.example .env && mkdir -p data workspace skills && sudo chown -R 1000 data workspace
uv run picobot skills add /percorso/skills/docx      # opzionale: skill di esempio (anche pptx, xlsx)
docker compose up -d --build
```
`picobot serve` avvia Telegram + API + scheduler in un solo processo (flag `--no-telegram`, `--no-api`).
Test: `uv run --group dev pytest tests` (LLM finto, nessuna chiave). Collaudo manuale: `docs/manual-qa.md`.
