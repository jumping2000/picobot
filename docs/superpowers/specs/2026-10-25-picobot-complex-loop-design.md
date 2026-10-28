# PicoBot: ComplexTeam come workflow con ciclo di revisione — Design

Data: 2026-10-25 · Stato: da rivedere · Base: v0.7.0 (spec 2026-10-23 "SimpleTeam e ComplexTeam")

Questo documento descrive solo ciò che cambia nel ComplexTeam. SimpleTeam, workflow riassunti, memorie, sandbox con
conferma, skill, MCP, canali e scheduler restano come sono.

## 1. Perché
Oggi il ComplexTeam è un `Team` in modalità coordinate: un leader (modello forte) decide a parole chi chiamare e in che
ordine (Researcher → Analyst → Critic opzionale → Writer) e deve ricopiare a mano il materiale di un membro nel task del
successivo. Due problemi:

1. **Il Critic non ha effetto.** Dice "OK" o elenca correzioni, ma nulla obbliga l'Analyst a rifare il lavoro, né il
   leader a richiamarlo. L'ordine stesso dipende dal prompt.
2. **Il leader costa.** Ogni passaggio di materiale è output del leader sul modello forte; in più la sua sintesi finale.

Lo schema voluto:

```
Loop( Researcher → Analyst → Critic , max = TEAM_MAX_ITERATIONS , esce se Critic = "OK" )  →  Writer
```

Il Critic giudica il **pensiero** (allucinazioni, passaggi saltati, dati senza fonte), non la scrittura. Se non approva, si
ritorna a monte; solo a materiale approvato il Writer scrive, formatta, esegue il codice (con conferma) e consegna i file,
**una volta sola**.

**Criterio di successo:**
1. Una richiesta con un dato non verificato al primo giro viene corretta al secondo e il Writer parte solo dopo l'"OK".
2. Un file Word/PowerPoint/Excel viene consegnato una sola volta, qualunque sia il numero di giri.
3. Se il Critic non approva mai, dopo `TEAM_MAX_ITERATIONS` giri il Writer risponde comunque, dichiarando all'utente le
   riserve rimaste. L'utente non resta mai senza risposta.
4. Il lavoro per richiesta non supera `TEAM_MAX_ITERATIONS` × (Researcher + Analyst + Critic) + Writer chiamate di
   agente, e ogni giro è visibile nel log.

## 2. Decisioni dell'utente
- Schema del ciclo come sopra, con **Researcher dentro il ciclo** (oltre ad Analyst e Critic).
- Numero massimo di giri = `team_max_iterations`, ora **3** (prima 8, non usato dal codice).
- Il ciclo esce quando il Critic risponde "OK".
- Se il Critic non è d'accordo si ritorna indietro e si rivede il pensiero; **il Writer scrive solo dopo l'approvazione**.
- Il Writer resta fuori dal ciclo: ha gli effetti collaterali (conferme del codice, `deliver_file`).

## 3. Cosa ha mostrato la prova (script fuori dal repo, Agno 3.1.10)
Una prova con modelli gratuiti, ricerca finta e Critic scriptato (rifiuta il giro 1, approva il giro 2) ha stabilito:

**Funziona.** `Loop` con `end_condition` esce all'"OK"; il Writer gira dopo, una volta. La conferma del codice funziona
dentro gli step del ciclo (il `ContextVar` di `RunCtx` arriva agli agenti): `run_python` ha chiesto conferma in entrambi
i giri. Il Researcher rifà la ricerca nel secondo giro.

**Tre trappole, che questo design deve evitare:**
1. Con `forward_iteration_output=True`, `previous_step_content` dal secondo giro è **vecchio** (il Critic ha visto le
   proprie obiezioni del giro 1 invece dell'output dell'Analyst). `previous_step_outputs["<nome step>"]` invece è
   corretto. → Ogni step legge gli output **per nome**, mai `previous_step_content`.
2. Dopo il `Loop`, il Writer vede in `previous_step_outputs` solo il riepilogo del ciclo (chiave del Loop,
   "completed N iterations"); senza accorgimenti riceve solo l'ultimo output del Critic. Al primo tentativo ha risposto
   "OK. Nessuna riserva", senza materiale. → Il materiale approvato va consegnato al Writer esplicitamente (§5.3).
3. `ctx.runs` è unico per tutto il workflow. Con `CODE_MAX_RUNS=6` e fino a 3 giri, l'Analyst può esaurire il budget
   prima che parta il Writer (§5.5).

**Altro.** Uno step che solleva un'eccezione viene ritentato 3 volte (4 tentativi, `Step.max_retries=3` di default). Su
Writer e Analyst, che eseguono codice e consegnano file, un retry può ripetere effetti (§5.6).

**Non verificato dalla prova** (da provare con un test prima di fidarsi): vista di profilo/entità (`learning`) negli
agenti dentro un workflow; `StepOutput.steps` del Loop come fonte degli output interni; qualità reale del giudizio di un
Critic LLM (nella prova era scriptato).

## 4. Fuori scope e anti-obiettivi
**Fuori scope:** ragionamento nativo di Agno (`reasoning`); streaming o avanzamento per fase verso i canali; membri
richiamabili singolarmente; modifiche a SimpleTeam, router (modello e memorie) o workflow riassunti; revisione del file
finale prodotto dal Writer (il Critic vede il contenuto, non il file).

**Anti-obiettivi (sarebbe un fallimento anche se "funziona"):** tre giri di strong model su una richiesta banale; il
Writer che consegna due volte lo stesso file o una bozza; il Critic che blocca la risposta; stato condiviso tra utenti
diversi che usano il ComplexTeam in contemporanea.

## 5. Design

### 5.1 Dove si innesta
Un `Team` di Agno accetta solo `Agent` o `Team` come membri: **un `Workflow` non può restare tra i membri del router**.
Come già per i riassunti, il ComplexTeam diventa un **workflow richiamato da un tool del router**:

- `build_complex_workflow(s, registry, mcp_tools, db)` (nuovo, in `workflows/complex.py`) sostituisce
  `build_complex_team` in `agents.py`.
- Il router riceve il tool `complex_task(compito)` e `ComplexTeam` esce da `members`: il router ha come membro solo il
  `SimpleTeam`.
- `service.ask(target="complex")` esegue direttamente il workflow, con session id `"<sid>:complex"` (mai quello del
  router) e registra lo scambio nella sessione del router come oggi (`_record_in_session`).
- `files`/`deliver_file` e `ctx.outputs` non cambiano: gli agenti del workflow usano gli stessi tool e lo stesso `RunCtx`.

### 5.2 Passi del workflow
Giro `n` (1 ≤ n ≤ `TEAM_MAX_ITERATIONS`):

1. **Researcher** — giro 1: sempre eseguito; se la richiesta non richiede ricerca web risponde "NESSUNA RICERCA
   NECESSARIA" senza chiamare tool. Giri successivi: eseguito solo se l'ultimo verdetto del Critic è `RIFAI_RICERCA`
   (`Condition`). Con `RIFAI_ANALISI` si salta e si riusano i fatti già trovati.
2. **Analyst** — ragiona, calcola, può eseguire codice (conferma umana); al giro n>1 riceve la propria analisi
   precedente più le obiezioni del Critic e le corregge.
3. **Critic** — rivede il materiale e termina il giro. Disattivato (`ENABLE_CRITIC=false`) il ciclo si riduce a un solo
   giro senza Critic: Researcher → Analyst → Writer.

Poi, fuori dal ciclo: **Writer**.

Ogni agente riceve in modo esplicito: la richiesta originale dell'utente, gli output più recenti degli altri passi
(per nome), le obiezioni correnti del Critic. Il modo concreto di comporre il messaggio (executor a funzione che invoca
l'agente, o altro) è del costruttore, purché valga questa regola: un passo non usa mai `previous_step_content`, ma
legge `previous_step_outputs[<nome>]` (trappola 1, §3).

### 5.3 Verdetto del Critic e consegna al Writer
Il Critic risponde sempre in una forma leggibile dal codice: **prima riga** esattamente `OK`, `RIFAI_RICERCA` o
`RIFAI_ANALISI`, poi l'elenco puntuale delle correzioni. Qualsiasi altra prima riga conta come obiezione (mia scelta:
`RIFAI_ANALISI`), mai come approvazione.

Il passo Critic è un wrapper in codice: invoca l'agente, legge la prima riga e restituisce un `StepOutput` il cui
contenuto è **assemblato dal codice**, non copiato dall'LLM: verdetto, ultima analisi dell'Analyst, ultimi fatti del
Researcher (con URL) e le obiezioni residue. `end_condition` del `Loop` guarda solo la prima riga. Il passo Writer legge
il pacchetto dal risultato del ciclo (`StepOutput.steps` o un campo per-run; vedi §6) e lo riceve insieme alla richiesta
originale e alla regola: "se ci sono riserve residue, dichiarale all'utente".

Giri esauriti senza "OK": il ciclo termina da solo; il Writer riceve il pacchetto con le obiezioni residue e risponde
comunque (criterio di successo 3).

### 5.4 Stato per richiesta
Il workflow è costruito una volta all'avvio e condiviso da tutti gli utenti, come `doc_flow`. Nessuno stato nelle
closure o a livello di modulo (la prova li usava per i contatori): tutto ciò che varia per richiesta viaggia negli
`StepOutput`, nell'input o nel `RunCtx`. Un test lo verifica con due richieste concorrenti.

### 5.5 Budget del codice
`ctx.runs` conta le esecuzioni approvate per richiesta. Ogni esecuzione resta comunque sotto conferma umana: il tetto è
una protezione di costo, non di sicurezza. Mia scelta: il tetto `CODE_MAX_RUNS` vale **per fase** — `ctx.runs` si azzera
all'ingresso del Writer, così le esecuzioni dell'Analyst nei giri non tolgono budget alla produzione del documento.

### 5.6 Retry
Sui passi con effetti collaterali (Analyst, Writer) `max_retries=0`: un errore arriva al canale invece di rieseguire
codice o ripetere una consegna. Researcher e Critic possono mantenere il default.

### 5.7 Skill, profilo, MCP
- **Skill.** Il leader non c'è più (non chiama più `list_skills` né scrive "usa la skill X"). Tutti i membri hanno già il
  catalogo (`skills=`): Analyst e Writer chiamano `list_skills(compito)` come primo passo. Il prompt dell'Analyst e del
  Writer lo dicono esplicitamente. (Mia scelta.)
- **Profilo/entità** (lingua, fuso, formato, titoli). Oggi la vista in sola lettura sta sul leader. Nel workflow va su
  Analyst e Writer (`_view(s, db)`). Se la vista non funziona dentro un workflow, ripiego: il tool `complex_task` antepone
  il profilo letto al compito. Da verificare (§6).
- **MCP.** Gli stessi oggetti `MCPTools` condivisi, come oggi, su tutti i membri.

### 5.8 Router e prompt
- `ROUTER`: "delega a ComplexTeam" diventa "chiama `complex_task(compito)`"; per i documenti caricati vale come ora
  (riassunto → `summarize_document`, altro → `complex_task`); resta il rispetto della scelta esplicita
  ("usa il ComplexTeam").
- Il router restituisce il risultato di `complex_task` **così com'è**, senza riscriverlo.
- `COMPLEX_LEADER` sparisce; `RESEARCHER`, `ANALYST`, `WRITER`, `CRITIC` si adeguano (verdetto, `list_skills`, riserve,
  nessuna consegna fuori dal Writer). Il test sul prompt del leader cambia di conseguenza.

### 5.9 Configurazione e documentazione
- `TEAM_MAX_ITERATIONS` (default 3, ora usata): giri massimi del ciclo, valore ≥1. Non è più riusato per altro.
- `ENABLE_CRITIC` resta, con il significato di §5.2.
- Aggiornare `docs/it|en/configuration.md` (che dicono "default 8, non usata"), `architecture.md` (diagramma e
  sequenza), `README` (tabella "Two agent teams") e `CHANGELOG.md`.

## 6. Da lasciare al costruttore, ma da verificare con un test
- Come il Writer legge il pacchetto dopo il `Loop` (`StepOutput.steps` del Loop contiene gli output interni nella
  versione provata; non l'ho verificato come strada di produzione). Alternativa accettabile: stato per richiesta in
  `additional_data` o `session_state`.
- Che profilo/entità (`learning`) funzionino per agenti dentro un workflow con `user_id`; altrimenti il ripiego §5.7.
- Nome e posizione esatti di `max_retries` per step e se una `Condition` dentro un `Loop` vede gli output del giro.

## 7. Test (usando `tests/fake_llm.py`)
1. Giro 1 "RIFAI_ANALISI", giro 2 "OK": il Writer gira una sola volta, dopo l'"OK", e riceve l'**analisi del giro 2**.
2. Il Critic al giro 2 vede l'ultima analisi, non le proprie obiezioni vecchie (trappola 1).
3. Mai "OK": si fermano i giri a `TEAM_MAX_ITERATIONS`; il Writer risponde con le riserve.
4. `RIFAI_RICERCA` rilancia il Researcher; `RIFAI_ANALISI` no.
5. Prima riga non valida del Critic = obiezione, non approvazione.
6. `ENABLE_CRITIC=false`: un solo giro, nessun Critic.
7. `deliver_file` chiamato una volta sola; le esecuzioni dell'Analyst non tolgono budget al Writer (§5.5).
8. Errore nel Writer: nessun retry, l'errore esce.
9. Due richieste concorrenti non si scambiano stato (§5.4).
10. Il router chiama `complex_task`; `service.ask(target="complex")` esegue il workflow e registra lo scambio nella
    sessione del router; `test_core`, `test_teams`, `test_explicit`, `test_mcp` e `test_skills` aggiornati
    (il ComplexTeam non è più un membro).

## 8. Rischi
- **Costo:** fino a 3 giri sul modello forte. Il log per giro (verdetto, durata, chiamate) serve a misurarlo; il valore
  di `TEAM_MAX_ITERATIONS` si abbassa con un'impostazione.
- **Critic troppo severo o troppo permissivo:** non lo sappiamo finché non lo si prova con un modello reale; il prompt
  del Critic va tarato su richieste vere (non solo sul test scriptato).
- **Migrazione:** ComplexTeam non è più un `Team`; chi lo richiamava come membro (test, `service._member`) cambia.
