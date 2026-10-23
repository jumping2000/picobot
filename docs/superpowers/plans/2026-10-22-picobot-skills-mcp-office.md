# PicoBot v0.4: skill estensibili, MCP e file Office nel ComplexTeam — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Il ComplexTeam usa skill standard (installabili/cancellabili a caldo) e MCP, esegue Node/Python con conferma e consegna file Word/PowerPoint/Excel sui tre canali.

**Architecture:** Esteso il sandbox con `run_node` e un tetto di esecuzioni; `deliver_file` + `Reply(text, files)` portano i file ai canali; `SkillRegistry`/`CatalogSkills` (sottoclasse di `agno.skills.Skills` senza `get_skill_script`) condivisi da leader e membri del ComplexTeam; CLI admin `picobot skills`; `deps/` e Dockerfile come punti di estensione.

**Tech Stack:** Python >=3.11, Agno `>=3.1.0,<4`, FastAPI, python-telegram-bot 21.10, Node (`docx`, `pptxgenjs`), `openpyxl`, `fastmcp` (test MCP), pytest.

**Spec:** `docs/superpowers/specs/2026-10-22-picobot-office-skills-design.md` (rev. 2). Il progetto parte dalla v0.3 (`/home/claude/out/picobot`, 30 test verdi).

## Global Constraints
- Test: `python -m pytest -q tests -p no:cacheprovider`; i 30 test esistenti restano verdi in ogni task (si adattano solo dove indicato).
- Skill solo al ComplexTeam (leader + Researcher, Analyst, Writer, Critic); **mai** al router né al Coder. Solo l'Analyst ha `run_python`, `run_node`, `deliver_file`. `get_skill_script` escluso ovunque.
- Conferma a ogni esecuzione di codice (`ctx.confirm(code, language)`); API solo con `approve_code=true`; schedule bloccati.
- Limiti: CPU 60 s; `RLIMIT_AS` 768 MB Python / `CODE_NODE_MEM_MB`=1536 Node; `RLIMIT_FSIZE` = 2 x `MAX_OUTPUT_MB`; `CODE_MAX_RUNS`=6 (conta le approvate, anche pre-approvate API; i rifiuti no).
- Consegna: `MAX_OUTPUT_MB`=20, `MAX_OUTPUT_FILES`=5, `OUTPUT_EXTENSIONS`=docx,pptx,xlsx,csv,txt,md,pdf, solo dentro `workspace/outputs/`, niente symlink; `OUTBOX_TTL_H`=24; id file = 32 hex; altrui/inesistente = 404.
- Codice Telegram > 1500 caratteri: inviato per intero come allegato prima dei bottoni.
- Skill: nome `[a-z0-9-]{1,64}` = nome cartella; <= 50 MB; niente symlink; zip senza percorsi assoluti né `..`; loader `validate=False`; `SKILLS_LIST_MAX`=50; descrizione in `list_skills` <= 120 caratteri; `SKILLS_ROUTER_HINT_MAX`=15 (solo nomi); snippet di sistema a lunghezza fissa. Gestione skill/MCP solo da host (nessuna da chat/API); `/skills` Telegram solo lettura.
- Dockerfile: `skills/` montata `:ro`, non nell'immagine né nel repo; `src/`, `.venv`, `skills/` di root e non scrivibili dall'utente `picobot`; versioni npm/pip esatte e pubblicate da >= 14 giorni; nessun LibreOffice; `uvx` copiato accanto a `uv`.
- Testi per l'utente in italiano.

## Review Focus
1. Zip con layout/nomi ostili (cartella radice vs file in radice, `../x`, percorso assoluto, nome `../x` nel frontmatter) -> rifiuto pulito, nessun residuo. (Task 10)
2. Skill a metà installazione visibile al registry durante la copia -> cartelle `.tmp-*`/`_*` ignorate; installazione atomica. (Task 7, 10)
3. Richieste parallele: contatori e nomi script isolati per richiesta. (Task 2)
4. Nomi file con spazi/accenti ("Relazione città.docx") da `deliver_file` fino a Telegram e API. (Task 3, 5, 6)
5. Node/`PATH` mancante o cartella skill assente/illeggibile all'avvio -> messaggio all'agente / nessuna skill, mai crash. (Task 2, 7)

## File Structure
| File | Stato | Responsabilità |
|---|---|---|
| `src/picobot/context.py` | mod | `OutputFile`, `Reply`, `ConfirmFn(code, language)`, `RunCtx.outputs/runs` |
| `src/picobot/config.py` | mod | nuove variabili d'ambiente e proprietà |
| `src/picobot/tools/sandbox.py` | mod | executor comune, `run_node`, tetto, nomi unici |
| `src/picobot/tools/files.py` | nuovo | `deliver_file`, outbox API |
| `src/picobot/skills.py` | nuovo | `SkillInfo`, `CatalogSkills`, `SkillRegistry` |
| `src/picobot/skills_cli.py` | nuovo | install/list/remove/validate/deps + dispatch `picobot skills` |
| `src/picobot/mcp_loader.py` | mod | flag `enabled` |
| `src/picobot/agents.py`, `team.py`, `prompts.py`, `service.py` | mod | cablaggio skill/MCP, hint router, `Reply` |
| `src/picobot/channels/{telegram,cli,api,common}.py`, `__main__.py` | mod | consegna file, `/skills`, `skills` subcommand |
| `deps/{apt,pip,npm}.txt`, `deps/setup.sh`, `Dockerfile`, `docker-compose.yaml`, `.env.example`, `.gitignore` | nuovo/mod | punti di estensione e hardening |
| `tests/test_*.py`, `tests/fake_llm.py`, `tests/mcp_probe_server.py` | nuovo/mod | test per task |

---
## Parte A — Sandbox, file, canali

### Task 1: Contesto, `Reply`, configurazione
**Files:** Modify `context.py`, `config.py`; Test `tests/test_context_config.py`
**Interfaces — Produces:**
`ConfirmFn = Callable[[str, str], Awaitable[bool]]` (codice completo, `"python"|"node"`); `OutputFile(path: Path, name: str, size: int)`; `Reply(text: str, files: list[OutputFile] = [])`; `RunCtx(user_id, channel, confirm=None, pre_approved=False, outputs: list[OutputFile]=[], runs: int=0)`; `Settings`: `code_node_mem_mb=1536, code_max_runs=6, max_output_mb=20, max_output_files=5, output_extensions="docx,pptx,xlsx,csv,txt,md,pdf", outbox_ttl_h=24, enable_skills=True, skills_dir=Path("/app/skills"), skills_list_max=50, skills_router_hint_max=15, node_path=""` e proprietà `output_ext_set -> set[str]`, `outputs_dir == workspace_dir/"outputs"`, `outbox_dir == data_dir/"outbox"`.

- [ ] **Step 1:** nel progetto: `git init && git add -A && git commit -m "chore: baseline v0.3"`.
- [ ] **Step 2: test che falliscono**
```python
def test_defaults():
    s = Settings()
    assert (s.code_node_mem_mb, s.code_max_runs, s.max_output_mb, s.max_output_files, s.outbox_ttl_h) == (1536, 6, 20, 5, 24)
    assert s.output_ext_set == {"docx","pptx","xlsx","csv","txt","md","pdf"}
    assert (s.skills_list_max, s.skills_router_hint_max, s.enable_skills) == (50, 15, True)
    assert s.outputs_dir == s.workspace_dir/"outputs" and s.outbox_dir == s.data_dir/"outbox"
def test_runctx_and_reply():
    c = RunCtx("u", "api"); assert c.outputs == [] and c.runs == 0 and not c.can_run_code
    assert Reply("x").files == []
```
- [ ] **Step 3:** esegui `pytest tests/test_context_config.py -v` -> FAIL (attributi mancanti).
- [ ] **Step 4:** implementa i tipi e i campi sopra (liste con `field(default_factory=list)`; `output_ext_set` = split CSV, minuscolo).
- [ ] **Step 5:** `pytest tests/test_context_config.py -v` -> PASS; suite completa verde (la modifica è additiva).
- [ ] **Step 6:** `git add -A && git commit -m "feat: contesto Reply/OutputFile e nuove impostazioni"`.

### Task 2: Executor comune, `run_node`, tetto, nomi unici
**Files:** Modify `tools/sandbox.py`, `pyproject.toml` (gruppo dev), `tests/fake_llm.py`, `tests/test_core.py`, `channels/telegram.py` (solo la lambda di conferma), `channels/cli.py` (solo `confirm`); Test `tests/test_sandbox_node.py`
**Interfaces — Consumes:** Task 1. **Produces:** `make_code_tools(s) -> [save_python_file, run_python]` (invariata per il Coder); `make_node_tools(s) -> [run_node]`; entrambi i run chiamano `await ctx.confirm(code, language)` con il codice **completo**.

- [ ] **Step 1: test che falliscono** (`node` assente = `pytest.skip`):
```python
def test_run_node_after_confirm():
    seen = []
    async def yes(code, lang): seen.append((code, lang)); return True
    out = run_in_ctx(RunCtx("u","telegram",confirm=yes), run_node, "console.log(6*7)")
    assert "exit=0" in out and "42" in out and seen == [("console.log(6*7)", "node")]
def test_node_env_clean_and_node_path():
    s = Settings(node_path="/x/modules")
    out = run_in_ctx(PRE, make_node_tools(s)[0], "console.log(process.env.OPENROUTER_API_KEY, process.env.NODE_PATH)")
    assert "undefined /x/modules" in out
def test_run_cap_counts_only_approved():
    s = Settings(code_max_runs=2); ctx = RunCtx("u","api",pre_approved=True); rp = make_code_tools(s)[1]
    outs = [run_in_ctx(ctx, rp, "print(1)") for _ in range(3)]
    assert "exit=0" in outs[0] and "exit=0" in outs[1] and "limite raggiunto" in outs[2] and ctx.runs == 2
    async def no(code, lang): return False
    no_ctx = RunCtx("u","telegram",confirm=no); run_in_ctx(no_ctx, rp, "print(1)"); assert no_ctx.runs == 0
def test_parallel_runs_isolated(tmp_path):   # Review Focus 3
    outs = asyncio.run(gather_in_ctxs(rp, ["print('A')", "print('B')", "print('C')"]))   # un RunCtx pre-approvato per ciascuno
    assert [o.split("\n")[1] for o in outs] == ["A", "B", "C"] and not list((ws/"scripts").glob("_run*"))
def test_node_missing_path(monkeypatch):     # Review Focus 5
    monkeypatch.setenv("PATH", "/nonexistent")
    assert "node" in run_in_ctx(PRE, run_node, "1").lower() and "non" in out.lower()   # messaggio, nessuna eccezione
@pytest.mark.parametrize("ctx", [None, RunCtx("u","schedule"), RunCtx("u","api")])
def test_run_node_blocked_without_human(ctx): assert "NON consentita" in run_in_ctx(ctx, run_node, "1")
def test_dirs_created_at_tool_build(tmp_path):
    s = Settings(workspace_dir=tmp_path/"w"); make_node_tools(s); make_code_tools(s)
    assert (s.workspace_dir/"outputs").is_dir() and (s.workspace_dir/"scripts").is_dir()
def test_real_office_generation(tmp_path):   # salta se mancano node, docx/pptxgenjs (NODE_PATH = `npm root -g`) o openpyxl
    s = Settings(workspace_dir=tmp_path/"w", node_path=npm_root_g())
    docx = "const {Document,Packer,Paragraph}=require('docx');const fs=require('fs');Packer.toBuffer(new Document({sections:[{children:[new Paragraph('x')]}]})).then(b=>fs.writeFileSync('outputs/a.docx',b))"
    pptx = "const P=require('pptxgenjs');const p=new P();p.addSlide().addText('x',{x:1,y:1});p.writeFile({fileName:'outputs/a.pptx'})"
    xlsx = "import openpyxl; wb=openpyxl.Workbook(); wb.active['A1']='=1+1'; wb.save('outputs/a.xlsx')"
    for code, name, tool in [(docx,"a.docx",run_node),(pptx,"a.pptx",run_node),(xlsx,"a.xlsx",run_python)]:
        assert "exit=0" in run_in_ctx(PRE, tool_of(s, tool), code)
        z = zipfile.ZipFile(s.workspace_dir/"outputs"/name); assert z.testzip() is None and "[Content_Types].xml" in z.namelist()
```
Aggiungi in `fake_llm.py`: `elif "run_node" in names and "esegui node" in user: tool_call run_node(code="console.log(42)")`.
- [ ] **Step 2:** `pytest tests/test_sandbox_node.py -v` -> FAIL.
- [ ] **Step 3: implementa** in `sandbox.py` `async def _execute(s, ctx, code, language) -> str`: gate (`can_run_code`; se `confirm` -> `await ctx.confirm(code, language)`), tetto (`ctx.runs >= s.code_max_runs` -> "limite raggiunto", altrimenti `ctx.runs += 1` solo dopo conferma/pre-approvazione), file `scripts/_run-<uuid4 hex>.py|.js` cancellato in `finally`, env `PATH, HOME=workspace, PYTHONIOENCODING` (+ `NODE_PATH=s.node_path` per Node se non vuoto), `RLIMIT_AS` = 768 MB / `code_node_mem_mb`, `RLIMIT_CPU` 60, `RLIMIT_FSIZE` = 2x`max_output_mb`; `FileNotFoundError` dell'eseguibile -> stringa d'errore. `make_code_tools`/`make_node_tools` creano `workspace/outputs` e `workspace/scripts` alla costruzione. Aggiungi `openpyxl` al gruppo `dev` di `pyproject.toml` (solo test). `run_python`/`run_node` sono wrapper sottili.
- [ ] **Step 4:** adatta `test_core.py` (`async def yes(code, language)` ecc.), `telegram.py` (`lambda code, language: ...` ancora con `ask_yes_no`) e `cli.py` (`confirm(code, language)`). Suite completa -> PASS.
- [ ] **Step 5:** `git commit -am "feat: run_node, tetto esecuzioni, nomi script unici"`.

### Task 3: `deliver_file`
**Files:** Create `tools/files.py`; Test `tests/test_files.py`
**Interfaces — Produces:** `make_file_tools(s) -> [deliver_file]`; `async deliver_file(path: str) -> str` (path relativo a `workspace/`, aggiunge `OutputFile` a `ctx.outputs`).

- [ ] **Step 1: test che falliscono** (workspace temporaneo, `ctx` via `set_ctx`):
```python
def test_deliver_ok_and_dedup():   # "Relazione città.docx" con spazio e accento (Review Focus 4)
    assert "Consegnato" in run(deliver("outputs/Relazione città.docx")); run(deliver("outputs/Relazione città.docx"))
    assert [f.name for f in ctx.outputs] == ["Relazione città.docx"]
@pytest.mark.parametrize("p", ["../x.docx", "/etc/passwd", "outputs/../scripts/a.docx", "outputs/a.exe", "scripts/a.docx"])
def test_deliver_refused(p): assert "rifiutato" in run(deliver(p)).lower() and ctx.outputs == []
def test_symlink_refused():
    os.symlink(outside_file, outputs/"link.docx"); assert "rifiutato" in run(deliver("outputs/link.docx")).lower() and ctx.outputs == []
def test_size_and_count():     # Settings(max_output_mb=1)
    (outputs/"big.docx").write_bytes(b"x"*2*1024*1024); assert "rifiutato" in run(deliver("outputs/big.docx")).lower()
    for i in range(6): (outputs/f"f{i}.docx").write_bytes(b"x"); res = [run(deliver(f"outputs/f{i}.docx")) for i in range(6)]
    assert len(ctx.outputs) == 5 and "rifiutato" in res[5].lower()
def test_no_ctx(): assert "rifiutato" in run(deliver("outputs/a.docx")).lower()
```
- [ ] **Step 2:** run -> FAIL.
- [ ] **Step 3:** implementa: risolvi `(workspace/path).resolve()`, richiedi `is_relative_to(outputs_dir.resolve())`, nessun componente symlink (`Path.is_symlink` su ogni livello dentro outputs), `suffix.lower()` in `output_ext_set`, `st_size <= max_output_mb*1MiB`, `len(ctx.outputs) < max_output_files`, dedup per percorso. Messaggi in italiano, prefisso "Rifiutato:" o "Consegnato:".
- [ ] **Step 4:** `pytest tests/test_files.py -v` -> PASS. **Step 5:** `git add -A && git commit -m "feat: deliver_file con controlli"`.

### Task 4: Outbox per l'API
**Files:** Modify `tools/files.py`; Test `tests/test_files.py`
**Interfaces — Produces:** `store_outputs(s, user_id: str, files: list[OutputFile]) -> list[dict]` (`{"id","name","size"}`); `find_output(s, user_id: str, file_id: str) -> Path | None`; `purge_outbox(s) -> int` (rimossi).

- [ ] **Step 1: test**
```python
def test_store_find_other_user():
    meta = store_outputs(s, "alice", [of])[0]
    assert re.fullmatch(r"[0-9a-f]{32}", meta["id"]) and find_output(s, "alice", meta["id"]).read_bytes() == b"x"
    assert find_output(s, "bob", meta["id"]) is None and find_output(s, "alice", "../x") is None
def test_purge_ttl(): # una cartella con mtime 25 h fa -> rimossa; una nuova resta
```
- [ ] **Step 2:** FAIL. **Step 3:** implementa (id `uuid4().hex`, copia in `outbox_dir/<user>/<id>/<name>`, `find_output` valida l'id con regex e che il percorso resti in outbox; purge su mtime `> outbox_ttl_h`). **Step 4:** PASS. **Step 5:** commit `feat: outbox file API`.

### Task 5: `service.ask` -> `Reply`, consegna Telegram
**Files:** Modify `service.py`, `channels/telegram.py`, `channels/cli.py`, `channels/api.py` (solo `.text`), `tests/*` che confrontano l'esito di `ask`; Test `tests/test_channels.py`
**Interfaces — Consumes:** Task 1, 4. **Produces:** `PicoBotService.ask(text, *, user_id, session_id, ctx=None) -> Reply` (`Reply(text, list(ctx.outputs))`); `PicoBotService._ask_text(...) -> str` (lo `Scheduler` la riceve come `run_fn`, quindi `scheduler.py` non cambia); `TelegramGateway.send_reply(update, reply: Reply)`; `TelegramGateway.confirm_code(bot, chat_id, user_id, code: str, language: str) -> bool`.

- [ ] **Step 1: test che falliscono**
```python
def test_ask_returns_reply_with_files(svc):
    ctx = RunCtx("1","api"); ctx.outputs.append(of)
    r = run(svc.ask("ciao", user_id="1", session_id="r1", ctx=ctx)); assert isinstance(r, Reply) and r.files == [of] and r.text
def test_send_reply_documents():      # due file -> testo prima, poi 2 reply_document con i nomi giusti
def test_confirm_code_long_is_attached():   # 2000 caratteri, "node" -> send_document(filename="codice.js") PRIMA del messaggio con bottoni
def test_confirm_code_short_inline():       # 100 caratteri -> nessun send_document, il testo contiene il codice
def test_send_failure_is_reported():        # reply_document solleva -> "Impossibile inviare il file", nessuna eccezione; nome "Relazione città.docx" passato intatto
```
- [ ] **Step 2:** FAIL. **Step 3:** implementa `ask` come sopra (+ `_ask_text` passato a `Scheduler`); `confirm_code`: se `len(code) > 1500` invia `bot.send_document(chat_id, document=BytesIO(code.encode()), filename="codice.js"|"codice.py")` poi `ask_yes_no` con testo breve, altrimenti codice nel messaggio; `send_reply`: `send_safe(text)` poi un `reply_document` per file (try/except -> messaggio d'errore + `logger.exception`); `on_message` usa `confirm=lambda code, lang: self.confirm_code(...)` e `send_reply`. CLI stampa `reply.text`; API usa `reply.text`.
- [ ] **Step 4:** aggiorna i test che confrontavano `str`. Suite completa -> PASS. **Step 5:** commit `feat: Reply e consegna Telegram`.

### Task 6: Consegna CLI e API
**Files:** Modify `channels/api.py`, `channels/cli.py`; Test `tests/test_channels.py`
**Interfaces — Consumes:** `store_outputs`, `find_output`, `purge_outbox`, `Reply`. **Produces:** `FileOut(id: str, name: str, size: int)`; `ChatOut.files: list[FileOut]`; `GET /v1/files/{file_id}` (bearer).

- [ ] **Step 1: test che falliscono** (con `monkeypatch` di `svc.ask` che restituisce `Reply` con un file reale in `workspace/outputs/Relazione città.docx`):
```python
async def t(c, svc):
    r = (await c.post("/v1/chat", json={"message":"x"}, headers=A)).json()
    f = r["files"][0]; assert f["name"] == "Relazione città.docx" and f["size"] == 5
    d = await c.get(f"/v1/files/{f['id']}", headers=A)
    assert d.status_code == 200 and d.content == b"hello" and "filename*" in d.headers["content-disposition"]
    assert (await c.get(f"/v1/files/{f['id']}", headers=B)).status_code == 404
    assert (await c.get("/v1/files/" + "0"*32, headers=A)).status_code == 404
    assert (await c.get(f"/v1/files/{f['id']}")).status_code == 401
def test_cli_prints_file_path(monkeypatch, capsys):   # run_cli con ask -> Reply(file): l'output contiene f"File: {path}"
def test_startup_purges_old_outbox(tmp_path):   # cartella outbox con mtime 25 h fa: dopo `await svc.start()` non esiste più
```
- [ ] **Step 2:** FAIL. **Step 3:** `/v1/chat`: `purge_outbox(s)`, `store_outputs(...)`, risposta con `files`; endpoint download con `FileResponse(path, filename=name)`; 404 identico per altrui/inesistente/id non valido. `PicoBotService.start()` chiama `purge_outbox(s)`. CLI: dopo il testo, `print(f"File: {f.path}")`.
- [ ] **Step 4:** PASS (suite completa). **Step 5:** commit `feat: consegna file CLI e API`.

---
## Parte B — Skill estensibili

### Task 7: `CatalogSkills` e `SkillRegistry`
**Files:** Create `skills.py`; Test `tests/test_skills.py`
**Interfaces — Produces:** `NAME_RE = re.compile(r"^[a-z0-9-]{1,64}$")`; `SkillInfo(name: str, description: str, files: int, has_scripts: bool)`; `CatalogSkills(Skills)` con tool `get_skill_instructions`, `get_skill_reference`, `list_skills(query: str = "") -> str` (nessun `get_skill_script`); `SkillRegistry(s: Settings)` con `.skills: CatalogSkills | None` (None se `enable_skills=False`), `.refresh(force: bool=False) -> bool` (True se cambiato), `.names() -> list[str]`, `.info() -> list[SkillInfo]`.

- [ ] **Step 1: test che falliscono** (cartella skill temporanea; helper `mk(name, desc, extra="")`):
```python
def test_loads_valid_and_extra_frontmatter(): mk("docx","Word", extra="argument-hint: x\neffort: low"); assert reg.names() == ["docx"]
def test_invalid_skipped_not_fatal(): (d/"bad").mkdir(); (d/"bad"/"SKILL.md").write_text("niente frontmatter"); mk("ok","x"); assert reg.names() == ["ok"]
def test_partial_and_bad_names_ignored():   # Review Focus 2
    mk(".tmp-x","x"); mk("_x","x"); mk("Maiuscola","x"); assert reg.names() == []
def test_missing_or_empty_dir_degrades():   # Review Focus 5
    assert SkillRegistry(Settings(skills_dir=tmp/"nope")).names() == []   # niente eccezioni
    assert SkillRegistry(Settings(enable_skills=False)).skills is None
def test_refresh_detects_add_remove(): assert reg.refresh() is False; mk("pptx","P"); assert reg.refresh() and "pptx" in reg.names(); shutil.rmtree(d/"pptx"); assert reg.refresh() and reg.names() == []
def test_tools_no_script(): assert {t.name for t in reg.skills.get_tools()} == {"get_skill_instructions","get_skill_reference","list_skills"}
def test_list_skills_rank_and_cap():
    # 60 skill, skills_list_max=50 -> 50 righe; query "word" mette docx per primo; ogni descrizione <= 120 caratteri
def test_reload_failure_keeps_previous(monkeypatch): mk('a','x'); reg.refresh(); monkeypatch.setattr(reg.skills,'reload',boom); mk('b','y'); reg.refresh(); assert reg.names() == ['a']
def test_snippet_fixed_length(): assert reg_with(1).skills.get_system_prompt_snippet() == reg_with(30).skills.get_system_prompt_snippet() and reg_with(0).skills.get_system_prompt_snippet() == ""
```
- [ ] **Step 2:** FAIL. **Step 3: implementa** `CatalogSkills` (override `get_tools` escludendo `get_skill_script` e aggiungendo `list_skills` come `agno.tools.Function`; override `get_system_prompt_snippet`: stringa fissa "Hai skill installate: chiama list_skills() e valuta se una facilita il compito." se ci sono skill, altrimenti ""). `list_skills`: punteggio = parole della query presenti in nome+descrizione, ordine per punteggio poi nome; query vuota = tutte; riga `- nome: descrizione[:120]`. `SkillRegistry.refresh`: fingerprint = tupla `(nome, mtime)` delle sottocartelle valide (`NAME_RE`, no prefisso `.`/`_`, `SKILL.md` leggibile UTF-8 con `name` e `description`); se cambia -> `skills.reload()` (con loader `LocalSkills(..., validate=False)`; se `LocalSkills` sulla cartella padre non ignora le cartelle non valide, usa un loader per cartella valida e riassegna `skills.loaders` prima di `reload()`); errori -> warning e si mantiene l'elenco precedente.
- [ ] **Step 4:** PASS. **Step 5:** commit `feat: SkillRegistry e CatalogSkills`.

### Task 8: Cablaggio agenti, prompt, hint del router
**Files:** Modify `agents.py`, `team.py`, `prompts.py`, `service.py` (solo la chiamata a `build_router`); Test `tests/test_skills.py`
**Interfaces — Consumes:** Task 2, 3, 7. **Produces:** `build_complex_team(s, registry: SkillRegistry | None = None, mcp_tools: list | None = None) -> Team`; `build_router(s, registry=None, mcp_tools=None) -> Team`; `prompts.router_instructions(names: list[str], max_hint: int) -> list[str]`.

- [ ] **Step 1: test che falliscono**
```python
def test_skills_only_in_complexteam():
    team = build_router(s, reg, mcp_tools=[probe]); ct = next(m for m in team.members if m.name == "ComplexTeam")
    assert team.skills is None and next(m for m in team.members if m.name == "Coder").skills is None
    assert ct.skills is reg.skills and all(m.skills is reg.skills for m in ct.members)
    assert all(probe in m.tools for m in ct.members)
    names = lambda m: {getattr(t, "__name__", getattr(t, "name", "")) for t in m.tools}
    assert {"run_python","run_node","deliver_file"} <= names(analyst) and not ({"run_node","deliver_file"} & names(researcher))
def test_disabled_skills():
    s = Settings(enable_skills=False); team = build_router(s, SkillRegistry(s))
    ct = next(m for m in team.members if m.name == "ComplexTeam")
    assert ct.skills is None and all(m.skills is None for m in ct.members)
def test_router_instructions():
    assert "Skill nel ComplexTeam: docx, pptx" in " ".join(router_instructions(["docx","pptx"], 15))
    assert "Skill nel ComplexTeam" not in " ".join(router_instructions([f"s{i}" for i in range(16)], 15))
    assert "Skill nel ComplexTeam" not in " ".join(router_instructions([], 15))
    assert all("ComplexTeam" in " ".join(router_instructions(n, 15)) and "Word" in " ".join(router_instructions(n, 15)) for n in ([], ["a"]))
def test_leader_prompt_mentions_list_skills(): assert "list_skills" in prompts.COMPLEX_LEADER
```
(`probe` = una funzione qualsiasi usata come tool MCP finto.)
- [ ] **Step 2:** FAIL. **Step 3:** in `build_complex_team` ogni membro (e il `Team`) riceve `skills=registry.skills` se `registry is not None and registry.skills is not None` (mai un test di verità sull'oggetto: con elenco vuoto deve comunque essere collegato, così le skill aggiunte dopo l'avvio sono viste), e `*mcp_tools`; l'Analyst ha in più `make_code_tools`, `make_node_tools`, `make_file_tools`; `Coder` invariato. `prompts`: `COMPLEX_LEADER` aggiunge "prima di delegare chiama `list_skills(compito)` e, se ne esiste una pertinente, scrivi nel task 'usa la skill X'"; Analyst/Writer/Researcher/Critic: riga "se una skill è citata nel task o ti serve, usa `get_skill_instructions`; solo l'Analyst esegue codice; LibreOffice non c'è: salta validazione, ricalcolo, anteprime, conversioni PDF; per xlsx avvisa che le formule si calcolano all'apertura; salva in `outputs/` e consegna con `deliver_file`". `router_instructions` = `[ROUTER] + hint` (hint solo se `1 <= len(names) <= max_hint`), con la regola "documenti Word, PowerPoint, Excel, PDF o compiti per cui esiste una skill -> ComplexTeam" dentro `ROUTER`.
- [ ] **Step 4:** PASS (suite completa; `service.start` passa `registry` creato prima del team). **Step 5:** commit `feat: skill e MCP nel ComplexTeam`.

### Task 9: Reload a caldo nel servizio e `/skills`
**Files:** Modify `service.py`, `channels/telegram.py`, `channels/common.py`; Test `tests/test_skills.py`, `tests/test_channels.py`
**Interfaces — Consumes:** Task 7, 8. **Produces:** `PicoBotService.registry: SkillRegistry`; `PicoBotService.skill_info() -> list[SkillInfo]`; `TelegramGateway.on_skills`.

- [ ] **Step 1: test che falliscono**
```python
def test_router_hint_hot_reload(tmp_path):       # servizio con Settings(skills_dir=tmp)
    mk("docx","Word"); svc = start(); ask("ciao"); assert "docx" in system_prompt(LOG[0])
    mk("pptx","P"); ask("ciao 2"); assert "pptx" in system_prompt(LOG[-1])
    shutil.rmtree(tmp/"docx"); ask("ciao 3"); assert "docx" not in system_prompt(LOG[-1]) and "pptx" in system_prompt(LOG[-1])
def test_complexteam_tool_sees_new_skill(): mk("xlsx","E"); svc.registry.refresh(); assert "xlsx" in list_skills_tool(svc.registry)("")
def test_telegram_skills_command():   # utente autorizzato: elenco "nome: descrizione"; vuoto: "Nessuna skill installata."; non autorizzato: nessuna risposta; HELP contiene "/skills"
```
- [ ] **Step 2:** FAIL. **Step 3:** `ask` inizia con `if self.registry.refresh(): self.team.instructions = router_instructions(self.registry.names(), self.s.skills_router_hint_max)`; `start` applica lo stesso hint una volta. `/skills` risponde con `skill_info()` (descrizione troncata a 120). Aggiorna `HELP`.
- [ ] **Step 4:** PASS. **Step 5:** commit `feat: reload a caldo skill e /skills`.

### Task 10: CLI admin `picobot skills` (list/add/remove/validate)
**Files:** Create `skills_cli.py`; Modify `__main__.py`; Test `tests/test_skills_cli.py`
**Interfaces — Consumes:** `NAME_RE`, `SkillInfo`. **Produces:** `SkillInstallError(ValueError)`; `MAX_SKILL_BYTES = 50*1024*1024`; `list_installed(dir: Path) -> list[SkillInfo]`; `install(source: str, dir: Path, force: bool = False) -> SkillInfo`; `remove(name: str, dir: Path) -> None`; `validate_dir(dir: Path) -> list[tuple[str, str]]`; `main_skills(argv: list[str], s: Settings) -> int`.

- [ ] **Step 1: test che falliscono**
```python
def test_install_dir_renames_to_frontmatter_name(): info = install(str(src), d); assert info.name == "docx" and (d/"docx"/"SKILL.md").exists() and info.has_scripts
def test_duplicate_needs_force(): install(src, d); with pytest.raises(SkillInstallError): install(src, d); install(src, d, force=True)
@pytest.mark.parametrize("bad", ["no_skill_md", "no_description", "name_traversal", "name_upper", "symlink_inside"])
def test_invalid_rejected_no_residue(bad, tmp_path):    # Review Focus 1/2; ogni fixture è una cartella in tmp_path:
    src = FIXTURES[bad](tmp_path)   # senza SKILL.md | senza description | name: ../x | name: Docx | symlink verso /etc/passwd
    with pytest.raises(SkillInstallError): install(str(src), d)
    assert list(d.iterdir()) == []      # nessuna .tmp-* residua
def test_size_limit(monkeypatch): monkeypatch.setattr(skills_cli, "MAX_SKILL_BYTES", 10); with pytest.raises(SkillInstallError): install(big, d)
def test_zip_layouts(): zip_root_folder -> ok; zip_files_at_root -> ok (nome dal frontmatter)
@pytest.mark.parametrize("member", ["../evil.txt", "/abs/evil.txt"])
def test_zip_hostile_rejected(member, tmp_path):   # zip valido + un membro ostile
    with pytest.raises(SkillInstallError): install(str(make_zip(tmp_path, extra=member)), d)
    assert list(d.iterdir()) == [] and not (tmp_path/"evil.txt").exists()
def test_git_source(tmp_path): # repo locale creato con `git init`; skip se git assente; source = "file://<repo>" -> installa
def test_remove(): remove("docx", d); assert not (d/"docx").exists(); with pytest.raises(SkillInstallError): remove("docx", d)
def test_cli_dispatch(capsys): assert main_skills(["list"], s) == 0; assert main_skills(["add","/nonexistent"], s) == 1
def test_main_skills_needs_no_api_key(tmp_path): subprocess.run([sys.executable,"-m","picobot","skills","list"], env={"SKILLS_DIR": str(d), "PATH": os.environ["PATH"]}, check=True)
```
- [ ] **Step 2:** FAIL. **Step 3:** `install`: risolvi la sorgente (cartella; `.zip` estratto in temp con controllo membri; `file://`/`http(s)://`/`git@`/`.git` -> `git clone --depth 1` in temp), trova la cartella con `SKILL.md` (radice o unica sottocartella), valida (frontmatter `name` `NAME_RE`, `description` non vuota, niente symlink, dimensione <= `MAX_SKILL_BYTES`), copia in `.tmp-<uuid>` dentro `dir` e `os.replace` verso `dir/<name>` (con `force` sostituisce); in caso di errore rimuove ogni temporaneo. Riepilogo stampato dal dispatch: nome, descrizione, n. file, avviso se `scripts/` ("eseguibili solo dall'Analyst, con la tua conferma"). `__main__`: sottocomando `skills` gestito **prima** del controllo `OPENROUTER_API_KEY`.
- [ ] **Step 4:** PASS. **Step 5:** commit `feat: picobot skills list/add/remove/validate`.

### Task 11: `picobot skills deps`
**Files:** Modify `skills_cli.py`; Test `tests/test_skills_cli.py`
**Interfaces — Produces:** `declared_deps(dir: Path) -> dict[str, dict[str, list[str]]]` (`{skill: {"pip": [...], "npm": [...], "apt": [...]}}` da `requirements.txt`, `package.json` -> `dependencies` come `nome@versione` senza `^~`, `apt.txt`); `missing_deps(declared, deps_dir: Path) -> dict[str, list[str]]` (per tipo, confronto per **nome** del pacchetto); `write_missing(declared, deps_dir: Path) -> int`.

- [ ] **Step 1: test che falliscono**
```python
def test_declared(): # requirements.txt con commenti/righe vuote; package.json {"dependencies":{"docx":"^9.0.0"}}; apt.txt
    assert declared["s1"]["npm"] == ["docx@9.0.0"] and declared["s1"]["pip"] == ["openpyxl==3.1.5"]
def test_missing_compares_by_name(): # deps/npm.txt contiene "docx@9.5.0" -> docx non è mancante; pptxgenjs sì
def test_write_missing_idempotent(): assert write_missing(decl, deps) == 2 and write_missing(decl, deps) == 0 and "# skill: s1" in (deps/"npm.txt").read_text()
def test_cli_deps_exit_codes(): # senza --write e con mancanti -> 1; con --write -> 0; nessuna dipendenza dichiarata -> 0
```
- [ ] **Step 2b:** aggiungi il test `test_add_summary_lists_declared_deps(capsys)`: `main_skills(["add", src_con_requirements], s)` stampa `"pip: openpyxl==3.1.5"`.
- [ ] **Step 2:** FAIL. **Step 3:** estendi il riepilogo di `add` con le dipendenze dichiarate (`declared_deps` della skill appena installata); implementa e collega `skills deps [--write]` (`--deps-dir` default `./deps`). Non installa mai nulla. **Step 4:** PASS. **Step 5:** commit `feat: picobot skills deps`.

---
## Parte C — MCP, Docker, consegna

### Task 12: MCP condiviso con flag `enabled`
**Files:** Modify `mcp_loader.py`; Create `tests/mcp_probe_server.py`; Modify `tests/fake_llm.py`; Test `tests/test_mcp.py`
**Interfaces — Consumes:** Task 8. **Produces:** `load_mcp_tools(path: Path) -> list[MCPTools]` rispetta `"enabled": false` per server.

- [ ] **Step 1: test che falliscono** (`pytest.importorskip("fastmcp")`; `mcp_probe_server.py` = FastMCP con tool `add(a: int, b: int) -> int`; fake LLM: `elif "add" in names and "somma" in user: tool_call add(a=2, b=3)`):
```python
def test_loader_enabled_and_broken_skipped():
    cfg = {"mcpServers": {"probe": {"command": sys.executable, "args": [probe_path]},
                          "rotto": {"command": "comando-inesistente"},
                          "off": {"command": sys.executable, "args": [probe_path], "enabled": False}}}
    tools = run(load_mcp_tools(write(cfg))); assert len(tools) == 1 and list(tools[0].functions) == ["add"]
def test_all_complexteam_members_call_shared_mcp():
    ct = build_complex_team(s, reg, mcp_tools=tools)
    for name in ("Researcher", "Analyst", "Writer", "Critic"):
        member = next(m for m in ct.members if m.name == name); LOG.clear(); run(member.arun("somma 2 e 3"))
        assert "5" in [m["content"] for b in LOG for m in b["messages"] if m["role"] == "tool"]
```
- [ ] **Step 2:** FAIL. **Step 3:** salta i server con `enabled` falso (log info). **Step 4:** PASS. **Step 5:** commit `feat: MCP enabled flag e test condivisione`.

### Task 13: `deps/`, Dockerfile, compose, hardening
**Files:** Create `deps/apt.txt`, `deps/pip.txt`, `deps/npm.txt`, `deps/setup.sh`; Modify `Dockerfile`, `docker-compose.yaml`, `.env.example`, `.gitignore`, `pyproject.toml`; Test `tests/test_docker_static.py`

- [ ] **Step 1: test che falliscono** (lettura file, nessun Docker):
```python
def test_deps_seed():
    assert all(re.fullmatch(r"(docx|pptxgenjs)@\d+\.\d+\.\d+", l) for l in lines("deps/npm.txt")) and len(lines("deps/npm.txt")) == 2
    assert lines("deps/pip.txt") == [l for l in lines("deps/pip.txt") if re.fullmatch(r"openpyxl==\d+\.\d+\.\d+", l)] != []
    assert read("deps/setup.sh").startswith("#!")
def test_dockerfile_order_and_hardening():
    d = read("Dockerfile")
    assert d.index("COPY deps/") < d.index("apt-get install") < d.index("uv pip install") < d.index("npm install -g") < d.index("setup.sh") < d.index("COPY src/")
    assert "/uvx" in d and "chown -R picobot /app" not in d and "NODE_PATH" in d and "libreoffice" not in d.lower()
def test_compose_and_env_and_gitignore():
    assert "./skills:/app/skills:ro" in read("docker-compose.yaml") and "./config:/app/config:ro" in read("docker-compose.yaml")
    assert "skills/" in read(".gitignore") and all(k in read(".env.example") for k in ("ENABLE_SKILLS","SKILLS_DIR","CODE_NODE_MEM_MB","CODE_MAX_RUNS","MAX_OUTPUT_MB","MAX_OUTPUT_FILES","OUTPUT_EXTENSIONS","OUTBOX_TTL_H"))
```
- [ ] **Step 2:** FAIL. **Step 3:** scegli le versioni: `npm view docx time --json` e `npm view pptxgenjs time --json` (ultima versione con data >= 14 giorni fa), `curl -s https://pypi.org/pypi/openpyxl/json` (idem). `Dockerfile`: `COPY deps/ /tmp/deps/` -> `xargs -a /tmp/deps/apt.txt apt-get install` (salta righe vuote/commenti) -> `uv pip install -r /tmp/deps/pip.txt` nel venv -> `npm install -g $(grep -v '^#' npm.txt)` con `ENV NODE_PATH=/usr/lib/node_modules` -> `bash /tmp/deps/setup.sh` -> `COPY src/`; `COPY --from=ghcr.io/astral-sh/uv:0.5 /uv /uvx /usr/local/bin/`; `chown` solo di `data` e `workspace`; `src/`, `.venv`, `skills` restano di root. `docker-compose.yaml`: volumi `./skills:/app/skills:ro`, `./config:/app/config:ro`, `./workspace`, `./data`. `.env.example`: le variabili elencate con i default del Global Constraints. `.gitignore`: aggiungi `skills/`.
- [ ] **Step 4:** PASS. **Step 5:** commit `feat: punti di estensione deps e hardening Docker`.

### Task 14: Documentazione, collaudo, versione, pacchetto
**Files:** Modify `README.md`, `pyproject.toml`, `src/picobot/__init__.py`; Create `docs/manual-qa.md`; Test: suite completa

- [ ] **Step 1:** README: sezioni "Skill" (installare/cancellare = copiare/eliminare in `skills/`, `picobot skills ...`, reload a caldo, solo dall'host), "Dipendenze" (`deps/*`, `skills deps`, rebuild), "MCP" (`enabled`, nessuna conferma sui tool, riavvio), "Costi". Versione `0.4.0` in `pyproject.toml` e `__init__.py`.
- [ ] **Step 2:** `docs/manual-qa.md`: checklist con (1) docx da Telegram con conferma dei bottoni e file aperto in Word; (2) pptx; (3) xlsx; (4) aggiunta e rimozione di una skill a caldo vista dal ComplexTeam; (5) un server MCP reale (es. filesystem via `npx`); (6) codice > 1500 caratteri allegato prima dei bottoni; (7) `picobot skills add` con zip.
- [ ] **Step 3:** `python -m pytest -q tests -p no:cacheprovider` -> tutti verdi (>= 30 esistenti + nuovi; i test Node/MCP possono risultare "skipped" se mancano `node`/`fastmcp`, mai "failed").
- [ ] **Step 4:** installazione pulita: copia in cartella temporanea, `uv sync --no-dev`, `.venv/bin/python -c "import picobot.skills, picobot.tools.files"` e `.venv/bin/python -m picobot skills list` -> exit 0.
- [ ] **Step 5:** zip `picobot_v0.4.zip` senza `data/`, `workspace/`, `skills/`, `certs/`, `.venv/`; `git add -A && git commit -m "release: v0.4.0" && git tag v0.4.0`.
