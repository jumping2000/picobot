"""Tool di invio email del router e dei membri che consegnano file. Solo da outputs/, con gli stessi controlli di deliver_file."""
import logging
from collections.abc import Awaitable, Callable

from ..config import Settings
from ..context import get_ctx
from ..mailbox import MailTooLarge, Mailbox, bare_address
from .files import _Refused, _validate

logger = logging.getLogger("picobot.email")

# (thread_id, indirizzo, oggetto, corpo, nomi dei file)
RecordFn = Callable[[str, str, str, str, list[str]], Awaitable[None]]


def make_email_tools(s: Settings, mailbox: Mailbox, record: RecordFn) -> list:
    async def send_email(to: list[str], subject: str, body: str, attachments: list[str] = []) -> str:  # noqa: B006  mai modificata (non `files`: Agno lo riserva ai media)
        """Invia un'email dalla casella di PicoBot, solo se l'utente lo chiede. Il corpo e' Markdown.
        Gli eventuali file vanno prima creati e consegnati, poi indicati come outputs/<nome>.

        Args:
            to: uno o piu' indirizzi email destinatari
            subject: oggetto dell'email
            body: testo dell'email in Markdown
            attachments: percorsi dei file da allegare, es. ["outputs/relazione.docx"]; opzionale, max 6 MB in tutto
        """
        if get_ctx() is None:
            return "Rifiutato: nessuna richiesta attiva da cui inviare."
        recipients = [a.strip() for a in to or [] if a and a.strip()]
        if not recipients or any("@" not in bare_address(a) for a in recipients):
            return "Rifiutato: serve almeno un indirizzo email valido."
        try:
            paths = [_validate(s, f) for f in attachments or []]
        except _Refused as e:
            return f"Rifiutato: {e}."
        try:
            thread_id = await mailbox.send(recipients, subject, body, paths)
        except MailTooLarge:
            return "Rifiutato: l'email supera il limite di 6 MB (allegati inclusi); allega meno file o file piu' piccoli."
        except Exception:  # noqa: BLE001  l'esito arriva all'agente come testo, i dettagli restano nel log
            logger.exception("Invio email fallito")
            return "Errore: invio email non riuscito."
        names = [p.name for p in paths]
        for a in recipients:
            try:
                await record(thread_id, bare_address(a), subject, body, names)
            except Exception:  # noqa: BLE001  l'invio e' riuscito comunque
                logger.exception("Impossibile registrare l'email inviata (thread %s)", thread_id)
        return f"Inviata a {', '.join(recipients)}."

    return [send_email]
