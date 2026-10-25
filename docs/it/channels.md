# Canali: Telegram e CLI

🇮🇹 Italiano · 🇬🇧 [English](../en/channels.md) · ⬅️ [Indice](index.md)

Per l'API REST vedi [api.md](api.md).

## Comandi

Disponibili su Telegram e nella CLI.

| Comando | Descrizione |
|---|---|
| `/help` (`/start`) | Elenco dei comandi |
| `/new` | Nuova conversazione (la memoria a lungo termine resta) |
| `/simple <richiesta>` | Invia direttamente allo SimpleTeam (quotazioni, ricerche, script) |
| `/complex <richiesta>` | Invia direttamente al ComplexTeam (documenti, compiti complessi) |
| `/riassumi [istruzioni]` | Riassunto diretto (Telegram: come didascalia di un documento o in risposta a un documento) |
| `/riassumi <link> [istruzioni]` | Riassunto diretto di una pagina web (articoli, blog) |
| `/memory` | Mostra memorie, profilo ed entità |
| `/forget` | Cancella memorie, profilo ed entità (chiede conferma) |
| `/schedule <cron> \| <richiesta>` | Crea un task ricorrente, es. `/schedule 0 8 * * 1-5 \| quotazioni AAPL e MSFT` |
| `/schedules` | Elenco dei tuoi task |
| `/unschedule <id>` | Elimina un task |
| `/skills` | Skill installate (sola lettura) |

Solo CLI:

| Comando | Descrizione |
|---|---|
| `/file <percorso> [richiesta]` | Usa un documento locale; decide il router (riassunto o altro) |
| `/riassumi <percorso> [istruzioni]` | Riassunto diretto di un documento locale |
| `/quit` (`/exit`) | Esci |

## Telegram

### Accesso

Vengono serviti solo gli id in `TELEGRAM_ALLOWED_USER_IDS`; gli altri utenti sono ignorati e registrati nel log
(`Accesso negato: user_id=...`). Per conoscere il tuo id scrivi a un bot come `@userinfobot`.

### Messaggi e sessioni

- Ogni chat ha il suo id di sessione, salvato in `data/telegram_state.pkl`; `/new` ne crea uno nuovo.
- Le richieste della stessa chat vengono elaborate una alla volta; nel frattempo compare "sta scrivendo…".
- Le risposte lunghe vengono divise in messaggi da 4.000 caratteri. Se Telegram rifiuta il Markdown, si ripiega
  sul testo semplice.

### Documenti

Formati supportati: **PDF, DOCX, TXT, MD, CSV, JSON, LOG**, fino a `MAX_UPLOAD_MB` (15 MB).

| Cosa invii | Cosa succede |
|---|---|
| Documento senza didascalia, o con didascalia "riassumi" | Il router chiama il workflow dei riassunti |
| Documento con una richiesta in didascalia (es. "fammi un PowerPoint da questo PDF") | Il router delega al ComplexTeam, che lo legge con `read_document` |
| Documento con didascalia `/riassumi [istruzioni]` | Riassunto diretto, senza router |
| `/riassumi [istruzioni]` in risposta a un documento inviato prima | Riassunto diretto di quel documento |

Il file viene scaricato in `data/inbox/` e **sempre cancellato** dopo l'elaborazione. Il riassunto entra nella
sessione, quindi puoi fare domande successive.

### Pagine web

`/riassumi <link> [istruzioni]` scarica la pagina e ne riassume il testo principale (senza menu, pubblicità e
piè di pagina), su Telegram, CLI e API. È pensato per articoli e blog: PDF online, pagine con login o paywall,
pagine riempite solo da JavaScript e video non sono supportati. Solo `http`/`https`, max 5 MB, timeout 20 s.
I link verso `localhost`, la rete privata o i metadata cloud sono rifiutati, anche dopo un redirect.
Senza proxy viene controllato anche l'IP a cui la connessione arriva davvero (contro il DNS rebinding): la risposta
di un host privato viene scartata senza leggerla, ma la richiesta GET gli arriva comunque. Con un
proxy (`HTTPS_PROXY`/`HTTP_PROXY`/`ALL_PROXY`, salvo `NO_PROXY`) il nome lo risolve il proxy: configuralo perché
neghi le destinazioni private. Il controllo preventivo risolve comunque i nomi dal container: se il container non
ha un DNS esterno e lo risolve solo il proxy, i link falliscono con "host … sconosciuto".

### Messaggi vocali

Le note vocali e i file audio (anche inviati come documento) vengono trascritti dal servizio `stt`: il bot scrive
prima `🎤 <trascrizione>`, poi risponde come se lo avessi scritto. Spento finché non imposti `STT_URL`: vedi
[voice.md](voice.md).

### Conferma del codice

Prima di ogni esecuzione PicoBot mostra il **codice completo** e due bottoni, **Conferma** e **Annulla**:

- il codice fino a 1.500 caratteri è mostrato nel messaggio; quello più lungo arriva prima come allegato
  (`codice.py` / `codice.js`);
- solo l'utente che ha fatto la richiesta può premere i bottoni;
- nessuna risposta entro `CONFIRM_TIMEOUT_S` (120 s) vale come **rifiuto**.

I file creati dagli agenti arrivano come documenti Telegram dopo la risposta.

## CLI

```bash
# Docker
docker compose exec -it picobot python -m picobot cli
# locale
uv run picobot cli
```

- L'id utente è `CLI_USER_ID` (default `cli`); usa il tuo id Telegram per condividere la memoria.
- Le conferme del codice sono un prompt `Eseguire? [y/N]` (`y`, `yes`, `s`, `si` = sì); timeout = rifiuto.
- I file consegnati sono indicati con il percorso (`File: /app/workspace/outputs/...`).
- `/schedule` scrive solo il task: lo esegue il processo `picobot serve`.

```text
> /file ~/relazione.pdf fammi una presentazione di 5 slide
> /riassumi ~/contratto.docx in 3 punti
> /simple cambio EUR/USD
```
