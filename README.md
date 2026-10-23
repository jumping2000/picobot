# PicoBot v0.3 — assistente multi-agente (Agno 3): Telegram, CLI, API REST

## Architettura (costo minimo)
```
Router (Team coordinate, modello ECONOMICO, con sessione + memoria + learning)
 |- risponde da solo a domande/conversazione ............ 1 chiamata LLM
 |- Finance  (yfinance)         modello economico
 |- Web      (DuckDuckGo)       modello economico
 |- Coder    (Python, HITL)     modello economico
 '- ComplexTeam (Researcher, Analyst, Writer, Critic)   modello STRONG, solo task complessi
Workflow DocSummary: estrazione testo (codice) -> map parallelo se lungo -> riduzione (modello economico)
  Il riassunto entra nella sessione del router (nessuna chiamata LLM): i follow-up funzionano e costano 1 chiamata.
  Limite: il follow-up vede il riassunto, non l'intero documento.
Scheduler: cron su SQLite, stessi prompt dell'utente, esito sul canale che li ha creati
```
Un task schedulato non puo' eseguire codice (nessun umano per confermare).

## Canali
- **Telegram**: testo, documenti (PDF/DOCX/TXT/MD/CSV/JSON/LOG; la didascalia = istruzioni), conferme a bottoni.
- **CLI**: `python -m picobot cli` (conferme y/N, `/file <percorso>`).
- **API**: `Authorization: Bearer <token>`; `POST /v1/chat`, `POST /v1/summarize` (multipart), `GET|DELETE /v1/memory`,
  `GET|POST /v1/schedules`, `DELETE /v1/schedules/{id}`, `GET /health`. Docs: `/docs`.
  Il codice si esegue solo con `"approve_code": true` nella richiesta.
  `/v1/summarize` accetta `session_id` (e lo restituisce): usalo in `/v1/chat` per le domande sul documento.
  HTTPS diretto, senza reverse proxy: `API_SSL_CERTFILE` + `API_SSL_KEYFILE` (se esponi l'API senza TLS parte un warning).
- Comandi (Telegram/CLI): `/help /new /memory /forget(con conferma) /schedule /schedules /unschedule`.

```bash
curl -X POST localhost:8000/v1/chat -H "Authorization: Bearer $TOKEN" -H "content-type: application/json" \
     -d '{"message":"quotazione AAPL"}'
curl -X POST localhost:8000/v1/summarize -H "Authorization: Bearer $TOKEN" -F file=@report.pdf -F instruction="5 punti"
```
Schedule: `/schedule 0 8 * * 1-5 | quotazioni AAPL e MSFT` (cron a 5 campi, fuso `TIMEZONE`, minimo 30 min).

## Sicurezza
Telegram fail-closed (senza ID autorizzati non parte); token API confrontati a tempo costante, API su 127.0.0.1 di default (`API_BIND=0.0.0.0` per esporla);
codice generato: sempre dopo conferma, processo separato, env ripulito (nessuna chiave), timeout, limiti CPU/RAM,
cwd = `workspace/` (il DB sta in `data/`, non visibile). Il processo ha pero' rete libera: l'isolamento reale e' il container.

## Avvio
```bash
cp .env.example .env && mkdir data workspace && sudo chown -R 1000 data workspace
docker compose up -d --build
```
`picobot serve` avvia Telegram + API + scheduler in un solo processo (flag `--no-telegram`, `--no-api`).
Test: `uv run --group dev pytest tests` (LLM finto, nessuna chiave).
