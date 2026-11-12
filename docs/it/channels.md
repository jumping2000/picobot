# Canali: Telegram, email e CLI

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
| `/schedule <cron> \| <richiesta> [\| codice]` | Crea un task ricorrente, es. `/schedule 0 8 * * 1-5 \| quotazioni AAPL e MSFT`; con `\| codice` può eseguire codice (conferma una tantum) |
| `/schedules` | Elenco dei tuoi task |
| `/unschedule <id>` | Elimina un task |
| `/skills` | Skill installate |
| `/skill_add <link>` | Installa una skill da un URL `https://` (zip o repository git); solo amministratori. Su Telegram anche un allegato `.zip` con didascalia `/skill_add`; nella CLI anche un percorso locale. Vedi [skills.md](skills.md#da-telegram-e-dalla-chat-cli) |
| `/skill_remove <nome>` | Rimuove una skill; solo amministratori |
| `/trace` | Percorso dell'ultima richiesta: team, agenti, tool ed esiti (con `TRACE_ENABLED=true`) |

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
- Le risposte sono formattate secondo `telegram.reply_format` (vedi configuration.md); le tabelle diventano un blocco
  a larghezza fissa. Le risposte lunghe vengono divise in più messaggi senza spezzare la formattazione. Se Telegram
  rifiuta un messaggio formattato, si ripiega sul testo semplice.

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

## Email

PicoBot può avere una casella [AgentMail](https://docs.agentmail.to/): chi è in un elenco di indirizzi ammessi le
scrive e riceve la risposta nello stesso thread, come per un messaggio Telegram. La casella viene letta a
**polling**, non in modo istantaneo.

### Configurazione

- `.env`: `AGENTMAIL_API_KEY` e `EMAIL_ALLOWED_SENDERS` (`indirizzo[:user_id]` separati da virgola).
- `config/config.yaml`: `email.inbox_id` (l'indirizzo della casella) e `email.poll_interval_s` (default 60).
- Il canale parte solo con la chiave **e** `inbox_id`; `picobot serve --no-email` lo spegne. L'email può essere
  l'unico canale. Senza configurazione email PicoBot funziona come prima.

Dettagli in [configuration.md](configuration.md).

### Mittenti ammessi

Vengono serviti solo gli indirizzi in `EMAIL_ALLOWED_SENDERS`; il confronto non distingue le maiuscole né guarda il
nome visualizzato. Una mail di chiunque altro non riceve risposta, non arriva agli agenti e nel log compare solo il
mittente. Elenco vuoto = nessuno può scrivere (l'invio di mail resta possibile).

Una voce si collega a un utente esistente con `indirizzo:id`, per esempio
`io@jumpi.top:123456789,collega@esempio.it`. Con `:id` lo user_id è quell'id (di solito il tuo id Telegram, lo
stesso di `CLI_USER_ID`): memoria, profilo e schedule sono condivisi tra i canali. Senza `:id` lo user_id è
l'indirizzo in minuscolo.

### Cosa succede a una mail

1. Ogni `email.poll_interval_s` secondi si legge la casella; le mail si elaborano **una alla volta**, in ordine di arrivo.
2. La richiesta è `oggetto + corpo`, che va al router come un messaggio Telegram.
3. La risposta torna nello stesso thread, con allegati i file creati dagli agenti.
4. Si ignorano, senza rispondere: le mail di PicoBot stesso, le risposte automatiche (`Auto-Submitted`, fuori sede)
   e le immagini inline come le firme.

**Sessione per thread.** Ogni thread email è una sessione (`mail-<thread>-<hash del mittente>`): una risposta come
"aggiungi anche novembre" ha il contesto dello scambio. Vale anche quando il thread l'ha aperto PicoBot
(`send_email` o la notifica di uno schedule): la mail inviata viene registrata nella sessione del destinatario, se è
un mittente ammesso. La memoria a lungo termine segue lo user_id, come sugli altri canali.

**Mail già viste.** Gli id elaborati stanno nella tabella `picobot_email_seen` di `picobot.db` (30 giorni). Al primo
avvio il passato non si elabora, solo la posta che arriva dopo. Una mail è segnata come vista appena elaborata e
**prima** di inviare la risposta: se l'invio fallisce (rete, limite del piano) la richiesta non si rifà e la mail
resta senza risposta (vedi il log). Un crash durante l'elaborazione ripete quella mail al riavvio.

**Errori.** Un `DocumentError` riceve il suo messaggio, ogni altra eccezione "Errore interno durante
l'elaborazione. Riprova tra poco."; se AgentMail non risponde il giro viene saltato e riprovato.

### Allegati

Trattati come i documenti inviati su Telegram: **PDF, DOCX, TXT, MD, CSV, JSON, LOG** fino a `MAX_UPLOAD_MB`.

- Il **primo** allegato supportato ed entro il limite viene scaricato in `data/inbox/` e il prompt diventa
  `[Documento caricato: nome] <testo>`; il file viene **sempre cancellato** a fine elaborazione.
- Gli altri (formato non supportato, troppo grandi, o successivi al primo) sono elencati in coda alla risposta come ignorati.
- Se l'oggetto o la prima riga del corpo inizia con `/riassumi [istruzioni]`, l'allegato riceve un riassunto diretto,
  come su Telegram. Gli altri comandi (`/new`, `/schedules`, ...) via email non esistono: scrivi a parole.
- La risposta porta i file creati dagli agenti. AgentMail accetta al massimo **6 MB per mail** (allegati contati in
  base64): oltre, la risposta parte senza allegati e lo dice ("Allegati oltre 6 MB: non inviati.").

### Codice

Via email nessuno può confermare, quindi la mail è pre-approvata: con `code.allow_code: true` (default) un mittente
ammesso può far eseguire codice nella sandbox **senza conferma**; con `false` nessun codice gira. Vedi
[security.md](security.md): tieni corto l'elenco dei mittenti.

### Schedule

Uno schedule creato da una mail (`channel: email`) consegna l'esito con una **mail nuova** all'indirizzo che l'ha
creato, con oggetto `[Schedule #id] <prompt>`; rispondendo si continua la conversazione con il suo contesto. Gli
schedule si creano, elencano ed eliminano a parole (gli agenti hanno i tool), non con `/schedule`.

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
