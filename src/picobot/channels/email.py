"""Canale email (AgentMail) a polling: mittenti ammessi, mail gia' viste in SQLite, risposta nello stesso thread.

Nei log: mittente e id messaggio si', oggetto, corpo e chiave API mai.
"""
import asyncio
import logging
import sqlite3
import time
import uuid
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from ..config import Settings
from ..context import RunCtx
from ..documents import SUPPORTED, DocumentError
from ..mailbox import InAttachment, InMail, MailTooLarge, Mailbox, session_for
from ..service import PicoBotService

logger = logging.getLogger(__name__)

SQL_CREATE = "CREATE TABLE IF NOT EXISTS picobot_email_seen(message_id TEXT PRIMARY KEY, ts REAL)"
SQL_MAX = "SELECT MAX(ts) FROM picobot_email_seen"
SQL_KNOWN = "SELECT 1 FROM picobot_email_seen WHERE message_id=?"
SQL_MARK = "INSERT OR IGNORE INTO picobot_email_seen VALUES(?,?)"
SQL_PURGE = "DELETE FROM picobot_email_seen WHERE ts<? AND ts<(SELECT MAX(ts) FROM picobot_email_seen)"
OVERLAP_S, KEEP_S = 300, 30 * 24 * 3600   # margine su orologi e ordine; conservazione delle righe
ERROR_TEXT = "Errore interno durante l'elaborazione. Riprova tra poco."
TOO_LARGE_NOTE = "Allegati oltre 6 MB: non inviati."


def _riassumi(m: InMail) -> str | None:
    """Istruzione se l'oggetto o la prima riga del corpo inizia con /riassumi, altrimenti None."""
    body = next((ln.strip() for ln in m.text.splitlines() if ln.strip()), "")
    for line in (m.subject.strip(), body):
        if line.lower().startswith("/riassumi"):
            return line[len("/riassumi"):].strip()
    return None


class EmailChannel:
    def __init__(self, s: Settings, service: PicoBotService, mailbox: Mailbox):
        self.s, self.service, self.mailbox = s, service, mailbox

    # -- mail gia' viste ---------------------------------------------------------------
    def _db(self) -> sqlite3.Connection:
        self.s.data_dir.mkdir(parents=True, exist_ok=True)
        c = sqlite3.connect(self.s.database_file, timeout=10)
        c.execute(SQL_CREATE)
        return c

    def _max_ts(self) -> float | None:
        with closing(self._db()) as c:
            return c.execute(SQL_MAX).fetchone()[0]

    def _is_seen(self, message_id: str) -> bool:
        with closing(self._db()) as c:
            return c.execute(SQL_KNOWN, (message_id,)).fetchone() is not None

    def _mark(self, message_id: str, ts: float) -> None:
        with closing(self._db()) as c, c:
            c.execute(SQL_MARK, (message_id, ts))

    def _purge(self) -> None:
        with closing(self._db()) as c, c:
            c.execute(SQL_PURGE, (time.time() - KEEP_S,))

    # -- ciclo ----------------------------------------------------------------------------
    async def run(self, stop: asyncio.Event) -> None:
        if not self.s.email_sender_map:
            logger.warning("EMAIL_ALLOWED_SENDERS e' vuoto: nessun mittente e' ammesso, tutta la posta in arrivo verra' ignorata.")
        while not stop.is_set():
            try:
                await self.poll_once()
            except Exception:  # noqa: BLE001  il canale non muore per un giro andato male
                logger.exception("Giro di polling email fallito")
            try:
                await asyncio.wait_for(stop.wait(), self.s.poll_interval_s)
            except TimeoutError:
                pass

    async def poll_once(self) -> None:
        last = self._max_ts()
        if last is None:   # primo avvio: si parte da adesso, la posta vecchia non si elabora
            self._mark("_start", time.time())
            return
        try:
            mails = await self.mailbox.list_since(datetime.fromtimestamp(last - OVERLAP_S, tz=timezone.utc))
        except Exception as e:  # noqa: BLE001  un messaggio illeggibile blocca il giro: si riprova al prossimo
            logger.warning("Lettura della casella email fallita, riprovo al prossimo giro: %s", e)
            return
        for m in mails:
            if not self._is_seen(m.message_id):
                await self._handle(m)
        self._purge()

    async def _handle(self, m: InMail) -> None:
        ts = min(m.timestamp.timestamp(), time.time())   # data nel futuro (mittente ostile): non sposta il watermark
        if m.sender == self.mailbox.address or m.auto_reply:
            return self._mark(m.message_id, ts)
        if m.sender not in self.s.email_sender_map:
            logger.info("Email ignorata: mittente %s non ammesso (messaggio %s)", m.sender, m.message_id)
            return self._mark(m.message_id, ts)
        logger.info("Email da %s (messaggio %s, %d allegati)", m.sender, m.message_id, len(m.attachments))
        text, files = await self._answer(m)
        self._mark(m.message_id, ts)   # prima dell'invio: se l'invio fallisce la richiesta non si rifa'
        try:
            try:
                await self.mailbox.reply(m.message_id, text, files)
            except MailTooLarge:
                await self.mailbox.reply(m.message_id, f"{text}\n\n{TOO_LARGE_NOTE}", [])
        except Exception:  # noqa: BLE001
            logger.exception("Risposta al messaggio %s non inviata", m.message_id)

    # -- elaborazione -----------------------------------------------------------------------
    def _pick(self, attachments: list[InAttachment]) -> tuple[InAttachment | None, list[str]]:
        """Primo allegato non inline supportato ed entro il limite; i nomi degli altri sono 'ignorati'."""
        limit, chosen, ignored = self.s.max_upload_mb * 1024 * 1024, None, []
        for a in attachments:
            if a.inline:
                continue
            if chosen is None and Path(a.filename).suffix.lower() in SUPPORTED and a.size <= limit:
                chosen = a
            else:
                ignored.append(a.filename or "allegato")
        return chosen, ignored

    async def _answer(self, m: InMail) -> tuple[str, list]:
        """(testo, file) della risposta; gli errori diventano testo, il documento scaricato si cancella sempre."""
        uid, sid = self.s.email_user_id(m.sender), session_for(m.thread_id, m.sender)
        chosen, ignored = self._pick(m.attachments)
        note = f"\n\nAllegati ignorati: {', '.join(ignored)}." if ignored else ""
        path = None
        try:
            text = f"{m.subject}\n\n{m.text}".strip()
            ctx = RunCtx(user_id=uid, channel="email", target=m.sender, pre_approved=True)
            if chosen:
                inbox = self.s.data_dir / "inbox"
                inbox.mkdir(parents=True, exist_ok=True)
                path = inbox / f"{uuid.uuid4().hex}{Path(chosen.filename).suffix.lower()}"
                await self.mailbox.download(m.message_id, chosen.attachment_id, path)
                instruction = _riassumi(m)
                if instruction is not None:
                    summary = await self.service.summarize(path, instruction, user_id=uid, name=chosen.filename,
                                                           session_id=sid)
                    return summary + note, []
                ctx.document, ctx.document_name = path, chosen.filename
                text = f"[Documento caricato: {chosen.filename}] {text}".strip()
            reply = await self.service.ask(text, user_id=uid, session_id=sid, ctx=ctx)
            return reply.text + note, [f.path for f in reply.files]
        except DocumentError as e:
            return str(e), []
        except Exception:  # noqa: BLE001
            logger.exception("Errore nell'elaborazione del messaggio %s", m.message_id)
            return ERROR_TEXT, []
        finally:
            if path:
                path.unlink(missing_ok=True)   # il documento non resta sul server

    # -- schedule ------------------------------------------------------------------------------
    async def notify(self, target: str, text: str) -> None:
        """Notifier degli schedule: mail nuova a `target`, registrata nella sessione del thread."""
        subject = (text.splitlines() or [""])[0][:120]
        thread_id = await self.mailbox.send([target], subject, text, [])
        await self.service.record_outgoing_mail(thread_id, target, subject, text, [])
