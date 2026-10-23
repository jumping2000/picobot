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

## Managing

| Action | Telegram / CLI | API |
|---|---|---|
| List | `/schedules` | `GET /v1/schedules` |
| Delete | `/unschedule <id>` | `DELETE /v1/schedules/{id}` |

In the CLI, `/schedules` also prints the last result of each task.

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
| CLI, API | Not pushed: read it with `/schedules` (CLI) or `GET /v1/schedules` (`last_result`) |

## How it works

- Tasks live in the `picobot_schedules` table of `data/picobot.db`.
- Only the `picobot serve` process executes them (APScheduler). The CLI and the API just write to the table; the
  server re-syncs it every 30 seconds.
- Each run uses a new session (`sched-<id>-<timestamp>`) but the same user, so memory and profile apply.
- Missed runs are tolerated for up to 5 minutes (`misfire_grace_time`) and coalesced; one instance per task at a time.
