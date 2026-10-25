# API REST

🇮🇹 Italiano · 🇬🇧 [English](../en/api.md) · ⬅️ [Indice](index.md)

Applicazione FastAPI ([`channels/api.py`](../../src/picobot/channels/api.py)). Documentazione OpenAPI interattiva:
`http://localhost:8000/docs`.

## Autenticazione

Tutti gli endpoint tranne `/health` richiedono:

```
Authorization: Bearer <token>
```

I token si configurano in `API_TOKENS` come coppie `token:user_id`. Lo `user_id` seleziona memoria, profilo,
schedule e file: usa il tuo id Telegram per condividerli con Telegram. Token mancante o non valido → `401`.

> [!WARNING]
> Senza TLS il token viaggia in chiaro. Se esponi l'API (`API_BIND=0.0.0.0`), imposta `API_SSL_CERTFILE` e
> `API_SSL_KEYFILE`, oppure mettila dietro un reverse proxy HTTPS.

## Endpoint

| Metodo | Percorso | Descrizione |
|---|---|---|
| `GET` | `/health` | `{"status": "ok", "version": "0.6.0"}` — senza autenticazione |
| `POST` | `/v1/chat` | Invia un messaggio |
| `GET` | `/v1/files/{id}` | Scarica un file consegnato (24 h) |
| `POST` | `/v1/summarize` | Riassume un documento caricato o una pagina web (form) |
| `GET` | `/v1/memory` | Memorie, profilo, entità |
| `DELETE` | `/v1/memory?confirm=true` | Cancella memorie, profilo, entità |
| `GET` | `/v1/schedules` | Elenco dei task |
| `POST` | `/v1/schedules` | Crea un task |
| `DELETE` | `/v1/schedules/{id}` | Elimina un task |

### `POST /v1/chat`

Richiesta:

| Campo | Tipo | Default | Note |
|---|---|---|---|
| `message` | stringa | — | 1-8.000 caratteri |
| `session_id` | stringa | casuale | `[A-Za-z0-9_-]`, max 80. Riusalo per continuare una conversazione |
| `approve_code` | bool | `false` | Pre-approva l'esecuzione di codice per **questa richiesta** |
| `target` | `auto` \| `simple` \| `complex` | `auto` | `auto` = decide il router |

Risposta:

```json
{
  "answer": "Ecco il tuo documento...",
  "session_id": "a1b2c3d4",
  "files": [{"id": "3f2c...e9", "name": "relazione.docx", "size": 18234}]
}
```

> [!IMPORTANT]
> L'API non ha una conferma interattiva. Senza `"approve_code": true` gli agenti non possono eseguire codice,
> quindi non possono generare file Office. Con il flag, fino a `CODE_MAX_RUNS` esecuzioni sono approvate senza revisione.

Le richieste con lo stesso `session_id` vengono serializzate.

### `GET /v1/files/{id}`

Restituisce il file come allegato. Un file di un altro utente, un file scaduto e un id non valido danno tutti lo
stesso `404`. I file vengono eliminati dopo `OUTBOX_TTL_H` (24 h).

### `POST /v1/summarize`

Form (multipart con `file`, oppure normale con `url`):

| Campo | Obbligatorio | Note |
|---|---|---|
| `file` | uno tra `file` e `url` | PDF, DOCX, TXT, MD, CSV, JSON, LOG; max `MAX_UPLOAD_MB` |
| `url` | uno tra `file` e `url` | Pagina web `http`/`https` (articoli, blog); rete privata rifiutata |
| `instruction` | no | es. "in 5 punti" (max 1.000 caratteri) |
| `session_id` | no | Usa il valore restituito in `/v1/chat` per le domande successive |

Risposta: `{"summary": "...", "session_id": "..."}`. Sempre diretto (senza router). Una pagina non
scaricabile o senza articolo leggibile dà `422` con il motivo.

### `GET /v1/memory`

```json
{
  "memories": ["Lavora nella finanza"],
  "profile": {"lingua": "italiano", "titoli_seguiti": "AAPL, ENI.MI"},
  "entities": [{"name": "Harbor", "type": "progetto", "description": "Progetto con Sara"}]
}
```

Campi del profilo: `name`, `preferred_name`, `lingua`, `fuso_orario`, `formato_risposta`, `titoli_seguiti`.
Vengono restituiti solo quelli valorizzati.

### Schedule

```bash
# crea
curl -X POST localhost:8000/v1/schedules -H "Authorization: Bearer $TOKEN" -H "content-type: application/json" \
     -d '{"cron": "0 8 * * 1-5", "prompt": "quotazioni AAPL e MSFT"}'
# -> 201 {"id": 3}
curl localhost:8000/v1/schedules -H "Authorization: Bearer $TOKEN"
curl -X DELETE localhost:8000/v1/schedules/3 -H "Authorization: Bearer $TOKEN"   # -> 204
```

Ogni voce di `GET /v1/schedules` contiene `id`, `cron`, `prompt`, `created_at`, `last_run` e `last_result`:
i task creati dall'API non vengono notificati, i risultati si leggono qui.

## Codici di errore

| Codice | Quando |
|---|---|
| `400` | `DELETE /v1/memory` senza `?confirm=true` |
| `401` | Token mancante o non valido |
| `404` | File o schedule non trovato (o non tuo) |
| `413` | Upload oltre `MAX_UPLOAD_MB` |
| `415` | Formato del documento non supportato |
| `422` | Errore di validazione, cron non valido, intervallo troppo breve, limite di schedule, documento illeggibile |
| `500` | Errore interno durante `/v1/chat` |

## Esempi

```bash
TOKEN=...
# chat, decide il router
curl -X POST localhost:8000/v1/chat -H "Authorization: Bearer $TOKEN" -H "content-type: application/json" \
     -d '{"message": "Qual è il cambio EUR/USD?"}'
# ComplexTeam diretto, con codice approvato
curl -X POST localhost:8000/v1/chat -H "Authorization: Bearer $TOKEN" -H "content-type: application/json" \
     -d '{"message": "PowerPoint di 3 slide su PicoBot", "target": "complex", "approve_code": true}'
# download
curl -OJ localhost:8000/v1/files/<id> -H "Authorization: Bearer $TOKEN"
# riassunto
curl -X POST localhost:8000/v1/summarize -H "Authorization: Bearer $TOKEN" \
     -F file=@relazione.pdf -F instruction="in 5 punti"
curl -X POST localhost:8000/v1/summarize -H "Authorization: Bearer $TOKEN" \
     -F url=https://microservices.io/post/architecture/2026/09/29/architecting-with-llms.html -F instruction="in 5 punti"
```
