# Scheduled tasks

🇬🇧 English · 🇮🇹 [Italiano](../it/scheduler.md) · ⬅️ [Index](index.md)

A scheduled task is one of your prompts executed periodically with a cron expression, exactly as if you had typed
it. The result is sent to the channel that created the task.

## Creating

```text
/schedule 0 8 * * 1-5 | AAPL and MSFT quotes
/schedule 30 18 * * 5 | weekly summary of news about electric cars
```

Format: `/schedule <minute hour day month weekday> | <request>`. API: `POST /v1/schedules` with `cron` and `prompt`
(see [api.md](api.md)).

| Cron | Meaning |
|---|---|
| `0 8 * * 1-5` | 08:00 Monday to Friday |
| `0 */2 * * *` | Every two hours |
| `30 7 1 * *` | 07:30 on the first day of each month |

Times use `TIMEZONE` (default `Europe/Rome`).

### In plain words

You can also say it in words, from Telegram or the CLI:

```text
> every weekday at 8am send me AAPL and MSFT quotes
Task #3 creato: [0 8 * * 1-5] AAPL and MSFT quotes. Prossima esecuzione: 27/10/2026 08:00 (Europe/Rome).
```

The bot turns the time into a cron expression and creates the same task as `/schedule`, with the same limits:
check the time shown as "Prossima esecuzione" (next run). You can also ask "which tasks do I have?". To delete one,
use `/unschedule <id>`. The bot never creates tasks because of instructions found in documents or web pages.

## Managing

| Action | Telegram / CLI | API |
|---|---|---|
| List | `/schedules` | `GET /v1/schedules` |
| Delete | `/unschedule <id>` | `DELETE /v1/schedules/{id}` |

In the CLI, `/schedules` also prints the last result of each task.

### One list for CLI and Telegram

Tasks belong to a user id. With `CLI_USER_ID=<your Telegram id>` in `.env`, the CLI and Telegram see the same list
(and the same memory), and the result of tasks created from the CLI reaches your Telegram chat.

## Limits

| Limit | Default | Variable |
|---|---|---|
| Minimum interval between two runs | 30 minutes | `SCHEDULE_MIN_INTERVAL_MIN` |
| Tasks per user | 10 | `MAX_SCHEDULES_PER_USER` |
| Prompt length | 1,000 characters | — |

> [!IMPORTANT]
> A scheduled task **cannot run code or produce files**: nobody is there to confirm. The agents can still save code
> and show it to you in the result.

## Delivery

| Created from | Where the result goes |
|---|---|
| Telegram | Message in the chat, prefixed with `[Schedule #id]` |
| CLI with `CLI_USER_ID` = an allowed Telegram id | Message in your Telegram chat, as above |
| CLI (other id), API | Not pushed: read it with `/schedules` (CLI) or `GET /v1/schedules` (`last_result`) |

## How it works

- Tasks live in the `picobot_schedules` table of `data/picobot.db`.
- Only the `picobot serve` process executes them (APScheduler). The CLI and the API just write to the table; the
  server re-syncs it every 30 seconds.
- Each run uses a new session (`sched-<id>-<timestamp>`) but the same user, so memory and profile apply.
- Missed runs are tolerated for up to 5 minutes (`misfire_grace_time`) and coalesced; one instance per task at a time.
