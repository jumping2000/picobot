# Memoria, profilo ed entità

🇮🇹 Italiano · 🇬🇧 [English](../en/memory.md) · ⬅️ [Indice](index.md)

PicoBot conserva tre tipi di conoscenza a lungo termine, tutti **privati per utente** e salvati in `data/picobot.db`.

| Tipo | Cosa | Esempio | Interruttore |
|---|---|---|---|
| **Memorie** | Fatti duraturi su di te | "sono un gestore di portafoglio" | `ENABLE_MEMORY` |
| **Profilo** | Preferenze strutturate | "rispondimi a punti", "seguo AAPL e ENI" | `ENABLE_LEARNING` |
| **Entità** | Progetti e persone ricorrenti | "lavoro al progetto Harbor con Sara" | `ENABLE_LEARNING` |

## Campi del profilo

| Campo | Significato | Esempio |
|---|---|---|
| `name`, `preferred_name` | Nome e come chiamarti | `Marco` |
| `lingua` | Lingua preferita per le risposte | `italiano` |
| `fuso_orario` | Fuso orario IANA | `Europe/Rome` |
| `formato_risposta` | Formato preferito delle risposte | `breve a punti` |
| `titoli_seguiti` | Ticker seguiti, separati da virgola | `AAPL, ENI.MI` |

Basta dirlo in conversazione: "seguo AAPL e ENI", "rispondimi sempre a punti". Poi "quotazione dei miei titoli"
usa i titoli salvati.

## Chi legge e chi scrive

- **Scrive solo il router** (modalità agentic: salva quando dichiari qualcosa, senza chiamate LLM in più).
- I leader di SimpleTeam e ComplexTeam e l'agente Finance leggono profilo ed entità **in sola lettura**.
- I team richiamati direttamente (`/simple`, `/complex`) non aggiornano il profilo.

## Visualizzare e cancellare

| Canale | Visualizza | Cancella tutto |
|---|---|---|
| Telegram | `/memory` | `/forget` + bottone di conferma |
| CLI | `/memory` | `/forget` + `y` |
| API | `GET /v1/memory` | `DELETE /v1/memory?confirm=true` |

`/forget` cancella memorie, profilo ed entità solo del **tuo** utente. Non cancella le sessioni di conversazione né
i task programmati: usa `/new` per una conversazione nuova e `/unschedule` per i task.

## Condivisione tra canali

La memoria è legata all'id utente:

| Canale | Id utente |
|---|---|
| Telegram | Il tuo id numerico Telegram |
| CLI | `CLI_USER_ID` |
| API | Lo `user_id` associato al token in `API_TOKENS` |

Usa lo stesso valore (il tuo id Telegram) ovunque per avere un unico profilo.

## Costi

I tool di profilo ed entità aggiungono circa 1.100 token a ogni chiamata del router. Imposta
`ENABLE_LEARNING=false` per risparmiarli, o `ENABLE_MEMORY=false` per disattivare le memorie.
`ENABLE_SESSION_SUMMARIES=true` aggiunge i riassunti di sessione al prezzo di una chiamata LLM in più per run.
