# PicoBot v0.6: messaggi vocali (speech-to-text) su Telegram — Design

Data: 2026-10-23 · Stato: da rivedere (rev. 1) · Base: v0.5.0 (`main` @ 3bd7cd8)

Questo documento descrive solo le aggiunte rispetto alla v0.5. Tutto il resto (router, team, workflow, conferme del
codice, scheduler, API, CLI) resta invariato.

## 1. Obiettivo
L'utente può parlare a PicoBot su Telegram: le note vocali e i file audio vengono trascritti da un container separato
(faster-whisper su CPU) e il testo entra nel router come un messaggio scritto.

**Criterio di successo:**
1. un vocale "quotazione di AAPL" produce l'eco "🎤 quotazione di AAPL" e poi la stessa risposta della frase scritta;
2. l'audio non esce dall'host (nessun servizio cloud per la trascrizione) e non resta su disco dopo la richiesta;
3. con `STT_URL` vuoto o con il servizio `stt` non avviato, PicoBot si comporta come la v0.5 (solo un messaggio
   cortese sui vocali);
4. la latenza su un N100 per un vocale breve è misurata con `stt/bench.py` e usata per scegliere il modello di default.

## 2. Decisioni (dall'utente)
- Hardware del servizio di trascrizione: **CPU x86 Intel N100** (4 core, AVX2, nessuna GPU), stessa macchina di PicoBot.
- Lingue: **italiano e inglese**, con rilevamento automatico.
- Esperienza: **eco della trascrizione** ("🎤 …") e poi esecuzione, senza conferma aggiuntiva.
- Input: **note vocali Telegram** (OGG/Opus) e **file audio allegati** (mp3, m4a, wav, …), anche inviati come documento.
- Approccio: **container proprio e minimale** (FastAPI + faster-whisper) con endpoint compatibile OpenAI
  `POST /v1/audio/transcriptions`, così il motore resta sostituibile cambiando solo l'URL.
- Modello di default scelto con una misura reale sul N100 (`base` vs `small`, beam 1 vs 5); provvisorio: `small`.

## 3. Fuori scope
Video-messaggi tondi; trascrizione via API REST o CLI; comandi pronunciati ("slash simple"); risposte vocali
(text-to-speech); GPU; lingue diverse da italiano e inglese; traduzione; diarizzazione; conferma della trascrizione
prima dell'esecuzione; trascrizione negli schedule.

## 4. Architettura
```
Telegram ──voce/audio──▶ picobot ──POST /v1/audio/transcriptions──▶ stt (faster-whisper, int8, CPU)
                           │◀──────────── {"text", "language", "duration"} ────┘
                           ├─▶ "🎤 <trascrizione>"   (eco in chat, testo semplice)
                           └─▶ router (service.ask), identico a un messaggio scritto
```
Rete: interna al compose (`http://stt:8000`), nessuna porta pubblicata per `stt`, nessuna autenticazione.
Il servizio `stt` è in un **profilo compose** (`stt`): si avvia solo con `docker compose --profile stt up -d`.

## 5. Componenti
| Unità | Modifica |
|---|---|
| `stt/app.py` (nuovo) | FastAPI: `POST /v1/audio/transcriptions`, `GET /health`; modello caricato una volta all'avvio; una trascrizione alla volta |
| `stt/transcriber.py` (nuovo) | Interfaccia `Transcriber` (testabile con un finto) e implementazione faster-whisper; scelta della lingua tra quelle ammesse |
| `stt/Dockerfile` (nuovo) | `python:3.11-slim`, faster-whisper, utente non root, `HEALTHCHECK` su `/health` |
| `stt/pyproject.toml` (nuovo) | dipendenze del servizio (faster-whisper, fastapi, uvicorn, python-multipart), separate da quelle di PicoBot |
| `stt/bench.py` (nuovo) | misura tempi e testo per `base`/`small` × beam 1/5 su file dati dall'utente |
| `stt/tests/` (nuovo) | test del servizio con trascrittore finto |
| `src/picobot/stt.py` (nuovo) | client async: `transcribe(path, filename) -> Transcript(text, language)`, solleva `SttError` |
| `src/picobot/config.py` | `stt_url`, `stt_timeout_s`, `max_voice_s` |
| `src/picobot/channels/telegram.py` | handler `filters.VOICE \| filters.AUDIO`; documenti con mime `audio/*` instradati alla trascrizione |
| `docker-compose.yaml` | servizio `stt` nel profilo `stt`, volume `./models`, limite memoria |
| `.github/workflows/release_ci-cd.yml` | test, build-check e pubblicazione anche per `stt` |
| `.env.example`, `docs/*`, `docs/manual-qa.md` | nuove variabili, pagina `voice.md` (EN/IT), righe di collaudo |

Il client in PicoBot usa `httpx`, già installato come dipendenza di `python-telegram-bot`: nessun pacchetto nuovo
nell'immagine di PicoBot.

## 6. Servizio `stt`
**API (compatibile OpenAI, sottoinsieme):**
- `POST /v1/audio/transcriptions`, multipart: `file` (obbligatorio), `language` (opzionale: forza la lingua),
  `model` (accettato e ignorato, per compatibilità). Risposta `200 {"text": str, "language": str, "duration": float}`.
  Errori: `400` file mancante o non decodificabile, `413` file oltre `STT_MAX_MB` o audio oltre `STT_MAX_SECONDS`,
  `503` modello non ancora caricato.
- `GET /health`: `200 {"status": "ok", "model": ...}` dopo il caricamento del modello, `503` prima.

**Motore:** `WhisperModel(STT_MODEL, device="cpu", compute_type=STT_COMPUTE_TYPE, cpu_threads=STT_THREADS)`.
Decodifica dell'audio con la libreria di faster-whisper (PyAV): OGG/Opus, mp3, m4a e wav senza ffmpeg di sistema.
Filtro VAD attivo per saltare il silenzio.

**Lingua:** con `STT_LANGUAGES=it,en` il servizio ottiene le probabilità delle lingue dal rilevamento di
faster-whisper e trascrive con la lingua più probabile **tra quelle ammesse** (es. `es`=0,6 e `it`=0,4 → `it`).
Un solo passaggio di trascrizione. Se la richiesta specifica `language`, si usa quella.

**Concorrenza:** una trascrizione alla volta (lock), eseguita in un thread per non bloccare l'event loop: due
trascrizioni parallele su 4 core sarebbero entrambe più lente. Le altre richieste attendono.

**Modelli:** scaricati da Hugging Face al primo avvio nel volume `./models` (`HF_HOME=/models`); dal secondo avvio
nessun accesso a internet. Nessun file audio salvato oltre la durata della richiesta.

**Variabili:**
| Variabile | Default | Ruolo |
|---|---|---|
| `STT_MODEL` | `small` (provvisorio) | modello faster-whisper multilingua |
| `STT_COMPUTE_TYPE` | `int8` | quantizzazione per CPU |
| `STT_THREADS` | `4` | thread CTranslate2 |
| `STT_BEAM_SIZE` | `1` (provvisorio) | 1 più veloce, 5 più accurato |
| `STT_LANGUAGES` | `it,en` | lingue ammesse |
| `STT_MAX_MB` | `20` | dimensione massima del file |
| `STT_MAX_SECONDS` | `300` | durata massima dell'audio |

## 7. PicoBot: flusso Telegram
Tutto sotto il lock della chat già esistente.
1. Utente non autorizzato → ignorato, come per il testo.
2. `STT_URL` vuoto → "I messaggi vocali non sono abilitati." Nessun download.
3. Controlli **prima del download**: durata (`voice.duration`/`audio.duration`, se presente) ≤ `MAX_VOICE_S` e
   dimensione ≤ `MAX_UPLOAD_MB`. Altrimenti "Vocale troppo lungo (max N minuti)." / "File troppo grande (max N MB)."
4. Download in `data/inbox/<uuid><estensione>`, indicatore "sta scrivendo…".
5. `stt.transcribe()`; testo ripulito con `strip()`.
6. Testo vuoto → "Non ho capito il vocale, puoi ripeterlo o scriverlo?" Il router non viene chiamato.
7. Eco: "🎤 <testo>" in **testo semplice** (niente Markdown), diviso con `split_text` se lungo.
8. Testo per il router: il testo trascritto così com'è; per un file audio con didascalia
   `"<didascalia>\n\n[Trascrizione audio]: <testo>"`.
9. `_ask(update, ctx, testo)`: stessa sessione, memoria, profilo e conferme del codice del testo scritto.
10. Il file in `data/inbox/` viene cancellato sempre (`finally`).

**Documenti audio:** in `on_document`, un documento con `mime_type` che inizia per `audio/` segue il flusso sopra
invece di essere rifiutato come formato non supportato. Per i documenti la durata non è nota prima del download: vale
il limite `STT_MAX_SECONDS` del servizio (risposta `413`).

**Variabili di PicoBot:**
| Variabile | Default | Ruolo |
|---|---|---|
| `STT_URL` | *(vuoto = spento)* | es. `http://stt:8000` |
| `STT_TIMEOUT_S` | `180` | attesa massima della risposta di `stt` |
| `MAX_VOICE_S` | `300` | durata massima controllata prima del download |

## 8. Errori
| Caso | Risposta all'utente | Log |
|---|---|---|
| `stt` non raggiungibile, timeout, `5xx`, `503` | "Trascrizione non disponibile al momento: riprova o scrivi il messaggio." | eccezione |
| `400` (audio illeggibile) | "Non riesco a leggere questo audio." | warning |
| `413` | "Vocale troppo lungo (max N minuti)." | info |
| Trascrizione vuota | "Non ho capito il vocale, puoi ripeterlo o scriverlo?" | info |
| Download da Telegram fallito | "Impossibile scaricare il vocale, riprova." | eccezione |
`SttError` porta il tipo di errore (`unavailable`, `unreadable`, `too_long`); il canale sceglie il messaggio.
Un errore di trascrizione non interrompe mai il bot né lascia file in `inbox/`.

## 9. Deploy
- `docker-compose.yaml`: servizio `stt` con `profiles: ["stt"]`, `build: ./stt`, nessuna sezione `ports`,
  volume `./models:/models`, `mem_limit: 2g`, `restart: unless-stopped`; niente `depends_on` in `picobot`
  (se `stt` è giù vale la sezione 8).
- Prima volta: `mkdir -p models && sudo chown -R 1000 models`; in `.env` `STT_URL=http://stt:8000`;
  `docker compose --profile stt up -d --build`.
- Immagine pubblicata: `ghcr.io/jumping2000/picobot-stt` con gli stessi tag di `picobot`.

## 10. CI
- `test`: aggiunge `uv run pytest stt/tests` (trascrittore finto, nessun download di modelli).
- `docker-check`: build anche di `stt/` e smoke test `python -c "import faster_whisper"`; nessun avvio del modello.
- `build-docker`: build multi-arch e push anche di `picobot-stt`, scansione Trivy e SBOM inclusi.

## 11. Test
**Servizio** (`stt/tests`, TestClient con trascrittore finto):
1. risposta `{"text", "language", "duration"}` per un file valido;
2. scelta della lingua tra le ammesse (`es`=0,6, `it`=0,4 → `it`); `language` esplicito rispettato;
3. silenzio → `text` vuoto, `200`;
4. `/health` e trascrizione → `503` prima del caricamento del modello;
5. due richieste simultanee eseguite in sequenza;
6. file mancante → `400`; oltre `STT_MAX_MB` o `STT_MAX_SECONDS` → `413`.

**Client** (`tests/test_stt.py`, `httpx.MockTransport`): successo → `Transcript`; timeout, connessione rifiutata,
`5xx`, `503` → `SttError("unavailable")`; `400` → `"unreadable"`; `413` → `"too_long"`.

**Telegram** (`tests/test_channels.py`, fake esistenti):
1. vocale → eco "🎤 …" e poi `service.ask` con il testo esatto;
2. trascrizione vuota → nessuna chiamata al router;
3. `STT_URL` vuoto → messaggio "non abilitati", nessun download;
4. durata oltre `MAX_VOICE_S` → rifiuto senza download;
5. documento `audio/mpeg` → trascritto; documento non audio → comportamento v0.5 invariato;
6. audio con didascalia → testo composto come in sezione 7;
7. `inbox/` vuota dopo successo ed errori;
8. utente non autorizzato → ignorato.

**Statici** (`tests/test_docker_static.py`): `stt` nel profilo `stt`, senza `ports`, con volume `./models`;
`stt/Dockerfile` con utente non root.

**Regressione:** i 163 test esistenti restano verdi.

**Collaudo manuale** (nuove righe in `docs/manual-qa.md`, modello reale sul N100):
1. vocale italiano "quotazione di AAPL": eco corretta, stessa risposta del testo scritto;
2. vocale inglese: lingua `en`;
3. vocale muto: richiesta di ripetere;
4. `stt` fermo: messaggio d'errore, PicoBot funzionante;
5. mp3 con didascalia "riassumi";
6. `stt/bench.py` con un vocale italiano e uno inglese: tempi annotati, scelta di `STT_MODEL` e `STT_BEAM_SIZE`.

Non verificabile in sviluppo: qualità e latenza reali sul N100, Telegram reale, download dei modelli da Hugging Face.
