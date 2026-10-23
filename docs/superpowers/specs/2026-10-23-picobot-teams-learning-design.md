# PicoBot v0.5: SimpleTeam e ComplexTeam, profilo ed entità, richiamo esplicito — Design

Data: 2026-10-23 · Stato: da rivedere (rev. 3) · Base: spec 2026-10-22 rev. 2 (skill, MCP, file Office), implementata in v0.4

Questo documento descrive solo le modifiche rispetto alla v0.4. Quanto non è citato resta come nello spec rev. 2:
sandbox con conferma, skill estensibili e reload a caldo, MCP, consegna file, canali, scheduler, deps/Docker.

## 1. Obiettivo
Il router diventa un semplice smistatore verso tre strade: **SimpleTeam** (compiti rapidi, modello economico),
**ComplexTeam** (compiti complessi e documenti, modello forte) e **workflow riassunti**. Ogni strada si può anche
richiamare esplicitamente. Il router impara un profilo utente strutturato e un'agenda di progetti e persone, privati per utente.

**Criterio di successo:**
1. "quotazione dei miei titoli" usa i titoli salvati nel profilo, passando dal SimpleTeam;
2. "fammi un Word di una pagina su X" passa dal ComplexTeam: l'Analyst prepara il contenuto, il Writer produce il file
   (con conferma del codice) e lo consegna;
3. `/simple`, `/complex`, `/riassumi` e "usa il ComplexTeam per…" mandano la richiesta sulla strada indicata;
4. `/forget` cancella memorie, profilo ed entità dell'utente; `/memory` li mostra tutti e tre.

## 2. Decisioni (dall'utente)
- SimpleTeam è un team nuovo sotto il router (Web, Finance, Coder). Il router indirizza a SimpleTeam, ComplexTeam o workflow.
  Costo accettato: circa 2 chiamate in più per quotazione, ricerca o script rispetto alla v0.4.
- ComplexTeam: Researcher, Analyst, Writer, Critic, tutti con skill e MCP, tutti sul modello forte (`LLM_STRONG_MODEL_ID`,
  stesso provider e chiave; il Writer smette di usare il modello economico).
- L'Analyst ragiona, usa le skill e può eseguire codice per calcoli e grafici, ma non consegna il risultato finale:
  lo passa al Writer. Il Writer formatta e produce il risultato finale: testo e, con codice confermato, Word/PowerPoint/Excel;
  consegna i file.
- Coder con `deliver_file`, sempre limitato a `outputs/`.
- LearningMachine: profilo con campi `lingua`, `fuso_orario`, `formato_risposta`, `titoli_seguiti`; entity memory per
  progetti e persone ricorrenti, privata per utente. `/forget` cancella tutto.
- Un documento caricato (Telegram, CLI) passa dal router, che sceglie tra riassunto e altro. `/v1/summarize` resta diretto.
- Richiamo esplicito con comandi e con linguaggio naturale.
- Workflow: soglia di spezzatura a 100.000 caratteri.

Decisione di progetto: il Coder riceve anche `save_text_file`, così un file di testo semplice (es. un CSV scritto
a mano) dal SimpleTeam non richiede di eseguire codice e quindi nessuna conferma.

## 3. Fuori scope
Profilo o entità condivisi tra utenti; tool di scrittura del profilo negli agenti diversi dal router; `PROPOSE` e
learned knowledge; isolamento del codice di Writer e Analyst l'uno dall'altro; richiamo esplicito dei singoli membri
(es. "usa Finance"); scrittura del profilo da parte dei team richiamati direttamente.

## 4. Architettura
```
Router (Team coordinate, modello economico; sessione, memorie, profilo ed entità IN SCRITTURA)
 |- risponde da solo a conversazione e domande generali .......... 1 chiamata
 |- tool summarize_document(istruzioni) -> workflow riassunti
 |- SimpleTeam (Team coordinate, modello economico; profilo in sola lettura)
 |    |- Web       ricerca web
 |    |- Finance   yfinance (profilo in sola lettura: titoli seguiti)
 |    '- Coder     save_python_file, save_text_file, run_python, deliver_file
 '- ComplexTeam (Team coordinate, modello forte; skill; profilo in sola lettura)
      |- Researcher  ricerca web, skill, MCP
      |- Analyst     yfinance, run_python, run_node, read_document, skill, MCP  (niente deliver_file)
      |- Writer      save_text_file, run_python, run_node, deliver_file, read_document, skill, MCP
      '- Critic      skill, MCP (niente codice)
```
Il router non ha più Finance, Web e Coder come membri diretti. Hint dei nomi skill nel router: invariato.

## 5. Componenti
| Unità | Modifica |
|---|---|
| `agents.py` | `build_simple_team(s, learning_view)`; `build_complex_team` con Writer esecutore, Analyst senza `deliver_file`, tutti forti |
| `team.py` | router con membri `[SimpleTeam, ComplexTeam]` e tool `summarize_document` |
| `storage.py` | `PicoProfile` (sottoclasse di `UserProfile`), `make_learning` (profilo + entità, in scrittura), `make_learning_view` (sola lettura) |
| `tools/files.py` | nuovo tool `save_text_file(filename, content)` |
| `tools/documents.py` (nuovo) | `summarize_document` (router), `read_document` (ComplexTeam) sul documento della richiesta |
| `context.py` | `RunCtx.document: Path | None`, `RunCtx.document_name: str` |
| `service.py` | `ask(..., target="auto"|"simple"|"complex")`, `forget` completo, `memory_report` |
| `prompts.py` | ROUTER, SIMPLE_LEADER, COMPLEX_LEADER, ANALYST, WRITER aggiornati |
| `channels/*` | `/simple`, `/complex`, `/riassumi`; documento al router; `/memory` esteso; API `target` |
| `config.py` | `doc_chunk_chars = 100000` |

## 6. Routing e richiamo esplicito
- **Automatico (router):** conversazione → risponde; quotazioni, ricerche, script, file di testo semplici → SimpleTeam;
  documenti Word/PowerPoint/Excel/PDF, compiti con skill, compiti complessi → ComplexTeam; documento caricato con
  didascalia vuota o richiesta di riassunto → `summarize_document`; altre richieste su un documento → ComplexTeam.
- **Linguaggio naturale:** se l'utente nomina esplicitamente "SimpleTeam", "ComplexTeam" o "riassunto/workflow",
  il router obbedisce (regola nel prompt). Non garantito al 100% col modello economico: per la certezza ci sono i comandi.
- **Comandi (saltano il router, quindi 1-2 chiamate in meno):**
  - Telegram: `/simple <testo>`, `/complex <testo>`; `/riassumi [istruzioni]` come didascalia di un documento o in risposta
    a un messaggio con documento.
  - CLI: `/simple <testo>`, `/complex <testo>`, `/riassumi <percorso> [istruzioni]`; `/file <percorso> [richiesta]`
    passa ora dal router (come un upload).
  - API: `POST /v1/chat` con `target`: `auto` (default), `simple`, `complex`; `POST /v1/summarize` invariato (diretto).
- Una richiesta esplicita a un team è registrata nella sessione del router senza chiamate LLM (meccanismo già usato
  per i riassunti in v0.4), così le domande successive al router hanno il contesto.
- Il team richiamato direttamente vede il profilo in sola lettura; non aggiorna memorie né profilo.

## 7. Documenti caricati
- Telegram e CLI: il file va in `data/inbox/`, il contesto della richiesta porta `document` e `document_name`, il router
  riceve `[Documento caricato: <nome>] <didascalia>`. Il file viene cancellato a fine richiesta (come in v0.4).
- `summarize_document(istruzioni)` (solo router): esegue il workflow riassunti sul documento della richiesta e ne
  restituisce il testo; senza documento risponde che non ce n'è.
- `read_document(inizio=0)` (Analyst e Writer): testo estratto del documento a blocchi di 20.000 caratteri; il contenuto
  è marcato come dato non fidato (stessa regola anti-injection del workflow).
- `/riassumi` e `/v1/summarize`: workflow diretto, risultato registrato nella sessione.

## 8. ComplexTeam: Analyst e Writer
- Leader (prompt): chiama `list_skills(compito)`; delega ricerca al Researcher, ragionamento e calcoli all'Analyst,
  produzione e consegna al Writer passandogli il materiale dell'Analyst; Critic opzionale sulla bozza prima del Writer.
- Analyst: può usare `run_python`/`run_node` per calcoli e grafici in `outputs/` (il Writer può includerli), non consegna.
- Writer: per `.md`, `.txt`, `.csv`, `.html`, `.json` usa `save_text_file` (nessuna conferma: non è esecuzione di codice);
  per Word/PowerPoint/Excel legge la skill e lancia il codice con `run_node`/`run_python` (conferma a ogni esecuzione);
  consegna con `deliver_file`.
- Il tetto `CODE_MAX_RUNS` (6) resta per richiesta ed è condiviso da tutti gli esecutori.

`save_text_file(filename, content)`: nome senza percorso (niente `/`, `\`, `..`, max 120 caratteri), estensione tra
md, txt, csv, html, json e tra quelle di `OUTPUT_EXTENSIONS`, contenuto <= `MAX_OUTPUT_MB`, scrive in `outputs/`
(sovrascrive) e restituisce il percorso da passare a `deliver_file`.

## 9. Profilo ed entità
- `PicoProfile`: campi standard `name`, `preferred_name` più `lingua`, `fuso_orario` (IANA), `formato_risposta`,
  `titoli_seguiti` (ticker separati da virgola). Modalità AGENTIC: nessuna chiamata LLM in più.
- Entity memory: modalità AGENTIC, `namespace="user"` (privata), tool `remember_about`, `link_entities`,
  `search_entities`, `forget` solo sul router.
- Vista in sola lettura (`enable_agent_tools=False`, `agent_can_update_profile=False`): i leader di SimpleTeam e
  ComplexTeam vedono profilo ed entità, Finance vede il profilo; nessun tool di scrittura (verificato su Finance).
- Router: usa lingua e formato per le risposte; inoltra i titoli seguiti quando servono.
- `/forget` (con conferma): memorie + `delete_user_learnings(user_id)` (profilo ed entità). `/memory`: tre sezioni
  (memorie, profilo con i campi valorizzati, entità con tipo e descrizione). API: `GET /v1/memory` restituisce
  `memories`, `profile`, `entities`; `DELETE /v1/memory?confirm=true` cancella tutto.

## 10. Costi (misurati col modello simulato, salvo dove indicato)
| Richiesta | v0.4 | v0.5 |
|---|---|---|
| "ciao" | 1 chiamata, ~1.600 token | 1 chiamata, ~2.900 token (i 4 tool delle entità pesano ~1.100) |
| quotazione, ricerca, script | ~4 chiamate economiche | ~6 economiche (stima); `/simple` ~4 |
| documento Office | 7 chiamate, 5 forti | 7-8, quasi tutte forti (stima, Writer sul modello forte) |
| riassunto 70.000 caratteri | 5 chiamate | 1 workflow + 2 router; `/riassumi` 1 |

## 11. Errori
Strada esplicita non valida (API `target` sconosciuto) → 422. `summarize_document`/`read_document` senza documento →
messaggio all'agente. Documento non leggibile → `DocumentError` comunicato all'utente come oggi. Profilo o entità non
salvabili → warning, la risposta prosegue. `/forget` fallito su una delle tre parti → messaggio d'errore, nessuna conferma falsa.

## 12. Test (LLM finto)
1. Struttura: router con membri [SimpleTeam, ComplexTeam] e tool `summarize_document`; SimpleTeam con Web/Finance/Coder;
   Coder con `deliver_file`; ComplexTeam tutti forti, Writer con esecutori e `deliver_file`/`save_text_file`, Analyst
   senza `deliver_file`, Critic senza codice; skill e MCP su tutti i membri del ComplexTeam.
2. Profilo: campi personalizzati nel tool del router; salvati e visibili nel prompt di Finance e dei leader; isolati tra
   utenti; nessun tool di scrittura fuori dal router.
3. Entity memory: salvata, privata, visibile ai leader; `/forget` la cancella.
4. `/memory` e `GET /v1/memory` mostrano le tre sezioni; `/forget` e `DELETE` cancellano tutto.
5. Richiamo esplicito: `/simple`, `/complex`, `target` API, `/riassumi` (didascalia e risposta) eseguono la strada giusta
   senza chiamare il router; l'esito è nella sessione del router.
6. Upload: documento al router con `summarize_document`; altra richiesta → ComplexTeam con `read_document`.
7. `save_text_file`: nomi ostili, estensioni, dimensione; e2e Writer: `save_text_file` + `deliver_file` senza conferma;
   e2e Word: Writer con `run_node` confermato e file consegnato.
8. Workflow: con soglia 100.000 un documento da 70.000 caratteri fa 1 chiamata.
9. Regressione: tutti i 113 test esistenti verdi, adattati dove cambia la struttura.

Non verificabile in sviluppo: scelte reali del router col modello economico (inclusa la regola in linguaggio naturale),
qualità dei documenti, Telegram reale, build Docker.
