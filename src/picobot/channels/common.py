"""Logica condivisa dai canali (testo help, parsing /schedule, split messaggi, skill da chat)."""
import asyncio
import errno
import logging
import re
from collections.abc import Awaitable, Callable
from urllib.parse import urlsplit

from .. import skills_cli
from ..config import Settings
from ..scheduler import format_schedules  # noqa: F401  (re-export per i canali)
from ..skills import SkillInfo
from ..trace import format_trace, last_trace

logger = logging.getLogger(__name__)

SKILL_ADMIN_ONLY = "Solo un amministratore può installare o rimuovere skill."
SKILL_ADMIN_OFF = SKILL_ADMIN_ONLY + " Comandi disattivati: imposta ADMIN_USER_IDS in .env."
SKILL_DIR_READONLY = ("Non posso scrivere nella cartella delle skill. Sull'host: sudo chown -R 1000 skills e, "
                      "se serve, togli :ro dal mount di ./skills nel compose.")
_READONLY_ERRNOS = {errno.EACCES, errno.EPERM, errno.EROFS}
_LOG_CTRL = re.compile(r"[\x00-\x1f\x7f-\x9f\u2028\u2029]")
_LOG_USERINFO = re.compile(r"(?<=://)[^/?#@\s]+@")


def _log_safe(text: str) -> str:
    """Per il log: niente credenziali negli URL e caratteri di controllo visibili (niente righe di log false)."""
    return _LOG_CTRL.sub(lambda m: m.group().encode("unicode_escape").decode("ascii"), _LOG_USERINFO.sub("", text))


def _log_source(source: str) -> str:
    """Sorgente per il log: di un URL solo schema://host[:porta]/percorso (niente utente, query e frammento)."""
    s = source.strip()
    if "://" in s:
        try:
            p = urlsplit(s)
            s = f"{p.scheme}://{p.netloc.rpartition('@')[2]}{p.path}"
        except ValueError:   # URL malformato (es. IPv6 non chiuso): si tagliano comunque query e frammento
            s = re.split(r"[?#]", s, maxsplit=1)[0]
    return _log_safe(s)

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


def skill_installed_text(info: SkillInfo, deps: dict[str, list[str]]) -> str:
    """Esito di /skill_add: stesso contenuto di skills_cli._print_info, adattato alla chat."""
    lines = [f"Installata: {info.name}", info.description, f"File: {info.files}"]
    if any(deps.values()):
        lines.append("Dipendenze dichiarate: sull'host aggiungile con `picobot skills deps --write` "
                     "e ricostruisci l'immagine.")
        lines += [f"- {kind}: {', '.join(deps[kind])}" for kind in skills_cli.KINDS if deps[kind]]
    if info.has_scripts:
        lines.append("Attenzione: contiene scripts/. Il bot non li esegue direttamente: l'Analyst puo' usarli "
                     "come riferimento e ogni esecuzione di codice richiede la tua conferma.")
    return "\n".join(lines)


def _skill_error_text(e: Exception, generic: str) -> str:
    # permessi della cartella: diretti o come causa di una SkillInstallError
    if any(isinstance(x, OSError) and x.errno in _READONLY_ERRNOS for x in (e, e.__cause__)):
        return SKILL_DIR_READONLY
    if isinstance(e, skills_cli.SkillInstallError):
        return str(e)
    logger.exception(generic)
    return generic


async def add_skill_flow(service, source: str, *, allow_local: bool, ask: Callable[[str], Awaitable[bool]],
                         user: str, channel: str) -> str:
    """Installa una skill da chat (solo admin: lo controlla il canale). Ritorna sempre il testo, non solleva."""
    try:
        async with service.fetched_skill(source, allow_local=allow_local) as path:
            try:
                info = await service.install_skill(path, force=False)
            except skills_cli.SkillExistsError as e:
                existing = e.name
                # stessa copia locale per il secondo tentativo: niente doppio download
                ok = await ask(f"La skill '{existing}' è già installata. Sostituirla?")
                info = await service.install_skill(path, force=True) if ok else None
        if info is None:
            text, outcome = f"Skill '{existing}' non sostituita.", f"non sostituita {existing}"
        else:
            deps = await asyncio.to_thread(skills_cli._skill_deps, service.s.skills_dir / info.name)
            text, outcome = skill_installed_text(info, deps), f"installata {info.name}"
    except Exception as e:  # noqa: BLE001  il canale riceve sempre un testo
        text = _skill_error_text(e, "Installazione fallita.")
        outcome = f"errore: {text}"
    logger.info("skill_add utente=%s canale=%s sorgente=%s esito=%s", _log_safe(str(user)), channel,
                _log_source(source), _log_safe(outcome))
    return text


async def remove_skill_flow(service, name: str, *, user: str, channel: str) -> str:
    """Rimuove una skill da chat (solo admin: lo controlla il canale). Ritorna sempre il testo, non solleva."""
    name = name.strip()
    try:
        await service.remove_skill(name)
        text, outcome = f"Rimossa: {name}", "rimossa"
    except Exception as e:  # noqa: BLE001
        text = _skill_error_text(e, "Rimozione fallita.")
        outcome = f"errore: {text}"
    logger.info("skill_remove utente=%s canale=%s nome=%s esito=%s", _log_safe(str(user)), channel,
                _log_safe(name), _log_safe(outcome))
    return text
