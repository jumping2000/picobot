# Task programmati

🇮🇹 Italiano · 🇬🇧 [English](../en/scheduler.md) · ⬅️ [Indice](index.md)

Un task programmato è un tuo prompt eseguito periodicamente con un'espressione cron, esattamente come se lo avessi
scritto tu. L'esito viene inviato al canale che ha creato il task.

## Creazione

```text
/schedule 0 8 * * 1-5 | quotazioni AAPL e MSFT
/schedule 30 18 * * 5 | riassunto settimanale delle notizie sulle auto elettriche
```

Formato: `/schedule <minuto ora giorno mese giorno_settimana> | <richiesta>`. API: `POST /v1/schedules` con `cron`
e `prompt` (vedi [api.md](api.md)).

| Cron | Significato |
|---|---|
| `0 8 * * 1-5` | Alle 08:00 dal lunedì al venerdì |
| `0 */2 * * *` | Ogni due ore |
| `30 7 1 * *` | Alle 07:30 del primo giorno di ogni mese |

Gli orari usano `TIMEZONE` (default `Europe/Rome`).

## Gestione

| Azione | Telegram / CLI | API |
|---|---|---|
| Elenco | `/schedules` | `GET /v1/schedules` |
| Eliminazione | `/unschedule <id>` | `DELETE /v1/schedules/{id}` |

Nella CLI `/schedules` mostra anche l'ultimo risultato di ogni task.

## Limiti

| Limite | Default | Variabile |
|---|---|---|
| Intervallo minimo tra due esecuzioni | 30 minuti | `SCHEDULE_MIN_INTERVAL_MIN` |
| Task per utente | 10 | `MAX_SCHEDULES_PER_USER` |
| Lunghezza del prompt | 1.000 caratteri | — |

> [!IMPORTANT]
> Un task programmato **non può eseguire codice né produrre file**: non c'è nessuno per confermare. Gli agenti
> possono comunque salvare il codice e mostrartelo nel risultato.

## Consegna

| Creato da | Dove arriva l'esito |
|---|---|
| Telegram | Messaggio nella chat, con il prefisso `[Schedule #id]` |
| CLI, API | Nessuna notifica: si legge con `/schedules` (CLI) o `GET /v1/schedules` (`last_result`) |

## Funzionamento

- I task stanno nella tabella `picobot_schedules` di `data/picobot.db`.
- Li esegue solo il processo `picobot serve` (APScheduler). CLI e API scrivono soltanto nella tabella; il server la
  riallinea ogni 30 secondi.
- Ogni esecuzione usa una sessione nuova (`sched-<id>-<timestamp>`) ma lo stesso utente, quindi memoria e profilo
  valgono.
- Le esecuzioni mancate sono tollerate fino a 5 minuti (`misfire_grace_time`) e accorpate; una sola istanza per task
  alla volta.
