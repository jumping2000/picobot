# Memory, profile and entities

🇬🇧 English · 🇮🇹 [Italiano](../it/memory.md) · ⬅️ [Index](index.md)

PicoBot keeps three kinds of long-term knowledge, all **private per user** and stored in `data/picobot.db`.

| Kind | What | Example | Switch |
|---|---|---|---|
| **Memories** | Durable facts about you | "I'm a portfolio manager" | `ENABLE_MEMORY` |
| **Profile** | Structured preferences | "answer in bullet points", "I follow AAPL and ENI" | `ENABLE_LEARNING` |
| **Entities** | Recurring projects and people | "I work on project Harbor with Sara" | `ENABLE_LEARNING` |

## Profile fields

| Field | Meaning | Example |
|---|---|---|
| `name`, `preferred_name` | Name and how to address you | `Marco` |
| `lingua` | Preferred answer language | `English` |
| `fuso_orario` | IANA time zone | `Europe/Rome` |
| `formato_risposta` | Preferred answer format | `short, bullet points` |
| `titoli_seguiti` | Followed tickers, comma-separated | `AAPL, ENI.MI` |

Just say it in conversation: "I follow AAPL and ENI", "always answer in bullet points". Later, "quotes of my
stocks" uses the saved tickers.

## Who reads and writes

- **Only the router writes** (agentic mode: it saves when you state something, without extra LLM calls).
- SimpleTeam and ComplexTeam leaders and the Finance agent read the profile and entities **read-only**.
- Teams called directly (`/simple`, `/complex`) do not update the profile.

## Viewing and deleting

| Channel | View | Delete everything |
|---|---|---|
| Telegram | `/memory` | `/forget` + confirm button |
| CLI | `/memory` | `/forget` + `y` |
| API | `GET /v1/memory` | `DELETE /v1/memory?confirm=true` |

`/forget` deletes memories, profile and entities of **your** user only. It does not delete conversation sessions
or scheduled tasks; use `/new` for a fresh conversation and `/unschedule` for tasks.

## Sharing across channels

Memory is keyed by user ID:

| Channel | User ID |
|---|---|
| Telegram | Your numeric Telegram ID |
| CLI | `CLI_USER_ID` |
| API | The `user_id` paired with the token in `API_TOKENS` |

Use the same value (your Telegram ID) everywhere to have one profile.

## Cost

Profile and entity tools add about 1,100 tokens to every router call. Set `ENABLE_LEARNING=false` to save them, or
`ENABLE_MEMORY=false` to disable memories. `ENABLE_SESSION_SUMMARIES=true` adds session summaries at the price of
one extra LLM call per run.
