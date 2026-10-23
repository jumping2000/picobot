"""Logica condivisa dai canali (testo help, parsing /schedule, split messaggi)."""
HELP = (
    "Scrivimi una richiesta (domande, quotazioni, ricerche web, piccoli programmi Python).\n"
    "Invia un PDF/DOCX/TXT per ottenere un riassunto (nella didascalia puoi scrivere istruzioni).\n\n"
    "/new - nuova conversazione (la memoria a lungo termine resta)\n"
    "/memory - cosa so di te\n"
    "/forget - cancella la mia memoria su di te (con conferma)\n"
    "/schedule <cron> | <richiesta> - task ricorrente, es: /schedule 0 8 * * 1-5 | quotazioni AAPL e MSFT\n"
    "/schedules - elenco task schedulati\n"
    "/unschedule <id> - elimina un task\n"
    "/help - questo messaggio\n\n"
    "Il codice Python viene eseguito solo dopo la tua conferma."
)


def parse_schedule_args(arg: str) -> tuple[str, str]:
    """'0 8 * * 1-5 | quotazioni AAPL' -> ('0 8 * * 1-5', 'quotazioni AAPL')"""
    if "|" not in arg:
        raise ValueError("Formato: /schedule <min ora giorno mese giorno_sett> | <richiesta>")
    cron, prompt = arg.split("|", 1)
    return cron.strip(), prompt.strip()


def format_schedules(rows: list[dict]) -> str:
    if not rows:
        return "Nessun task schedulato."
    out = []
    for r in rows:
        last = f" | ultimo: {r['last_run'][:16]}" if r["last_run"] else ""
        out.append(f"#{r['id']} [{r['cron']}] {r['prompt'][:70]}{last}")
    return "\n".join(out)


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
