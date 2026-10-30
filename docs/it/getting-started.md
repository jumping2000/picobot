# Per iniziare

🇮🇹 Italiano · 🇬🇧 [English](../en/getting-started.md) · ⬅️ [Indice](index.md)

## Requisiti

| Elemento | Note |
|---|---|
| Chiave API LLM | [OpenRouter](https://openrouter.ai/) (default) o qualsiasi endpoint compatibile OpenAI (`OPENAI_API_KEY` + `OPENROUTER_BASE_URL`) |
| Almeno un canale | Token di bot Telegram (da [@BotFather](https://t.me/BotFather)) e/o un token API |
| Docker + Compose | Modo consigliato per eseguire PicoBot |
| [uv](https://docs.astral.sh/uv/) | Serve sull'host per la CLI delle skill, l'esecuzione locale e i test |

> [!NOTE]
> La sola CLI non basta per `picobot serve`: servono Telegram o l'API. La CLI si avvia a parte con `picobot cli`.

## 1. Configurazione

```bash
git clone https://github.com/jumping2000/picobot.git && cd picobot
cp .env.example .env
```

Modifica `.env` impostando almeno:

```dotenv
OPENROUTER_API_KEY=sk-or-...
LLM_MODEL_ID=openai/gpt-4o-mini          # economico: router, SimpleTeam, riassunti
LLM_STRONG_MODEL_ID=openai/gpt-4o        # forte: solo ComplexTeam (vuoto = uguale a LLM_MODEL_ID)

# Telegram (opzionale)
TELEGRAM_BOT_TOKEN=123456:ABC...
TELEGRAM_ALLOWED_USER_IDS=123456789      # il tuo id numerico Telegram; separati da virgola

# API REST (opzionale): "token:user_id", separati da virgola
API_TOKENS=<token-lungo-casuale>:123456789
```

> [!TIP]
> Genera un token con `python -c "import secrets; print(secrets.token_urlsafe(32))"`.
> Usa il tuo id Telegram come `user_id` dell'API (e come `CLI_USER_ID`) per **condividere memoria e profilo tra i canali**.

Chiavi e segreti restano in `.env`; tutte le altre impostazioni vanno in `config/config.yaml` (facoltativo: senza
il file valgono i default):

```bash
cp config/config_example.yaml config/config.yaml
```

Tutte le opzioni sono descritte in [Configurazione](configuration.md).

## 2. Preparazione delle cartelle

```bash
mkdir -p data workspace skills && sudo chown -R 1000 data workspace skills
```

Il container gira con l'utente `picobot` (UID 1000), che deve poter scrivere in `data/`, `workspace/` e `skills/`
(quest'ultima serve per installare le skill da chat).

| Cartella host | Container | Modo | Contenuto |
|---|---|---|---|
| `./data` | `/app/data` | rw | DB SQLite, stato Telegram, outbox, inbox |
| `./workspace` | `/app/workspace` | rw | Script e file generati dagli agenti |
| `./config` | `/app/config` | ro | `config.yaml`, `mcp_config.json` |
| `./skills` | `/app/skills` | rw | Skill installate (ricarica a caldo; installabili da chat) |
| `./certs` | `/app/certs` | ro | Certificati TLS opzionali (commentato nel compose) |

## 3. (Opzionale) Installazione delle skill

Le skill abilitano i documenti Office. Per esempio, con le skill `docx`, `pptx` e `xlsx` sul disco:

```bash
uv run picobot skills add /percorso/skills/docx
uv run picobot skills add /percorso/skills/pptx
uv run picobot skills add /percorso/skills/xlsx
```

Vedi [Skill](skills.md). Con `ADMIN_USER_IDS` in `.env` puoi installarle anche da Telegram (`/skill_add`).

> [!TIP]
> **Messaggi vocali (opzionale):** `mkdir -p models && sudo chown -R 1000 models`, imposta
> `voice.stt_url: http://stt:8000` in `config/config.yaml` e aggiungi `COMPOSE_PROFILES=stt` a `.env` (oppure
> `--profile stt` a ogni comando `docker compose`). Vedi [Messaggi vocali](voice.md).

## 4. Avvio

```bash
docker compose up -d                # immagini pronte; build locale: docker compose -f compose-build.yaml up -d --build
docker compose logs -f picobot      # atteso "PicoBot pronto (modello=..., strong=..., mcp=N)."
```

`picobot serve` (il comando del container) avvia Telegram, l'API e lo scheduler in un solo processo.
Flag: `--no-telegram`, `--no-api`.

## 5. Prova

**Telegram**: invia `/help`, poi per esempio "quotazione AAPL" o un PDF senza didascalia (viene riassunto).

**CLI**:

```bash
docker compose exec -it picobot python -m picobot cli
```

**API**:

```bash
curl localhost:8000/health
curl -X POST localhost:8000/v1/chat -H "Authorization: Bearer $TOKEN" \
     -H "content-type: application/json" -d '{"message":"ciao"}'
```

Documentazione OpenAPI interattiva: `http://localhost:8000/docs`.

## Immagini pronte o build locale

Il repository ha due file compose, con gli stessi servizi, cartelle e volumi:

| File | Immagini | Comando |
|---|---|---|
| `compose.yaml` (predefinito) | `ghcr.io/jumping2000/picobot` e `picobot-stt`, già pronte | `docker compose up -d` |
| `compose-build.yaml` | costruite in locale da `Dockerfile` e `stt/` | `docker compose -f compose-build.yaml up -d --build` |

In entrambi il servizio `stt` (trascrizione dei vocali) parte solo con il profilo `stt`: `--profile stt`, oppure
`COMPOSE_PROFILES=stt` in `.env`. Con `compose-build.yaml` ogni comando `docker compose` vuole
`-f compose-build.yaml`; senza, agisce su `compose.yaml`.

Ogni release su GitHub pubblica immagini multi-architettura (linux/amd64, linux/arm64) su GitHub Container
Registry:

| Tag | Significato |
|---|---|
| `latest` | Ultima release stabile |
| `0.8.0`, `0.8` | Una versione precisa / l'ultima patch di una versione minore |
| `sha-<commit>` | Commit esatto |

> [!NOTE]
> L'immagine pronta contiene già le librerie elencate in `deps/` (quelle delle skill di esempio `docx`, `pptx`,
> `xlsx`). Se una skill richiede altre librerie, aggiungile in `deps/` e usa `compose-build.yaml`.

## Esecuzione senza Docker

```bash
uv sync
export DATA_DIR=./data WORKSPACE_DIR=./workspace SKILLS_DIR=./skills MCP_CONFIG_PATH=./config/mcp_config.json
uv run picobot serve          # oppure: uv run picobot cli
```

> [!CAUTION]
> Fuori da Docker non c'è il confine del container: il codice generato (dopo la tua conferma) gira con i permessi
> e l'accesso di rete del tuo utente. Preferisci Docker. Le skill Office richiedono anche Node.js e i pacchetti in `deps/`.

## Aggiornamento

```bash
docker compose pull && docker compose up -d                          # compose.yaml
git pull && docker compose -f compose-build.yaml up -d --build       # compose-build.yaml
```

I dati in `data/` (sessioni, memorie, schedule) vengono conservati.
