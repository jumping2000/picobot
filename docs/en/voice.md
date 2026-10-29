# Voice messages

🇬🇧 English · 🇮🇹 [Italiano](../it/voice.md) · ⬅️ [Index](index.md)

You can talk to PicoBot on Telegram. Voice notes and audio files are transcribed by a separate container, `stt`
([faster-whisper](https://github.com/SYSTRAN/faster-whisper) on CPU), and the text goes to the router exactly as if
you had typed it. The audio never leaves your host.

```
Telegram ──voice/audio──▶ picobot ──POST /v1/audio/transcriptions──▶ stt (faster-whisper, int8, CPU)
                            │◀──────────── {"text", "language", "duration"} ────┘
                            ├─▶ "🎤 <transcript>"   (echo in the chat)
                            └─▶ router, same as a typed message
```

The feature is **off by default**: with `STT_URL` empty PicoBot behaves exactly like v0.5.

## Enabling

```bash
mkdir -p models && sudo chown -R 1000 models
[ -f config/config.yaml ] || cp config/config_example.yaml config/config.yaml
# in config/config.yaml, voice block:  stt_url: http://stt:8000
docker compose --profile stt up -d --build
docker compose logs -f stt          # the first start downloads the model from Hugging Face
```

- The `stt` service lives in the compose **profile** `stt`: a plain `docker compose up -d` starts only PicoBot.
- The model is cached in `./models`: Internet access is needed only on the first start. The container reports
  *healthy* once the model is loaded.
- `stt` publishes **no port**: only PicoBot reaches it, on the internal compose network.
- Prebuilt image: replace `build: ./stt` with `image: ghcr.io/jumping2000/picobot-stt:latest`.

## What you can send

| Input | Handled |
|---|---|
| Telegram voice note (OGG/Opus) | ✅ |
| Audio file (mp3, m4a, wav, ogg…) | ✅ |
| Audio sent "as a file" (document with `audio/*` type) | ✅ |
| Audio with a caption (e.g. "summarize") | ✅ the router receives `<caption>\n\n[Trascrizione audio]: <text>` |
| Round video messages, API, CLI | ❌ not supported |

Languages: **Italian and English**, detected automatically. On short clips the language detector can confuse
Italian with Spanish or Portuguese, so `stt` picks the most likely language **among the allowed ones**
(`STT_LANGUAGES`).

## What the user sees

The bot first writes the transcript (`🎤 …`), then answers. If the transcript is wrong you see it at once; code
execution still asks for confirmation, as always.

| Case | Bot reply |
|---|---|
| Transcript OK | `🎤 <text>`, then the answer |
| Silence or noise only | "Non ho capito il vocale, puoi ripeterlo o scriverlo?" |
| Longer than `MAX_VOICE_S` / server limit | "Vocale troppo lungo (max 5 minuti)." |
| Larger than `MAX_UPLOAD_MB` | "File troppo grande (max 15 MB)." |
| `stt` down or timeout | "Trascrizione non disponibile al momento: riprova o scrivi il messaggio." |
| Unreadable audio | "Non riesco a leggere questo audio." |
| Download from Telegram failed | "Impossibile scaricare il vocale, riprova." |
| `STT_URL` empty | "I messaggi vocali non sono abilitati." |

Nothing reaches the router when the transcript is missing or unreliable.

## Configuration

PicoBot (`.env`):

| Variable | Default | Description |
|---|---|---|
| `STT_URL` | *(empty = off)* | e.g. `http://stt:8000` |
| `STT_TIMEOUT_S` | `180` | Max wait for a transcript |
| `MAX_VOICE_S` | `300` | Max duration, checked before downloading |

`stt` container (set them in `.env`; the compose file passes them to the container):

| Variable | Default | Description |
|---|---|---|
| `STT_MODEL` | `small` | faster-whisper multilingual model (`base`, `small`, …) |
| `STT_COMPUTE_TYPE` | `int8` | Quantization for CPU |
| `STT_THREADS` | `4` | CPU threads |
| `STT_BEAM_SIZE` | `1` | 1 = faster, 5 = more accurate |
| `STT_LANGUAGES` | `it,en` | Allowed languages |
| `STT_MAX_MB` | `20` | Max file size |
| `STT_MAX_SECONDS` | `300` | Max audio duration (covers files without duration metadata) |

`stt` transcribes **one request at a time**: on a 4-core CPU two parallel transcriptions would both be slower.
Other requests wait in line. Memory is capped at 2 GB (`mem_limit`).

## Choosing the model (benchmark)

The defaults (`small`, beam 1) are a starting point. Measure on your own hardware with a real Italian and a real
English voice note:

```bash
cp ~/voce_it.ogg ~/voice_en.ogg models/
docker compose --profile stt run --rm stt python bench.py /models/voce_it.ogg /models/voice_en.ogg \
    --models base small --beams 1 5
```

`bench.py` prints, for each model and beam: audio duration, seconds taken, **RTF** (seconds taken / audio
duration; below 1 means faster than real time), detected language and the beginning of the text. Pick the
fastest combination whose text is still correct, then set `STT_MODEL` / `STT_BEAM_SIZE` in `.env` and
`docker compose --profile stt up -d`.

## API of the `stt` service

OpenAI-compatible subset, reachable only inside the compose network:

- `POST /v1/audio/transcriptions`, multipart `file` (required), `language` (optional, forces the language),
  `model` (accepted and ignored) → `{"text", "language", "duration"}`. Errors: `400` missing or unreadable file,
  `413` too large or too long, `503` model not loaded yet.
- `GET /health` → `200` once the model is loaded, `503` before.

Because the interface is standard, you can point `STT_URL` at another OpenAI-compatible server without changing
PicoBot.

## Privacy and security

- The audio is downloaded to `data/inbox/` and **always deleted** after the request; `stt` keeps nothing.
- The PicoBot API keys are not passed to the `stt` container (no `env_file`).
- `stt` runs as a non-root user and publishes no port.
- The transcript enters the conversation session like any typed message.

## Troubleshooting

| Symptom | Fix |
|---|---|
| "Trascrizione non disponibile…" | `docker compose --profile stt ps`: is `stt` running and healthy? Check `docker compose logs stt` |
| `stt` never becomes healthy | First start: the model is still downloading, or Hugging Face is unreachable |
| `PermissionError` on `/models` | `sudo chown -R 1000 models` |
| Slow transcripts | Run `bench.py`; try `STT_MODEL=base` or `STT_BEAM_SIZE=1` |
| Wrong language | Check `STT_LANGUAGES`; speak a little longer on very short clips |
