# Messaggi vocali

🇮🇹 Italiano · 🇬🇧 [English](../en/voice.md) · ⬅️ [Indice](index.md)

Puoi parlare a PicoBot su Telegram. Le note vocali e i file audio vengono trascritti da un container separato,
`stt` ([faster-whisper](https://github.com/SYSTRAN/faster-whisper) su CPU), e il testo arriva al router esattamente
come se lo avessi scritto. L'audio non esce mai dal tuo host.

```
Telegram ──voce/audio──▶ picobot ──POST /v1/audio/transcriptions──▶ stt (faster-whisper, int8, CPU)
                           │◀──────────── {"text", "language", "duration"} ────┘
                           ├─▶ "🎤 <trascrizione>"   (eco in chat)
                           └─▶ router, come un messaggio scritto
```

La funzione è **spenta di default**: con `STT_URL` vuoto PicoBot si comporta esattamente come la v0.5.

## Attivazione

```bash
mkdir -p models && sudo chown -R 1000 models
[ -f config/config.yaml ] || cp config/config_example.yaml config/config.yaml
# in config/config.yaml, blocco voice:  stt_url: http://stt:8000
docker compose --profile stt up -d --build
docker compose logs -f stt          # al primo avvio scarica il modello da Hugging Face
```

- Il servizio `stt` sta nel **profilo** compose `stt`: un semplice `docker compose up -d` avvia solo PicoBot.
- Il modello resta in cache in `./models`: internet serve solo al primo avvio. Il container risulta *healthy*
  quando il modello è caricato.
- `stt` non pubblica **nessuna porta**: lo raggiunge solo PicoBot, sulla rete interna del compose.
- Immagine pronta: sostituisci `build: ./stt` con `image: ghcr.io/jumping2000/picobot-stt:latest`.

## Cosa puoi inviare

| Input | Gestito |
|---|---|
| Nota vocale Telegram (OGG/Opus) | ✅ |
| File audio (mp3, m4a, wav, ogg…) | ✅ |
| Audio inviato "come file" (documento di tipo `audio/*`) | ✅ |
| Audio con didascalia (es. "riassumi") | ✅ il router riceve `<didascalia>\n\n[Trascrizione audio]: <testo>` |
| Video-messaggi tondi, API, CLI | ❌ non supportati |

Lingue: **italiano e inglese**, rilevate automaticamente. Sui vocali brevi il rilevamento può confondere
l'italiano con spagnolo o portoghese, quindi `stt` sceglie la lingua più probabile **tra quelle ammesse**
(`STT_LANGUAGES`).

## Cosa vede l'utente

Il bot scrive prima la trascrizione (`🎤 …`), poi risponde. Se la trascrizione è sbagliata te ne accorgi subito;
l'esecuzione di codice chiede comunque conferma, come sempre.

| Caso | Risposta del bot |
|---|---|
| Trascrizione riuscita | `🎤 <testo>`, poi la risposta |
| Solo silenzio o rumore | "Non ho capito il vocale, puoi ripeterlo o scriverlo?" |
| Oltre `MAX_VOICE_S` / limite del server | "Vocale troppo lungo (max 5 minuti)." |
| Oltre `MAX_UPLOAD_MB` | "File troppo grande (max 15 MB)." |
| `stt` giù o timeout | "Trascrizione non disponibile al momento: riprova o scrivi il messaggio." |
| Audio illeggibile | "Non riesco a leggere questo audio." |
| Download da Telegram fallito | "Impossibile scaricare il vocale, riprova." |
| `STT_URL` vuoto | "I messaggi vocali non sono abilitati." |

Al router non arriva nulla se la trascrizione manca o non è affidabile.

## Configurazione

PicoBot (`.env`):

| Variabile | Default | Descrizione |
|---|---|---|
| `STT_URL` | *(vuoto = spento)* | es. `http://stt:8000` |
| `STT_TIMEOUT_S` | `180` | Attesa massima della trascrizione |
| `MAX_VOICE_S` | `300` | Durata massima, controllata prima del download |

Container `stt` (impostale in `.env`; il compose le passa al container):

| Variabile | Default | Descrizione |
|---|---|---|
| `STT_MODEL` | `small` | Modello faster-whisper multilingua (`base`, `small`, …) |
| `STT_COMPUTE_TYPE` | `int8` | Quantizzazione per CPU |
| `STT_THREADS` | `4` | Thread della CPU |
| `STT_BEAM_SIZE` | `1` | 1 = più veloce, 5 = più accurato |
| `STT_LANGUAGES` | `it,en` | Lingue ammesse |
| `STT_MAX_MB` | `20` | Dimensione massima del file |
| `STT_MAX_SECONDS` | `300` | Durata massima dell'audio (vale anche per i file senza durata nei metadati) |

`stt` trascrive **una richiesta alla volta**: su una CPU a 4 core due trascrizioni parallele sarebbero entrambe
più lente. Le altre richieste aspettano in coda. La memoria è limitata a 2 GB (`mem_limit`).

## Scelta del modello (benchmark)

I default (`small`, beam 1) sono un punto di partenza. Misura sul tuo hardware con un vocale reale in italiano e
uno in inglese:

```bash
cp ~/voce_it.ogg ~/voice_en.ogg models/
docker compose --profile stt run --rm stt python bench.py /models/voce_it.ogg /models/voice_en.ogg \
    --models base small --beams 1 5
```

Per ogni modello e beam, `bench.py` stampa la durata dell'audio, i secondi impiegati, l'**RTF** (secondi impiegati
/ durata dell'audio: sotto 1 è più veloce del parlato), la lingua rilevata e l'inizio del testo. Scegli la
combinazione più veloce con un testo ancora corretto, poi imposta `STT_MODEL` / `STT_BEAM_SIZE` in `.env` e
lancia `docker compose --profile stt up -d`.

## API del servizio `stt`

Sottoinsieme compatibile OpenAI, raggiungibile solo dentro la rete del compose:

- `POST /v1/audio/transcriptions`, multipart `file` (obbligatorio), `language` (opzionale, forza la lingua),
  `model` (accettato e ignorato) → `{"text", "language", "duration"}`. Errori: `400` file mancante o illeggibile,
  `413` troppo grande o troppo lungo, `503` modello non ancora caricato.
- `GET /health` → `200` quando il modello è caricato, `503` prima.

Grazie all'interfaccia standard puoi puntare `STT_URL` a un altro server compatibile OpenAI senza cambiare PicoBot.

## Privacy e sicurezza

- L'audio viene scaricato in `data/inbox/` e **sempre cancellato** dopo la richiesta; `stt` non conserva nulla.
- Le chiavi API di PicoBot non arrivano al container `stt` (niente `env_file`).
- `stt` gira con un utente non root e non pubblica porte.
- La trascrizione entra nella sessione della conversazione come un qualsiasi messaggio scritto.

## Risoluzione problemi

| Sintomo | Soluzione |
|---|---|
| "Trascrizione non disponibile…" | `docker compose --profile stt ps`: `stt` è attivo e healthy? Controlla `docker compose logs stt` |
| `stt` non diventa mai healthy | Primo avvio: il modello si sta ancora scaricando, o Hugging Face non è raggiungibile |
| `PermissionError` su `/models` | `sudo chown -R 1000 models` |
| Trascrizioni lente | Lancia `bench.py`; prova `STT_MODEL=base` o `STT_BEAM_SIZE=1` |
| Lingua sbagliata | Controlla `STT_LANGUAGES`; sui vocali brevissimi parla un po' più a lungo |
