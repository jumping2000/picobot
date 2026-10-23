# PicoBot v0.5 — assistente multi-agente (Agno 3): Telegram, CLI, API REST

## Architettura
```
Router (Team coordinate, modello ECONOMICO; sessione, memorie, profilo ed entita' IN SCRITTURA)
 |- risponde da solo a conversazione e domande generali ...... 1 chiamata LLM
 |- summarize_document -> workflow riassunti (documento caricato, modello economico)
 |- SimpleTeam (modello economico; profilo in sola lettura)
 |    |- Web       ricerca web
 |    |- Finance   yfinance (vede i titoli seguiti)
 |    '- Coder     programmi Python (con conferma), file di testo, consegna file
 '- ComplexTeam (modello FORTE, tutti i membri; skill e MCP; profilo in sola lettura)
      |- Researcher  ricerca web approfondita
      |- Analyst     ragiona, analizza, calcola (anche con codice); passa il materiale al Writer
      |- Writer      scrive e produce il risultato finale (testo; Word/PowerPoint/Excel con codice) e lo consegna
      '- Critic      rivede la bozza
Workflow DocSummary: estrazione testo (codice) -> map parallelo solo oltre 100.000 caratteri -> riduzione
Scheduler: cron su SQLite, stessi prompt dell'utente, esito sul canale che li ha creati
```
Un task schedulato non puo' eseguire codice ne' produrre file (nessun umano per confermare).

## Richiamo esplicito
Il router sceglie da solo, ma puoi indicare la strada:
- **Comandi** (saltano il router): `/simple <richiesta>`, `/complex <richiesta>`; `/riassumi [istruzioni]` come
  didascalia di un documento o in risposta a un documento (CLI: `/riassumi <percorso> [istruzioni]`).
- **Linguaggio naturale**: "usa il ComplexTeam per…" viene rispettato dal router (non garantito al 100% col modello
  economico: per la certezza usa i comandi).
- **API**: `POST /v1/chat` con `"target": "auto" | "simple" | "complex"`; `POST /v1/summarize` e' sempre diretto.
Lo scambio con un team richiamato direttamente resta nella sessione: le domande successive hanno il contesto.

## Profilo, entita' e memoria (per utente)
- **Profilo**: lingua, fuso orario, formato preferito, titoli seguiti (oltre a nome e nome preferito). Basta dirlo:
  "seguo AAPL e ENI", "rispondimi a punti". Poi "quotazione dei miei titoli" usa i titoli salvati.
- **Entita'**: progetti e persone ricorrenti ("lavoro al progetto Harbor con Sara"), private per utente.
- **Memorie**: fatti duraturi su di te.
- Le scrive solo il router; i leader dei team e Finance le vedono in sola lettura.
- `/memory` (e `GET /v1/memory`) mostra memorie, profilo ed entita'; `/forget` (con conferma) e
  `DELETE /v1/memory?confirm=true` cancellano tutto.

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
- **Telegram**: testo, documenti (PDF/DOCX/TXT/MD/CSV/JSON/LOG): con didascalia vuota o "riassumi" li riassume,
  altrimenti la didascalia e' la richiesta (es. "fammi una presentazione da questo PDF"). Conferme a bottoni.
  Il codice da confermare e' mostrato per intero (oltre 1500 caratteri arriva come allegato prima dei bottoni).
  I file creati dagli agenti arrivano come documenti dopo la risposta.
- **CLI**: `python -m picobot cli` (conferme y/N; `/file <percorso> [richiesta]` passa dal router,
  `/riassumi <percorso>` riassume direttamente; i file creati sono indicati con il percorso).
- **API**: `Authorization: Bearer <token>`; `POST /v1/chat` (risponde con `files: [{id, name, size}]`),
  `GET /v1/files/{id}` (download per 24 ore), `POST /v1/summarize` (multipart), `GET|DELETE /v1/memory`,
  `GET|POST /v1/schedules`, `DELETE /v1/schedules/{id}`, `GET /health`. Docs: `/docs`.
  Il codice si esegue solo con `"approve_code": true` nella richiesta.
  HTTPS diretto, senza reverse proxy: `API_SSL_CERTFILE` + `API_SSL_KEYFILE`.
- Comandi (Telegram/CLI): `/help /new /simple /complex /riassumi /memory /forget(con conferma) /schedule /schedules
  /unschedule /skills`.

```bash
curl -X POST localhost:8000/v1/chat -H "Authorization: Bearer $TOKEN" -H "content-type: application/json" \
     -d '{"message":"crea un docx di una pagina sulle quotazioni di AAPL", "approve_code": true}'
curl -OJ localhost:8000/v1/files/<id> -H "Authorization: Bearer $TOKEN"
```

## Costi (misurati con il modello simulato)
| Richiesta | Chiamate |
|---|---|
| "ciao" | 1 economica (~2.900 token: i tool di profilo ed entita' pesano ~1.100) |
| quotazione, ricerca, script | ~5-6 economiche (router -> SimpleTeam -> membro); con `/simple` 2 in meno |
| documento Office | ~9, di cui ~7 sul modello forte (Analyst -> Writer) |
| riassunto di un documento fino a 100.000 caratteri | 1 del workflow, piu' 2 del router; con `/riassumi` solo 1 |
- Router: circa 6 token per nome di skill (massimo 15 nomi) a ogni chiamata.
- ComplexTeam: snippet skill fisso; `list_skills` circa 40 token per skill, una volta per task.

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
