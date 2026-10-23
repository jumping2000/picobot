# PicoBot v0.6 — Messaggi vocali (speech-to-text) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Trascrivere note vocali e file audio Telegram con un container `stt` (faster-whisper su CPU) e passare il testo al router come un messaggio scritto, con eco "🎤 …".

**Architecture:** Nuovo servizio `stt/` (FastAPI + faster-whisper int8) con endpoint compatibile OpenAI `POST /v1/audio/transcriptions`, in un profilo compose senza porte pubblicate. In PicoBot un client httpx (`src/picobot/stt.py`) e un nuovo flusso in `channels/telegram.py`; con `STT_URL` vuoto tutto resta come in v0.5.

**Tech Stack:** Python 3.11, faster-whisper 1.2.1 (CTranslate2, PyAV), FastAPI, uvicorn, httpx, python-telegram-bot 21.10, pytest, Docker compose profiles, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-10-23-picobot-voice-stt-design.md`

## Global Constraints

- Branch di lavoro: `feat/voice-stt`. Commenti e messaggi per l'utente in italiano, come nel resto del codice.
- Versione: `0.6.0` in `pyproject.toml`, `src/picobot/__init__.py` e `stt/pyproject.toml` (la CI confronta le prime due).
- Nessuna nuova dipendenza nell'immagine di PicoBot: il client usa `httpx` (già installato da python-telegram-bot).
- `stt` ha dipendenze proprie in `stt/pyproject.toml`: `faster-whisper==1.2.1`, `fastapi`, `uvicorn`, `python-multipart`; dev: `pytest`, `httpx`.
- Default PicoBot: `STT_URL=""` (spento), `STT_TIMEOUT_S=180`, `MAX_VOICE_S=300`; resta valido `MAX_UPLOAD_MB=15`.
- Default `stt`: `STT_MODEL=small`, `STT_COMPUTE_TYPE=int8`, `STT_THREADS=4`, `STT_BEAM_SIZE=1`, `STT_LANGUAGES=it,en`, `STT_MAX_MB=20`, `STT_MAX_SECONDS=300`, `HF_HOME=/models`.
- Testi esatti per l'utente (Telegram):
  - eco: `f"🎤 {testo}"` in testo semplice (nessun `parse_mode`);
  - spento: `"I messaggi vocali non sono abilitati."`;
  - troppo lungo: `f"Vocale troppo lungo (max {s.max_voice_s // 60} minuti)."`;
  - troppo grande: `f"File troppo grande (max {s.max_upload_mb} MB)."`;
  - vuoto: `"Non ho capito il vocale, puoi ripeterlo o scriverlo?"`;
  - non disponibile: `"Trascrizione non disponibile al momento: riprova o scrivi il messaggio."`;
  - illeggibile: `"Non riesco a leggere questo audio."`;
  - download fallito: `"Impossibile scaricare il vocale, riprova."`.
- Testo al router: la trascrizione così com'è; con didascalia `f"{didascalia}\n\n[Trascrizione audio]: {testo}"`.
- Test automatici senza rete e senza modelli reali; i 163 test esistenti restano verdi.

## Review Focus

1. Audio inviato come documento senza durata nei metadati e più lungo di `STT_MAX_SECONDS`: il servizio risponde 413 e l'utente legge "Vocale troppo lungo…", non un errore generico → test in Task 5.
2. Trascrizione con caratteri Markdown (`_`, `*`, `[`): l'eco non deve fallire con `BadRequest` → test in Task 5 (eco senza `parse_mode`).
3. Trascrizione oltre 4.000 caratteri: l'eco va divisa in più messaggi → test in Task 5.
4. `stt` giù durante un vocale: il lock della chat viene rilasciato e il messaggio di testo successivo ottiene risposta → test in Task 5.
5. Audio inoltrato senza `file_name` (mime `audio/ogg`): va trascritto comunque, con estensione ricavata dal mime → test in Task 5.

---

## File Structure

| File | Responsabilità |
|---|---|
| `stt/pyproject.toml` | progetto uv non-package del servizio, dipendenze, `pytest` con `pythonpath=["."]` |
| `stt/settings.py` | `SttSettings` (dataclass) letto dall'ambiente |
| `stt/transcriber.py` | `AudioClip`, `AudioError`, protocollo `Transcriber`, `choose_language`, `FasterWhisperTranscriber` |
| `stt/app.py` | `create_app(settings, transcriber)`: endpoint, lifespan, lock, limiti |
| `stt/main.py` | oggetto `app` per uvicorn |
| `stt/bench.py` | misura dei modelli sul N100 (manuale) |
| `stt/Dockerfile`, `stt/.dockerignore` | immagine del servizio |
| `stt/tests/` | test del servizio con trascrittore finto |
| `src/picobot/stt.py` | client: `Transcript`, `SttError`, `transcribe()` |
| `src/picobot/config.py` | `stt_url`, `stt_timeout_s`, `max_voice_s` |
| `src/picobot/channels/telegram.py` | handler voce/audio e documenti `audio/*` |
| `docker-compose.yaml`, `.env.example`, `.gitignore`, `.dockerignore` | deploy opt-in |
| `.github/workflows/release_ci-cd.yml` | test, build-check e push di `picobot-stt` |
| `docs/en/voice.md`, `docs/it/voice.md` + rimandi, `docs/manual-qa.md`, README | documentazione |

---

### Task 1: Logica del servizio `stt` (impostazioni, scelta della lingua, trascrittore)

**Files:**
- Create: `stt/pyproject.toml`, `stt/settings.py`, `stt/transcriber.py`, `stt/tests/test_transcriber.py`

**Interfaces:**
- Produces:
  - `SttSettings` (dataclass frozen): `model: str`, `compute_type: str`, `threads: int`, `beam_size: int`, `languages: list[str]`, `max_mb: int`, `max_seconds: int`; `@classmethod from_env(cls, env: Mapping[str, str] = os.environ) -> SttSettings` con i default dei Global Constraints (`STT_LANGUAGES` separato da virgole, minuscolo, senza spazi).
  - `AudioClip` (dataclass): `samples: Any`, `duration: float`.
  - `class AudioError(ValueError)`.
  - `class Transcriber(Protocol)`: `load() -> None`; `decode(path: str) -> AudioClip` (solleva `AudioError`); `language_probs(clip: AudioClip) -> list[tuple[str, float]]`; `transcribe(clip: AudioClip, language: str) -> str`.
  - `choose_language(probs: list[tuple[str, float]], allowed: list[str]) -> str`.
  - `FasterWhisperTranscriber(settings: SttSettings)` che implementa `Transcriber`.

- [ ] **Step 1: Crea `stt/pyproject.toml`**

`[project] name="picobot-stt"`, `version="0.6.0"`, `requires-python=">=3.11"`, dipendenze dei Global Constraints; `[dependency-groups] dev=["pytest","httpx"]`; `[tool.uv] package=false`; `[tool.pytest.ini_options] pythonpath=["."]`. Nessun `build-system`.

- [ ] **Step 2: Scrivi i test che falliscono** in `stt/tests/test_transcriber.py`

```python
from settings import SttSettings
from transcriber import choose_language

def test_choose_language_picks_best_allowed():
    assert choose_language([("es", 0.6), ("it", 0.3), ("en", 0.1)], ["it", "en"]) == "it"
    assert choose_language([("en", 0.7), ("it", 0.2)], ["it", "en"]) == "en"

def test_choose_language_falls_back_to_first_allowed():
    assert choose_language([("es", 0.9)], ["it", "en"]) == "it"
    assert choose_language([], ["it", "en"]) == "it"

def test_settings_from_env_defaults_and_override():
    d = SttSettings.from_env({})
    assert (d.model, d.compute_type, d.threads, d.beam_size) == ("small", "int8", 4, 1)
    assert d.languages == ["it", "en"] and (d.max_mb, d.max_seconds) == (20, 300)
    o = SttSettings.from_env({"STT_MODEL": "base", "STT_LANGUAGES": " IT , en ", "STT_BEAM_SIZE": "5"})
    assert (o.model, o.languages, o.beam_size) == ("base", ["it", "en"], 5)
```

- [ ] **Step 3: Verifica che falliscano**

Run: `uv run --directory stt --group dev pytest tests/test_transcriber.py -v`
Expected: FAIL (`ModuleNotFoundError: settings`)

- [ ] **Step 4: Implementa `stt/settings.py` e `stt/transcriber.py`**

`FasterWhisperTranscriber`: importa `faster_whisper` **dentro** `load()` e `decode()` (i test e l'import di `main` non caricano il modello).
- `load`: `WhisperModel(s.model, device="cpu", compute_type=s.compute_type, cpu_threads=s.threads)`.
- `decode`: `decode_audio(path)` (16 kHz) → `AudioClip(samples, len(samples) / 16000)`; qualsiasi eccezione → `AudioError`.
- `language_probs`: terzo elemento di `model.detect_language(clip.samples, vad_filter=True)`.
- `transcribe`: `model.transcribe(clip.samples, language=language, beam_size=s.beam_size, vad_filter=True)`, segmenti uniti con `"".join(seg.text for seg in segments).strip()`.

- [ ] **Step 5: Verifica che passino**

Run: `uv run --directory stt --group dev pytest tests/test_transcriber.py -v`
Expected: 3 passed

- [ ] **Step 6: Commit**

```bash
git add stt/pyproject.toml stt/settings.py stt/transcriber.py stt/tests/test_transcriber.py
git commit -m "feat(stt): impostazioni, scelta della lingua e trascrittore faster-whisper"
```

---

### Task 2: API del servizio `stt`

**Files:**
- Create: `stt/app.py`, `stt/main.py`, `stt/tests/test_app.py`

**Interfaces:**
- Consumes: Task 1 (`SttSettings`, `Transcriber`, `AudioClip`, `AudioError`, `choose_language`, `FasterWhisperTranscriber`).
- Produces: `create_app(settings: SttSettings, transcriber: Transcriber) -> FastAPI`; `main.app` per `uvicorn main:app`.
  - `GET /health` → 200 `{"status": "ok", "model": settings.model}` se pronto, altrimenti 503.
  - `POST /v1/audio/transcriptions` multipart `file` (obbligatorio), `language` (opzionale), `model` (ignorato) → 200 `{"text": str, "language": str, "duration": float}`.
  - Errori: 503 modello non pronto; 400 file mancante o `AudioError`; 413 oltre `max_mb` o `max_seconds`.

- [ ] **Step 1: Scrivi i test che falliscono** in `stt/tests/test_app.py`

`FakeTranscriber` (nel file di test): `decode` restituisce `AudioClip(None, durata)` (durata configurabile; solleva `AudioError` se il contenuto è `b"bad"`); `language_probs` restituisce probabilità configurabili; `transcribe` restituisce un testo configurabile, registra la lingua usata e misura la concorrenza massima con un contatore protetto da `threading.Lock` e un `time.sleep(0.05)`.

```python
def test_transcription_ok(client):            # TestClient avviato (lifespan: load chiamato)
    r = client.post("/v1/audio/transcriptions", files={"file": ("v.ogg", b"audio")})
    assert r.status_code == 200 and r.json() == {"text": "ciao", "language": "it", "duration": 3.0}

def test_language_chosen_among_allowed(client, fake):   # probs es=0.6, it=0.4
    client.post("/v1/audio/transcriptions", files={"file": ("v.ogg", b"audio")})
    assert fake.languages_used == ["it"]

def test_explicit_language_is_respected(client, fake):
    client.post("/v1/audio/transcriptions", files={"file": ("v.ogg", b"audio")}, data={"language": "en"})
    assert fake.languages_used == ["en"]

def test_silence_returns_empty_text(client, fake):      # fake.text = ""
    assert client.post(...).json()["text"] == ""

def test_not_ready_before_load():               # create_app senza avviare il lifespan (httpx.ASGITransport)
    assert health.status_code == 503 and transcription.status_code == 503

def test_requests_are_serialized(client, fake): # 3 richieste in thread paralleli
    assert fake.max_concurrency == 1

def test_errors(client):
    assert client.post("/v1/audio/transcriptions").status_code == 400                       # senza file
    assert client.post(..., files={"file": ("x.ogg", b"bad")}).status_code == 400            # AudioError
    # max_mb=1 nelle impostazioni del test
    assert client.post(..., files={"file": ("x.ogg", b"a" * (1024 * 1024 + 1))}).status_code == 413
    # durata 301 s con max_seconds=300
    assert long_clip.status_code == 413
```

- [ ] **Step 2: Verifica che falliscano**

Run: `uv run --directory stt --group dev pytest tests/test_app.py -v`
Expected: FAIL (`ModuleNotFoundError: app`)

- [ ] **Step 3: Implementa `create_app` in `stt/app.py`**

- Lifespan: `await asyncio.to_thread(transcriber.load)`, poi `ready = True`.
- Upload: lettura a blocchi da 1 MB in un file temporaneo (`tempfile.NamedTemporaryFile`), con 413 appena si supera `max_mb`; il file viene cancellato in `finally`.
- Un `asyncio.Lock` serializza decode, lingua e trascrizione, eseguiti con `asyncio.to_thread`.
- Se la richiesta specifica `language`, si usa quella così com'è, senza `choose_language` né il calcolo delle probabilità.
- `duration` arrotondata a 2 decimali.

`stt/main.py`: `settings = SttSettings.from_env(); app = create_app(settings, FasterWhisperTranscriber(settings))`.

- [ ] **Step 4: Verifica che passino**

Run: `uv run --directory stt --group dev pytest tests -v`
Expected: tutti i test di `stt/tests` passano

- [ ] **Step 5: Commit**

```bash
git add stt/app.py stt/main.py stt/tests/test_app.py
git commit -m "feat(stt): endpoint compatibile OpenAI con limiti e una trascrizione alla volta"
```

---

### Task 3: Immagine, benchmark e compose

**Files:**
- Create: `stt/Dockerfile`, `stt/.dockerignore`, `stt/bench.py`
- Modify: `docker-compose.yaml`, `.gitignore`, `.dockerignore`, `tests/test_docker_static.py`

**Interfaces:**
- Consumes: Task 1-2 (`main:app`, `FasterWhisperTranscriber`, `SttSettings`).
- Produces: servizio compose `stt` (profilo `stt`, raggiungibile come `http://stt:8000`); immagine con `CMD uvicorn main:app --host 0.0.0.0 --port 8000`.

- [ ] **Step 1: Scrivi i test statici che falliscono** in `tests/test_docker_static.py`

```python
def test_stt_compose_service():
    import yaml
    svc = yaml.safe_load(read("docker-compose.yaml"))["services"]["stt"]
    assert svc["profiles"] == ["stt"] and "ports" not in svc
    assert "./models:/models" in svc["volumes"] and svc["build"] == "./stt"
    assert "env_file" not in svc                      # le chiavi di PicoBot non arrivano a stt
    assert "depends_on" not in yaml.safe_load(read("docker-compose.yaml"))["services"]["picobot"]

def test_stt_dockerfile_non_root():
    d = read("stt/Dockerfile")
    assert "USER stt" in d and "HF_HOME=/models" in d and "main:app" in d
    assert "models/" in read(".gitignore") and "models" in read(".dockerignore").split()
```

- [ ] **Step 2: Verifica che falliscano**

Run: `uv run --group dev pytest tests/test_docker_static.py -v`
Expected: FAIL (`KeyError: 'stt'`)

- [ ] **Step 3: Implementa**

`stt/Dockerfile`:
- `python:3.11-slim`, con `uv` copiato da `ghcr.io/astral-sh/uv:0.5` come nel Dockerfile principale;
- `COPY pyproject.toml`, poi `uv sync --no-dev`; `COPY *.py ./`;
- `useradd -m -u 1000 stt`, `mkdir /models`, `chown stt /models`, `USER stt`;
- `ENV PATH=/app/.venv/bin:$PATH HF_HOME=/models`;
- `HEALTHCHECK` con `python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=3)"`;
- `EXPOSE 8000`, `CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]`.

`stt/.dockerignore`: `tests`, `__pycache__`, `.venv`.

Servizio `stt` in `docker-compose.yaml`:
- `build: ./stt`, `profiles: ["stt"]`, `container_name: picobot-stt`, `restart: unless-stopped`, `mem_limit: 2g`;
- `volumes: ["./models:/models"]`;
- `environment` con interpolazione e default, per ogni variabile `STT_*` dei Global Constraints (es. `STT_MODEL: ${STT_MODEL:-small}`);
- commento di avvio: `mkdir -p models && sudo chown -R 1000 models`, poi `docker compose --profile stt up -d --build`.

Aggiungi `models/` a `.gitignore` e `models` a `.dockerignore`.

`stt/bench.py`:
- CLI `python bench.py FILE [FILE...] [--models base small] [--beams 1 5]`;
- per ogni combinazione: un `FasterWhisperTranscriber` con le impostazioni modificate, misura con `time.perf_counter` di decode, lingua e trascrizione;
- stampa una riga per file con modello, beam, durata audio, secondi impiegati, RTF (impiegati/durata), lingua e i primi 80 caratteri del testo.

- [ ] **Step 4: Verifica**

Run: `uv run --group dev pytest tests/test_docker_static.py -v && python3 -m py_compile stt/bench.py`
Expected: tutti passano, nessun errore di compilazione

- [ ] **Step 5: Commit**

```bash
git add stt/Dockerfile stt/.dockerignore stt/bench.py docker-compose.yaml .gitignore .dockerignore tests/test_docker_static.py
git commit -m "feat(stt): immagine non root, benchmark e servizio compose nel profilo stt"
```

---

### Task 4: Client STT e configurazione di PicoBot

**Files:**
- Create: `src/picobot/stt.py`, `tests/test_stt.py`
- Modify: `src/picobot/config.py` (sezione nuova `# --- Messaggi vocali (STT) ---`), `.env.example`, `tests/test_docker_static.py::test_compose_env_ignores` (chiavi `.env.example`)

**Interfaces:**
- Produces:
  - `Settings.stt_url: str = ""`, `Settings.stt_timeout_s: int = 180`, `Settings.max_voice_s: int = 300`.
  - `Transcript` (dataclass): `text: str`, `language: str`.
  - `class SttError(Exception)` con attributo `kind: Literal["unavailable", "unreadable", "too_long"]`.
  - `async def transcribe(s: Settings, path: Path, filename: str, transport: httpx.AsyncBaseTransport | None = None) -> Transcript` → POST multipart `file=(filename, bytes)` a `f"{s.stt_url.rstrip('/')}/v1/audio/transcriptions"`, timeout `s.stt_timeout_s`.

- [ ] **Step 1: Scrivi i test che falliscono** in `tests/test_stt.py`

```python
def _run(handler, tmp_path):   # handler: httpx.Request -> httpx.Response
    p = tmp_path / "v.ogg"; p.write_bytes(b"audio")
    s = Settings(stt_url="http://stt:8000/")
    return asyncio.run(transcribe(s, p, "v.ogg", transport=httpx.MockTransport(handler)))

def test_transcribe_ok(tmp_path):
    seen = {}
    def h(req): seen["url"] = str(req.url); return httpx.Response(200, json={"text": " ciao ", "language": "it", "duration": 1.0})
    assert _run(h, tmp_path) == Transcript("ciao", "it")
    assert seen["url"] == "http://stt:8000/v1/audio/transcriptions"

@pytest.mark.parametrize("status,kind", [(400, "unreadable"), (413, "too_long"), (500, "unavailable"), (503, "unavailable")])
def test_http_errors(tmp_path, status, kind):
    with pytest.raises(SttError) as e: _run(lambda r: httpx.Response(status), tmp_path)
    assert e.value.kind == kind

def test_network_errors(tmp_path):
    for exc in (httpx.ConnectError("x"), httpx.ReadTimeout("x")):
        def h(req, exc=exc): raise exc
        with pytest.raises(SttError) as e: _run(h, tmp_path)
        assert e.value.kind == "unavailable"

def test_settings_defaults():
    s = Settings()
    assert (s.stt_url, s.stt_timeout_s, s.max_voice_s) == ("", 180, 300)
```

- [ ] **Step 2: Verifica che falliscano**

Run: `uv run --group dev pytest tests/test_stt.py -v`
Expected: FAIL (`ModuleNotFoundError: picobot.stt`)

- [ ] **Step 3: Implementa** `src/picobot/stt.py` e i campi di `Settings`

`Transcript.text` restituito con `strip()`; JSON malformato → `SttError("unavailable")`. In `.env.example` aggiungi la sezione commentata con `STT_URL=http://stt:8000`, `STT_TIMEOUT_S=180` e `MAX_VOICE_S=300`, e la nota sul profilo compose. Aggiungi `STT_URL` e `MAX_VOICE_S` alle chiavi verificate da `test_compose_env_ignores`.

- [ ] **Step 4: Verifica che passino**

Run: `uv run --group dev pytest tests/test_stt.py tests/test_docker_static.py -v`
Expected: tutti passano

- [ ] **Step 5: Commit**

```bash
git add src/picobot/stt.py src/picobot/config.py .env.example tests/test_stt.py tests/test_docker_static.py
git commit -m "feat: client STT compatibile OpenAI e impostazioni dei messaggi vocali"
```

---

### Task 5: Vocali e audio nel canale Telegram

**Files:**
- Modify: `src/picobot/channels/telegram.py` (nuovi metodi in `TelegramGateway`, `on_document`, `build_application`), `src/picobot/channels/common.py` (riga di `HELP` sui vocali)
- Test: `tests/test_channels.py` (nuova sezione `# ---- vocali (v0.6) ----`)

**Interfaces:**
- Consumes: Task 4 (`transcribe`, `Transcript`, `SttError.kind`, `Settings.stt_url`, `max_voice_s`). `telegram.py` importa `from ..stt import SttError, transcribe` e chiama `transcribe(self.s, path, name)`: i test fanno monkeypatch di `picobot.channels.telegram.transcribe`.
- Produces:
  - `TelegramGateway.on_voice(update, ctx)` per `filters.VOICE | filters.AUDIO`: media = `message.voice or message.audio`;
  - `TelegramGateway._transcribe_and_ask(update, ctx, media, caption: str) -> None`, condiviso con `on_document` per i documenti con `(getattr(doc, "mime_type", None) or "").startswith("audio/")`.

- [ ] **Step 1: Scrivi i test che falliscono** in `tests/test_channels.py`

Helper `_voice_update(replies, kind="voice", duration=5, file_size=1000, mime="audio/ogg", file_name=None, caption=None, dl_fails=False)`, sullo stile di `_doc_update`: il media espone `duration`, `file_size`, `mime_type`, `file_name` e `get_file`, ed è assegnato a `message.voice`, `message.audio` o `message.document` secondo `kind`. `reply_text(text, **kw)` registra il testo e `kw`.

`fake_transcribe(result)` restituisce una coroutine che produce `Transcript(result, "it")`, o solleva `SttError(kind)` se `result` è `SttError`; registra le chiamate e i percorsi ricevuti.

Settings: `Settings(telegram_allowed_user_ids="1", stt_url="http://stt:8000")`.

```python
def test_voice_echo_then_router(tmp_path, monkeypatch):
    # transcribe -> "quotazione di AAPL"
    assert replies[0] == "🎤 quotazione di AAPL" and "parse_mode" not in kws[0]
    assert "quotazione di AAPL" in str(fake_llm.LOG[0]["messages"])       # testo esatto al router
    assert not list((s.data_dir / "inbox").glob("*"))

def test_voice_empty_transcript_skips_router(...):   # transcribe -> "   "
    assert replies == ["Non ho capito il vocale, puoi ripeterlo o scriverlo?"] and fake_llm.LOG == []

def test_voice_disabled_without_stt_url(...):        # Settings senza stt_url
    assert replies == ["I messaggi vocali non sono abilitati."]
    media.get_file.assert_not_called()

def test_voice_too_long_rejected_before_download(...):   # duration=301
    assert replies == ["Vocale troppo lungo (max 5 minuti)."]
    media.get_file.assert_not_called()

def test_voice_too_big_rejected_before_download(...):    # file_size = 15 MB + 1
    assert replies == ["File troppo grande (max 15 MB)."]

@pytest.mark.parametrize("kind,msg", [
    ("unavailable", "Trascrizione non disponibile al momento: riprova o scrivi il messaggio."),
    ("unreadable", "Non riesco a leggere questo audio."),
    ("too_long", "Vocale troppo lungo (max 5 minuti)."),         # Review Focus 1
])
def test_voice_stt_errors(..., kind, msg):
    assert replies[-1] == msg and fake_llm.LOG == [] and inbox vuota

def test_voice_download_failure(...):                 # dl_fails=True
    assert replies[-1] == "Impossibile scaricare il vocale, riprova." and inbox vuota

def test_audio_document_is_transcribed(...):          # kind="document", mime="audio/mpeg", file_name="nota.mp3"
    assert replies[0].startswith("🎤 ")
    # un documento .txt resta sul flusso v0.5: test esistenti verdi

def test_audio_caption_is_combined(...):              # kind="audio", caption="riassumi"
    assert "riassumi\n\n[Trascrizione audio]: testo" in str(fake_llm.LOG[0]["messages"])

def test_voice_unauthorized_is_ignored(...):          # effective_user.id=99
    assert replies == [] and transcribe non chiamato

def test_voice_echo_with_markdown_chars(...):         # Review Focus 2: testo "a_b *c* [d"
    assert replies[0] == "🎤 a_b *c* [d" and "parse_mode" not in kws[0]

def test_voice_long_echo_is_split(...):               # Review Focus 3: testo "parola " * 1300 (~9.100 caratteri)
    echo = replies[:-1]                                # l'ultima risposta e' quella del router
    assert len(echo) >= 3 and echo[0].startswith("🎤 ") and all(len(e) <= 4000 for e in echo)

def test_text_after_stt_down_still_answered(...):     # Review Focus 4
    # vocale con SttError("unavailable"), poi on_message testo nella stessa chat entro asyncio.wait_for(..., 5)
    assert replies[-1] == "RISPOSTA-FINTA"

def test_forwarded_audio_without_name(...):           # Review Focus 5: kind="document", file_name=None, mime="audio/ogg"
    assert transcribe chiamato con un percorso che termina in ".ogg" and replies[0].startswith("🎤 ")
```

- [ ] **Step 2: Verifica che falliscano**

Run: `uv run --group dev pytest tests/test_channels.py -k "voice or audio or stt_down" -v`
Expected: FAIL (`AttributeError: ... on_voice`)

- [ ] **Step 3: Implementa** in `channels/telegram.py`

Ordine in `_transcribe_and_ask`, tutto sotto `self._locks[chat_id]`:
1. Fuori dal lock: autorizzazione (in `on_voice` / `on_document`).
2. `stt_url` vuoto → messaggio "spento".
3. `duration` (se presente) oltre `max_voice_s` → "troppo lungo"; `file_size` oltre `max_upload_mb` → "troppo grande".
4. Download in `data/inbox/<uuid><ext>`; `ext` è il suffisso di `file_name`, altrimenti `mimetypes.guess_extension(mime)`, altrimenti `".ogg"` per `voice` e `".bin"` per gli altri.
5. `transcribe` dentro `_with_typing`.
6. Testo vuoto → messaggio "vuoto".
7. Eco con `split_text(f"🎤 {text}")` e `reply_text(chunk)`, senza `parse_mode`.
8. Composizione con la didascalia.
9. Chiamata al router con la stessa logica di `_ask` ma senza riacquisire il lock: estrai il corpo di `_ask` in `_ask_locked(update, ctx, text, target, **ctx_kw)` e fai chiamare quello a `_ask`.

Un unico `finally` cancella il file. `SttError` produce il messaggio della sua `kind`; un'eccezione nel download produce il messaggio di download fallito, con `logger.exception`.

In `build_application`, registra `MessageHandler(filters.VOICE | filters.AUDIO, gw.on_voice)` prima dell'handler dei documenti. In `HELP` aggiungi la riga `"Invia un messaggio vocale o un file audio: lo trascrivo e lo eseguo come un messaggio scritto."`.

- [ ] **Step 4: Verifica che passino, insieme alla regressione**

Run: `uv run --group dev pytest tests -v`
Expected: tutti passano (163 esistenti + nuovi), 1 saltato solo se mancano i pacchetti Node globali

- [ ] **Step 5: Commit**

```bash
git add src/picobot/channels/telegram.py src/picobot/channels/common.py tests/test_channels.py
git commit -m "feat(telegram): note vocali e file audio trascritti con eco e passati al router"
```

---

### Task 6: Pipeline CI/CD per `picobot-stt`

**Files:**
- Modify: `.github/workflows/release_ci-cd.yml`

**Interfaces:**
- Consumes: Task 1-3 (`stt/pyproject.toml`, `stt/tests`, `stt/Dockerfile`, `main:app` importabile senza modello).
- Produces: immagine `ghcr.io/${{ github.repository }}-stt` con gli stessi tag di `picobot`.

- [ ] **Step 1: Modifica i job**

- `test`: dopo i test di PicoBot, aggiungi uno step `Run stt tests` con `uv run --directory stt --group dev --python ${{ matrix.python-version }} pytest tests -v`.
- `docker-check`: aggiungi una seconda build (`context: ./stt`, `file: ./stt/Dockerfile`, `tags: picobot-stt:ci`, `load: true`, `cache-from/to: type=gha,scope=stt`) e uno smoke test `docker run --rm picobot-stt:ci python -c "import faster_whisper, main; print('stt ok')"`. Aggiungi `scope=picobot` alla cache della build esistente, così le due immagini non si sovrascrivono la cache.
- `build-docker`: aggiungi questi step per `stt`:
  - `Extract metadata (stt)`: id `meta_stt`, `images: ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}-stt`, stessi `tags`, `org.opencontainers.image.title=PicoBot STT`;
  - `Build and push (stt)`: multi-arch, `scope=stt`;
  - `Smoke test pushed image (stt)`: importa `main`;
  - `Scan image (stt)`: Trivy, output `trivy-stt-image-report.txt`;
  - `Generate SBOM (stt)`: output `sbom-stt.spdx.json`.

  Aggiungi i due file nuovi agli asset della release e all'artifact, e l'immagine `stt` al riepilogo.

- [ ] **Step 2: Verifica**

Run: `uvx --from actionlint-py actionlint .github/workflows/release_ci-cd.yml && python3 -c "import yaml; yaml.safe_load(open('.github/workflows/release_ci-cd.yml'))"`
Expected: nessun errore

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/release_ci-cd.yml
git commit -m "ci: test, build-check e pubblicazione dell'immagine picobot-stt"
```

---

### Task 7: Documentazione, collaudo e versione 0.6.0

**Files:**
- Create: `docs/en/voice.md`, `docs/it/voice.md`
- Modify: `pyproject.toml`, `src/picobot/__init__.py`, `README.md`, `README_IT.md`, `docs/{en,it}/index.md`, `docs/{en,it}/configuration.md`, `docs/{en,it}/channels.md`, `docs/{en,it}/getting-started.md`, `docs/{en,it}/development.md`, `docs/manual-qa.md`

**Interfaces:**
- Consumes: tutti i task precedenti (nomi delle variabili, messaggi, comandi).

- [ ] **Step 1: Versione** `0.6.0` in `pyproject.toml` e in `__version__`; badge della versione nei due README.

- [ ] **Step 2: `voice.md` (EN e IT, stessa struttura delle altre pagine)**

Sezioni:
1. Cosa fa, con il diagramma della spec.
2. Attivazione: cartella `models/`, `STT_URL`, comando con `--profile stt`.
3. Variabili `stt` e PicoBot (tabelle dei Global Constraints).
4. Messaggi all'utente.
5. Scelta del modello con `bench.py`: copia dei file audio in `./models/`, poi `docker compose --profile stt run --rm stt python bench.py /models/<file>`.
6. Privacy: audio cancellato e nessuna porta pubblicata.
7. Limiti: fuori scope della spec.

- [ ] **Step 3: Rimandi**

- **README:** riga "🎤 Voice messages / Messaggi vocali" nella tabella delle funzionalità e riga `voice` nella tabella della documentazione.
- **index:** riga `voice`.
- **configuration:** sezione "Voice messages (STT)" con le 3 variabili di PicoBot e il rimando a `voice.md`.
- **channels:** riga nella tabella dei documenti Telegram.
- **getting-started:** passo opzionale con il profilo `stt`.
- **development:** riga `stt/` nella struttura e immagine `picobot-stt` nella sezione CI/CD.

- [ ] **Step 4: Collaudo manuale:** aggiungi a `docs/manual-qa.md` le righe 16-21 della sezione 11 della spec (collaudo manuale), con colonne Prova / Atteso / Esito.

- [ ] **Step 5: Verifica**

Run (link relativi di README e docs, poi tutti i test):
```bash
python3 -c "
import re,pathlib
fs=[pathlib.Path('README.md'),pathlib.Path('README_IT.md'),*pathlib.Path('docs').glob('*/*.md')]
bad=[(f,t) for f in fs for t in re.findall(r'\]\(([^)\s]+)\)',f.read_text()) if not t.startswith(('http','#')) and not (f.parent/t.split('#')[0]).exists()]
print(len(bad),'broken',bad)"
uv run --group dev pytest tests -q && uv run --directory stt --group dev pytest tests -q
```
Expected: `0 broken`; tutti i test passano

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml src/picobot/__init__.py README.md README_IT.md docs/
git commit -m "docs: messaggi vocali (EN/IT), collaudo manuale e versione 0.6.0"
```
