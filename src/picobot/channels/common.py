"""Logica condivisa dai canali (testo help, parsing /schedule, split messaggi)."""
from ..config import Settings
from ..scheduler import format_schedules  # noqa: F401  (re-export per i canali)
from ..trace import format_trace, last_trace

HELP = (
    "Scrivimi una richiesta (domande, quotazioni, ricerche web, programmi Python, documenti Word/PowerPoint/Excel).\n"
    "Invia un PDF/DOCX/TXT: lo riassumo, oppure scrivi nella didascalia cosa farne.\n"
    "Invia un messaggio vocale o un file audio: lo trascrivo e lo eseguo come un messaggio scritto.\n\n"
    "/simple <richiesta> - usa direttamente il SimpleTeam (quotazioni, ricerche, script)\n"
    "/complex <richiesta> - usa direttamente il ComplexTeam (documenti, compiti complessi)\n"
    "/riassumi [istruzioni] - riassunto diretto: come didascalia di un documento o in risposta a un documento\n"
    "/riassumi <link> [istruzioni] - riassunto di una pagina web (articoli, blog)\n"
    "/new - nuova conversazione (la memoria a lungo termine resta)\n"
    "/memory - cosa so di te\n"
    "/forget - cancella la mia memoria su di te (con conferma)\n"
    "/schedule <cron> | <richiesta> - task ricorrente, es: /schedule 0 8 * * 1-5 | quotazioni AAPL e MSFT\n"
    "/schedules - elenco task schedulati\n"
    "/unschedule <id> - elimina un task\n"
    "/skills - skill installate (le gestisce l'amministratore)\n"
    "/trace - percorso dell'ultima richiesta (se TRACE_ENABLED=true)\n"
    "/help - questo messaggio\n\n"
    "Il codice Python viene eseguito solo dopo la tua conferma."
)


def parse_schedule_args(arg: str) -> tuple[str, str]:
    """'0 8 * * 1-5 | quotazioni AAPL' -> ('0 8 * * 1-5', 'quotazioni AAPL')"""
    if "|" not in arg:
        raise ValueError("Formato: /schedule <min ora giorno mese giorno_sett> | <richiesta>")
    cron, prompt = arg.split("|", 1)
    return cron.strip(), prompt.strip()


def trace_text(s: Settings, user_id: str) -> str:
    """Testo di /trace: percorso dell'ultima richiesta dell'utente."""
    if not s.trace_enabled:
        return "Traccia disattivata: imposta TRACE_ENABLED=true nel file .env e riavvia."
    rec = last_trace(s, user_id)
    return format_trace(rec) if rec else "Nessuna richiesta tracciata."


def split_text(text: str, limit: int = 4000) -> list[str]:
    parts, text = [], text.strip()
    while len(text) > limit:
        cut = max(text.rfind("\n\n", 0, limit), text.rfind("\n", 0, limit), text.rfind(" ", 0, limit))
        cut = cut if cut > limit // 2 else limit
        parts.append(text[:cut].rstrip())
        text = text[cut:].lstrip()
    if text:
        parts.append(text)
    return parts or ["(risposta vuota)"]


def format_memory_report(r) -> str:
    """Testo di /memory: memorie, profilo ed entita'."""
    parts = []
    if r.memories:
        parts.append("Memorie:\n" + "\n".join(f"- {m}" for m in r.memories))
    if r.profile:
        parts.append("Profilo:\n" + "\n".join(f"- {k.replace('_', ' ')}: {v}" for k, v in r.profile.items()))
    if r.entities:
        parts.append("Entita':\n" + "\n".join(f"- {n} ({t}): {d}" if d else f"- {n} ({t})" for n, t, d in r.entities))
    return "\n\n".join(parts) if parts else "Non ho memorie su di te."
