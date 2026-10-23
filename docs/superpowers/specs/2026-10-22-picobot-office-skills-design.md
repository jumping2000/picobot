# PicoBot: skill estensibili, MCP e creazione file Office per il ComplexTeam — Design

Data: 2026-10-22 · Stato: da rivedere (rev. 2) · Percorso: architectural

## 1. Obiettivo
Gli agenti del ComplexTeam usano **skill standard** (formato Agent Skills) e **server MCP** installati e configurati.
Le skill si aggiungono e si cancellano con facilità, senza toccare il codice. Le tre skill iniziali (`docx`, `pptx`, `xlsx`)
sono solo un esempio e permettono di creare file Word, PowerPoint ed Excel. L'utente riceve il file sul canale da cui lo ha chiesto
(Telegram, CLI, API).

**Criterio di successo:** (a) da Telegram, "fammi un docx di una pagina" -> bottoni di conferma -> file ricevuto che si apre in Word;
(b) copiando una nuova cartella skill in `skills/` (o `picobot skills add`), senza riavvio, il ComplexTeam la trova e la usa;
(c) cancellandola, sparisce.

## 2. Decisioni
Dette dall'utente:
- Skill disponibili a **tutti gli utenti autorizzati** (non per utente) e al **solo ComplexTeam**: leader e tutti e 4 i membri
  (Researcher, Analyst, Writer, Critic). **Non** al router e **non** al Coder (cambia rispetto alla rev. 1).
- Anche gli **MCP** configurati sono usati da tutti i membri del ComplexTeam.
- Gli agenti del ComplexTeam **valutano da soli** se esiste una skill che facilita il compito.
- Sistema skill estensibile; installare e cancellare facile; punti di estensione per le librerie richieste dalle skill.
- Solo creazione di file (niente LibreOffice: niente ricalcolo formule, anteprime, conversioni PDF). Una conferma a ogni esecuzione di codice.
- Approccio: estendere il sandbox con Node (scartati: tool strutturati senza codice; sidecar isolato).

Decisioni di progetto:
- Solo l'**Analyst** esegue codice (`run_python`, `run_node`) e consegna file (`deliver_file`); gli altri membri delegano all'Analyst.
- Skill e MCP si gestiscono **solo dall'host** (admin), mai da chat o API: una skill guida un agente che esegue codice,
  installarla da una conversazione sarebbe una prompt injection persistente.
- Conseguenza accettata: i documenti Office passano dal ComplexTeam (modello forte), quindi costano più di una domanda semplice.

## 3. Fuori scope (MVP)
`validate.py`/`recalc.py`/`thumbnail.py` delle skill Office, modifica di file esistenti, OCR, `get_skill_script`,
conferma sui tool MCP, skill per utente, installazione skill da chat/API, hot reload MCP, installazione di pacchetti senza rebuild,
registry remoto o aggiornamento automatico delle skill, isolamento di rete, isolamento tra utenti nel workspace, pandas/markitdown.

## 4. Componenti
| Unità | Responsabilità |
|---|---|
| `skills.py` (nuovo) | `SkillRegistry` (cartella, mtime, reload), `CatalogSkills(Skills)` |
| `skills_cli.py` (nuovo) | `picobot skills list \| add \| remove \| validate \| deps` |
| `tools/sandbox.py` (esteso) | Runner comune; `save_python_file`, `run_python`, `run_node`; nomi script unici |
| `tools/files.py` (nuovo) | `deliver_file`, outbox API, pulizia TTL |
| `mcp_loader.py` | Un `MCPTools` per server, condiviso dai membri; flag `enabled` |
| `agents.py` | ComplexTeam (leader + 4 membri) con skill e MCP; `run_node`/`deliver_file` solo Analyst |
| `team.py`/`prompts.py` | Hint con i nomi delle skill nel router; regole di valutazione skill |
| `context.py`, `service.py`, `channels/*` | `Reply(text, files)`; `ConfirmFn(code, language)`; `/skills` in sola lettura |
| `deps/`, `Dockerfile`, `docker-compose.yaml` | Punti di estensione per librerie e skill montate |

Router (salvo l'hint), memoria, learning, scheduler, workflow documenti: invariati. Gli schedule non eseguono codice e non producono file.

## 5. Sistema skill
**Cartella.** `SKILLS_DIR` (host: `./skills`; container: `/app/skills`, montata **sola lettura**). Non è nell'immagine né nel repo
(`.gitignore`): le skill Office riportano "All rights reserved" e rimandano ai termini Anthropic dell'utente.
Installare = copiare una cartella; cancellare = eliminarla. Formato: cartella con `SKILL.md` (frontmatter `name`, `description`).

**Reload a caldo (verificato).** All'inizio di ogni `ask` (il router decide dopo se delegare; il controllo è un solo `stat`), se il `mtime` della cartella è cambiato, `SkillRegistry` chiama
`Skills.reload()`. Un'unica istanza è condivisa da leader e membri: aggiunta e rimozione sono viste da tutti senza riavvio.
Una skill non valida è saltata con un warning e non blocca le altre. Loader con `validate=False`: la validazione strict di Agno
rifiuta 96 skill reali su 251 per campi extra nel frontmatter.

**CLI admin (sull'host).**
- `list`: nome, descrizione, numero file, presenza di `scripts/`.
- `add <cartella|zip|git-url>` (git-url richiede `git` sull'host): valida, mostra il riepilogo (nome, descrizione, file, avviso se contiene `scripts/`, dipendenze dichiarate),
  copia in modo atomico (temp + rename). Duplicato: serve `--force`.
- `remove <nome>`; `validate`: ricontrolla tutte le skill installate.
- Controlli all'installazione: `SKILL.md` presente; `name` `[a-z0-9-]{1,64}` e uguale al nome cartella (la cartella viene rinominata);
  dimensione <= 50 MB; nessun symlink; zip senza percorsi assoluti né `..`.
- Telegram `/skills`: elenco in sola lettura per gli utenti autorizzati. Nessuna installazione da chat o API.

**Valutazione da parte degli agenti.** `CatalogSkills` espone `get_skill_instructions`, `get_skill_reference` e `list_skills(query)`;
`get_skill_script` è escluso. Lo snippet nel prompt è fisso e breve ("hai skill installate: chiama `list_skills()` e valuta se una
facilita il compito"), quindi **non cresce con il numero di skill**. `list_skills` restituisce nome e descrizione (<= 120 caratteri),
ordinati per sovrapposizione di parole con la query (nessun LLM), massimo `SKILLS_LIST_MAX` (50); query vuota = tutte.
Il leader del ComplexTeam chiama `list_skills` prima di delegare e scrive nel task "usa la skill X"; ogni membro può richiamarla se in dubbio.

**Router.** Non riceve skill. Riceve solo l'hint "Skill nel ComplexTeam: n1, n2, ..." (solo nomi, massimo `SKILLS_ROUTER_HINT_MAX` = 15,
oltre il quale resta la regola generica), aggiornato a caldo (verificato: `team.instructions` è modificabile a runtime).
Regola: richieste di creare documenti (Word, PowerPoint, Excel, PDF) o compiti per cui esiste una skill vanno al ComplexTeam.

## 6. MCP
`config/mcp_config.json` (formato attuale), caricato all'avvio. Un `MCPTools` per server, passato a **tutti** i membri del ComplexTeam
(verificato con un server MCP Python locale: due agenti chiamano lo stesso tool). Server non raggiungibile: saltato con warning.
Flag per server `"enabled": false`. Le modifiche alla config richiedono il riavvio. **Nessuna conferma sui tool MCP**: l'admin configura
solo server fidati; è un rischio noto e accettato per l'MVP. I requisiti dei server stanno nei punti di estensione della sez. 9
(Node/`npx` già presenti; per server Python l'immagine include anche `uvx`).

## 7. Esecuzione del codice
- Script con **nome unico** (`scripts/_run-<uuid>.py|.js`), cancellato a fine run (corregge il `_run.py` condiviso della v0.3).
- Python: `sys.executable`; Node: `node`; `cwd = workspace/`; `workspace/outputs/` e `scripts/` create all'avvio.
- Ambiente: solo `PATH`, `HOME=workspace`, `PYTHONIOENCODING`; Node anche `NODE_PATH`. Nessuna chiave.
- Limiti: CPU 60 s, timeout `CODE_TIMEOUT_S`, output troncato, `RLIMIT_AS` 768 MB (Python) / `CODE_NODE_MEM_MB` (Node, default 1536:
  `pptxgenjs` va in abort a 768 MB, `docx` regge), `RLIMIT_FSIZE` = 2 x `MAX_OUTPUT_MB`.
- Gate: `ctx.confirm(code, language)` a ogni esecuzione; API solo con `approve_code=true`; schedule bloccati.
- Tetto: `CODE_MAX_RUNS` (6) esecuzioni approvate per richiesta (anche pre-approvate via API), python e node insieme. I rifiuti non contano.

## 8. Consegna dei file
- `deliver_file` (Analyst): solo percorsi risolti dentro `workspace/outputs/`, senza symlink; estensioni in `OUTPUT_EXTENSIONS`
  (docx,pptx,xlsx,csv,txt,md,pdf); <= `MAX_OUTPUT_MB` (20); <= `MAX_OUTPUT_FILES` (5) per richiesta.
- Telegram: testo, poi `reply_document` per file; codice > 1500 caratteri inviato per intero come allegato prima dei bottoni.
- CLI: stampa il percorso locale. API: `/v1/chat` risponde con `files: [{id, name, size}]`; `GET /v1/files/{id}` (bearer);
  copia in `data/outbox/<user>/<id>/<name>`, id = 32 hex casuali; altrui o inesistente = 404; pulizia oltre `OUTBOX_TTL_H` (24).

## 9. Punti di estensione per le librerie (Docker)
- `deps/apt.txt`, `deps/pip.txt`, `deps/npm.txt`: una dipendenza per riga, versioni esatte, commenti `# skill: <nome>`.
  `deps/setup.sh`: hook opzionale, eseguito come root come ultimo passo, per tutto il resto.
- Dockerfile, in ordine (per la cache): `COPY deps/` -> apt (da `apt.txt`) -> `uv pip install -r deps/pip.txt` nel venv ->
  `npm install -g` (da `npm.txt`, con `NODE_PATH`) -> `setup.sh` -> `COPY src/`. Versioni pubblicate da almeno 14 giorni.
- Seed di esempio per le tre skill: `npm.txt` = `docx`, `pptxgenjs`; `pip.txt` = `openpyxl`; `apt.txt` vuoto.
  Le tre skill ufficiali non dichiarano file di dipendenze (verificato).
- `picobot skills deps`: legge i file opzionali nelle skill (`requirements.txt`, `package.json`, `apt.txt`) e stampa le dipendenze
  mancanti in `deps/`; `--write` le aggiunge (mai installa). Dopo una modifica: `docker compose build && docker compose up -d`.
- Hardening: nell'immagine `src/`, `.venv` e `skills/` sono di root e di sola lettura per l'utente `picobot`;
  scrivibili solo `data/` e `workspace/`. Il codice generato non può modificare il bot né le skill (corregge `chown -R picobot /app` della v0.3).
- Compose: `./skills:/app/skills:ro`, `./config:/app/config:ro`, `./workspace`, `./data`. Nessun LibreOffice.

## 10. Costi
- Router: circa 6 token per nome di skill (massimo 15 nomi) a ogni chiamata.
- ComplexTeam: snippet fisso piccolo; `list_skills` costa circa 40 token per skill, una volta per task (confronto: inline 225 token per skill per membro per chiamata).
- Documenti Office: modello forte del ComplexTeam. Domande semplici: invariate (1 chiamata, modello economico).

## 11. Errori
Nessun errore dei tool fa cadere il bot. Skill non valida: saltata. Reload fallito: resta l'elenco precedente. MCP irraggiungibile: saltato.
Node o pacchetto mancante: stderr all'agente. Conferma rifiutata o scaduta: "annullato". `deliver_file` rifiutato: messaggio chiaro.
Invio Telegram fallito: avviso e log.

## 12. Test (LLM finto)
1. Gate `run_node`/`run_python`: sì, no, pre-approvato API, schedule bloccato, env ripulito, timeout, memoria, tetto, nomi unici.
2. Generazione reale: docx, pptx, xlsx validi (zip + content types); saltati se Node/pacchetti mancano.
3. `deliver_file`: path traversal, symlink, estensione, dimensione, solo `outputs/`, tetto file.
4. Skill: add/remove/validate; zip con `..` rifiutato; symlink; nome non valido; duplicato senza `--force`; skill non valida saltata;
   reload a caldo visto da leader e membri; `list_skills` con query; nessun `get_skill_script`; router/Coder senza skill; hint nomi nel router.
5. MCP: server Python di prova usato da tutti i membri; server rotto saltato; `enabled=false`.
6. `skills deps`: rileva mancanti e `--write` non duplica.
7. Canali: documento Telegram (mock), codice lungo allegato, API con download del proprietario / 404 / TTL, CLI, `/skills`.
8. Regressione: i 30 test esistenti verdi (adattati a `Reply` e `ConfirmFn`). Controllo statico del Dockerfile: percorsi `deps/` coerenti.

Non verificabile in sviluppo: qualità degli script di un LLM reale, Telegram reale, build Docker, server MCP reali (es. filesystem via `npx`).
Collaudo manuale alla consegna: docx, pptx, xlsx da Telegram; aggiunta e rimozione di una skill a caldo; un server MCP reale.

Fasi proposte per il piano: (A) sandbox Node, `deliver_file`, `Reply`, consegna sui canali; (B) registry skill, `CatalogSkills`, CLI, hint nel router; (C) MCP condiviso, `deps/` e Dockerfile, hardening.
