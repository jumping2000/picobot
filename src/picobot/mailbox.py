"""Casella AgentMail: unico modulo che conosce l'SDK. Il resto di PicoBot vede solo InMail e Mailbox.

Nei log: mittente e id messaggio si', oggetto, corpo e chiave API mai.
"""
import base64
import hashlib
import logging
import mimetypes
from dataclasses import dataclass, field
from datetime import datetime
from email.utils import parseaddr
from pathlib import Path

import httpx
from agentmail import AsyncAgentMail
from markdown_it import MarkdownIt

from .config import Settings

logger = logging.getLogger("picobot.mailbox")

MAX_SEND_BYTES = 6 * 1024 * 1024        # limite AgentMail per richiesta (corpo + allegati in base64)
_MARGIN = 64 * 1024                     # corpo e metadati
_PAGE = 100


class MailTooLarge(Exception):
    pass


@dataclass
class InAttachment:
    attachment_id: str
    filename: str
    size: int
    inline: bool


@dataclass
class InMail:
    message_id: str
    thread_id: str
    sender: str                         # indirizzo nudo, minuscolo
    subject: str
    text: str
    timestamp: datetime
    attachments: list[InAttachment] = field(default_factory=list)
    auto_reply: bool = False


def bare_address(addr: str) -> str:
    """'Mario <MARIO@Esempio.it>' -> 'mario@esempio.it'."""
    return parseaddr(addr or "")[1].strip().lower()


def session_for(thread_id: str, address: str) -> str:
    """Sessione di un thread per mittente: due mittenti nello stesso thread non si mescolano."""
    return f"mail-{thread_id}-{hashlib.sha1(address.lower().encode('utf-8')).hexdigest()[:8]}"


def _to_in_mail(m) -> InMail:
    headers = {str(k).lower(): str(v) for k, v in (getattr(m, "headers", None) or {}).items()}
    auto = headers.get("auto-submitted")
    atts = [InAttachment(a.attachment_id, a.filename or "", a.size or 0, a.content_disposition == "inline")
            for a in (getattr(m, "attachments", None) or [])]
    return InMail(
        message_id=m.message_id, thread_id=m.thread_id, sender=bare_address(m.from_), subject=m.subject or "",
        text=getattr(m, "extracted_text", None) or getattr(m, "text", None) or "", timestamp=m.timestamp,
        attachments=atts, auto_reply=auto is not None and auto.strip().lower() != "no",
    )


def _payload(body_md: str, files: list[Path]) -> dict:
    """Corpo + allegati base64; MailTooLarge prima di leggere i file se la somma supera il limite."""
    total = _MARGIN + sum((f.stat().st_size + 2) // 3 * 4 for f in files)
    if total > MAX_SEND_BYTES:
        raise MailTooLarge(f"{total} byte > {MAX_SEND_BYTES}")
    return {
        "text": body_md,
        "html": MarkdownIt().render(body_md),
        "attachments": [
            {"content": base64.b64encode(f.read_bytes()).decode("ascii"), "filename": f.name,
             "content_type": mimetypes.guess_type(f.name)[0] or "application/octet-stream"}
            for f in files
        ] or None,
    }


class Mailbox:
    def __init__(self, s: Settings, client=None):
        self.s = s
        self._client = client or AsyncAgentMail(api_key=s.agentmail_api_key)
        self.address = s.inbox_id.lower()

    @property
    def _messages(self):
        return self._client.inboxes.messages

    async def list_since(self, after: datetime | None) -> list[InMail]:
        """Messaggi ricevuti dopo `after`, in ordine crescente, tutte le pagine, con testo completo."""
        items, token = [], None
        while True:
            kw = dict(inbox_id=self.s.inbox_id, limit=_PAGE, ascending=True, include_spam=False,
                      include_blocked=False, include_unauthenticated=False)
            if after is not None:
                kw["after"] = after
            if token:
                kw["page_token"] = token
            page = await self._messages.list(**kw)
            items += page.messages or []
            token = page.next_page_token
            if not token:
                break
        # l'elenco non porta il testo: messaggio completo per ognuno
        mails = [_to_in_mail(await self._messages.get(inbox_id=self.s.inbox_id, message_id=i.message_id))
                 for i in items]
        mails.sort(key=lambda m: m.timestamp)
        return mails

    async def send(self, to: list[str], subject: str, body_md: str, files: list[Path]) -> str:
        r = await self._messages.send(inbox_id=self.s.inbox_id, to=to, subject=subject, **_payload(body_md, files))
        logger.info("Email inviata (thread %s, messaggio %s).", r.thread_id, r.message_id)
        return r.thread_id

    async def reply(self, message_id: str, body_md: str, files: list[Path]) -> None:
        await self._messages.reply(inbox_id=self.s.inbox_id, message_id=message_id, **_payload(body_md, files))
        logger.info("Risposta inviata al messaggio %s.", message_id)

    async def download(self, message_id: str, attachment_id: str, dest: Path) -> None:
        att = await self._messages.get_attachment(inbox_id=self.s.inbox_id, message_id=message_id,
                                                  attachment_id=attachment_id)
        async with httpx.AsyncClient(timeout=60, follow_redirects=True) as http:
            r = await http.get(att.download_url)
            r.raise_for_status()
        dest.write_bytes(r.content)
