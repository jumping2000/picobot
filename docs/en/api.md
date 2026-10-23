# REST API

🇬🇧 English · 🇮🇹 [Italiano](../it/api.md) · ⬅️ [Index](index.md)

FastAPI application ([`channels/api.py`](../../src/picobot/channels/api.py)). Interactive OpenAPI docs:
`http://localhost:8000/docs`.

## Authentication

Every endpoint except `/health` requires:

```
Authorization: Bearer <token>
```

Tokens are configured in `API_TOKENS` as `token:user_id` pairs. The `user_id` selects memory, profile, schedules
and files: use your Telegram ID to share them with Telegram. Missing or invalid token → `401`.

> [!WARNING]
> Without TLS the token travels in clear text. If you expose the API (`API_BIND=0.0.0.0`), set
> `API_SSL_CERTFILE` and `API_SSL_KEYFILE`, or put it behind an HTTPS reverse proxy.

## Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | `{"status": "ok", "version": "0.5.0"}` — no auth |
| `POST` | `/v1/chat` | Send a message |
| `GET` | `/v1/files/{id}` | Download a delivered file (24 h) |
| `POST` | `/v1/summarize` | Summarize an uploaded document (multipart) |
| `GET` | `/v1/memory` | Memories, profile, entities |
| `DELETE` | `/v1/memory?confirm=true` | Delete memories, profile, entities |
| `GET` | `/v1/schedules` | List scheduled tasks |
| `POST` | `/v1/schedules` | Create a task |
| `DELETE` | `/v1/schedules/{id}` | Delete a task |

### `POST /v1/chat`

Request:

| Field | Type | Default | Notes |
|---|---|---|---|
| `message` | string | — | 1–8,000 characters |
| `session_id` | string | random | `[A-Za-z0-9_-]`, max 80. Reuse it to continue a conversation |
| `approve_code` | bool | `false` | Pre-approves code execution for **this request** |
| `target` | `auto` \| `simple` \| `complex` | `auto` | `auto` = router decides |

Response:

```json
{
  "answer": "Here is your document...",
  "session_id": "a1b2c3d4",
  "files": [{"id": "3f2c...e9", "name": "report.docx", "size": 18234}]
}
```

> [!IMPORTANT]
> The API has no interactive confirmation. Without `"approve_code": true` the agents cannot run code, so they
> cannot generate Office files. With it, up to `CODE_MAX_RUNS` executions are approved without review.

Requests on the same `session_id` are serialized.

### `GET /v1/files/{id}`

Returns the file as an attachment. A file belonging to another user, an expired file and an invalid ID all return
the same `404`. Files are purged after `OUTBOX_TTL_H` (24 h).

### `POST /v1/summarize`

Multipart form:

| Field | Required | Notes |
|---|---|---|
| `file` | yes | PDF, DOCX, TXT, MD, CSV, JSON, LOG; max `MAX_UPLOAD_MB` |
| `instruction` | no | e.g. "in 5 bullet points" (max 1,000 characters) |
| `session_id` | no | Use the returned value in `/v1/chat` for follow-up questions |

Response: `{"summary": "...", "session_id": "..."}`. Always direct (no router).

### `GET /v1/memory`

```json
{
  "memories": ["Works in finance"],
  "profile": {"lingua": "italiano", "titoli_seguiti": "AAPL, ENI.MI"},
  "entities": [{"name": "Harbor", "type": "project", "description": "Project with Sara"}]
}
```

Profile keys are the Italian field names: `name`, `preferred_name`, `lingua` (language), `fuso_orario` (time
zone), `formato_risposta` (answer format), `titoli_seguiti` (followed tickers). Only non-empty fields are returned.

### Schedules

```bash
# create
curl -X POST localhost:8000/v1/schedules -H "Authorization: Bearer $TOKEN" -H "content-type: application/json" \
     -d '{"cron": "0 8 * * 1-5", "prompt": "AAPL and MSFT quotes"}'
# -> 201 {"id": 3}
curl localhost:8000/v1/schedules -H "Authorization: Bearer $TOKEN"
curl -X DELETE localhost:8000/v1/schedules/3 -H "Authorization: Bearer $TOKEN"   # -> 204
```

Each entry of `GET /v1/schedules` includes `id`, `cron`, `prompt`, `created_at`, `last_run` and `last_result`:
tasks created through the API are not pushed anywhere, read their results here.

## Error codes

| Code | When |
|---|---|
| `400` | `DELETE /v1/memory` without `?confirm=true` |
| `401` | Missing or invalid token |
| `404` | File or schedule not found (or not yours) |
| `413` | Upload larger than `MAX_UPLOAD_MB` |
| `415` | Unsupported document format |
| `422` | Validation error, invalid cron, interval too short, schedule limit, unreadable document |
| `500` | Internal error during `/v1/chat` |

## Examples

```bash
TOKEN=...
# chat, router decides
curl -X POST localhost:8000/v1/chat -H "Authorization: Bearer $TOKEN" -H "content-type: application/json" \
     -d '{"message": "What is the EUR/USD rate?"}'
# ComplexTeam directly, with code approved
curl -X POST localhost:8000/v1/chat -H "Authorization: Bearer $TOKEN" -H "content-type: application/json" \
     -d '{"message": "3-slide PowerPoint about PicoBot", "target": "complex", "approve_code": true}'
# download
curl -OJ localhost:8000/v1/files/<id> -H "Authorization: Bearer $TOKEN"
# summary
curl -X POST localhost:8000/v1/summarize -H "Authorization: Bearer $TOKEN" \
     -F file=@report.pdf -F instruction="in 5 bullet points"
```
