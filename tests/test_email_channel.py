"""EmailChannel: polling, dedup, mittenti ammessi, allegati, risposta, notifier. Mailbox e service finti."""
import asyncio
import sqlite3
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from picobot.channels.email import EmailChannel
from picobot.config import Settings
from picobot.context import OutputFile, Reply
from picobot.documents import DocumentError
from picobot.mailbox import InAttachment, InMail, MailTooLarge, session_for

NOW = datetime.now(timezone.utc)
ERR = "Errore interno durante l'elaborazione. Riprova tra poco."


class FakeMailbox:
    address = "bot@agentmail.to"

    def __init__(self):
        self.mails: list[InMail] = []
        self.afters: list = []
        self.replies: list[tuple] = []
        self.sent: list[tuple] = []
        self.downloads: list[tuple] = []
        self.blobs: dict[str, bytes] = {}
        self.list_errors = 0
        self.reply_errors: list[Exception] = []     # una per chiamata a reply, in ordine

    async def list_since(self, after):
        self.afters.append(after)
        if self.list_errors:
            self.list_errors -= 1
            raise RuntimeError("rete giu'")
        return [m for m in self.mails if after is None or m.timestamp > after]

    async def reply(self, message_id, body_md, files):
        if self.reply_errors:
            raise self.reply_errors.pop(0)
        self.replies.append((message_id, body_md, files))

    async def send(self, to, subject, body_md, files):
        self.sent.append((to, subject, body_md, files))
        return "th-new"

    async def download(self, message_id, attachment_id, dest):
        self.downloads.append((message_id, attachment_id))
        dest.write_bytes(self.blobs.get(attachment_id, b"%PDF"))


class FakeService:
    def __init__(self):
        self.asks: list[dict] = []
        self.summaries: list[dict] = []
        self.recorded: list[tuple] = []
        self.reply = Reply("risposta")
        self.ask_exc: Exception | None = None

    async def ask(self, text, *, user_id, session_id, ctx=None, target="auto"):
        doc = ctx.document if ctx else None
        self.asks.append(dict(text=text, user_id=user_id, session_id=session_id, ctx=ctx, target=target,
                              existed=doc.exists() if doc else None))
        if self.ask_exc:
            raise self.ask_exc
        return self.reply

    async def summarize(self, path, instruction="", *, user_id, name="", session_id=None):
        self.summaries.append(dict(path=path, instruction=instruction, user_id=user_id, name=name,
                                   session_id=session_id, existed=path.exists()))
        return "riassunto"

    async def record_outgoing_mail(self, thread_id, address, subject, body, filenames):
        self.recorded.append((thread_id, address, subject, body, filenames))


def mail(mid="m1", sender="mario@esempio.it", subject="Ciao", text="dimmi l'ora", thread="t1", ts=None,
         attachments=None, auto=False):
    return InMail(mid, thread, sender, subject, text, ts or NOW + timedelta(seconds=5),
                  attachments or [], auto)


def setup(tmp_path, **kw):
    s = Settings(workspace_dir=tmp_path / "ws", data_dir=tmp_path / "data", agentmail_api_key="k",
                 inbox_id="bot@agentmail.to", email_allowed_senders="mario@esempio.it:123", **kw)
    mb, svc = FakeMailbox(), FakeService()
    ch = EmailChannel(s, svc, mb)
    asyncio.run(ch.poll_once())           # primo avvio: riga sentinella, niente da elaborare
    return s, mb, svc, ch


def poll(ch, times=1):
    async def go():
        for _ in range(times):
            await ch.poll_once()
    asyncio.run(go())


def seen(s):
    with sqlite3.connect(s.database_file) as c:
        return dict(c.execute("SELECT message_id, ts FROM picobot_email_seen"))


# ---------------- primo avvio e dedup ----------------
def test_first_start_processes_nothing_then_new_mail_is_asked(tmp_path):
    s = Settings(workspace_dir=tmp_path / "ws", data_dir=tmp_path / "data", agentmail_api_key="k",
                 inbox_id="bot@agentmail.to", email_allowed_senders="mario@esempio.it")
    mb, svc = FakeMailbox(), FakeService()
    mb.mails = [mail("old1", ts=NOW - timedelta(hours=2)), mail("old2", ts=NOW - timedelta(hours=1))]
    ch = EmailChannel(s, svc, mb)
    poll(ch)
    assert svc.asks == [] and mb.replies == [] and mb.afters == []   # sentinella, nessuna lettura
    assert len(seen(s)) == 1
    mb.mails.append(mail("new", ts=NOW + timedelta(seconds=30)))
    poll(ch)
    assert [a["text"] for a in svc.asks] == ["Ciao\n\ndimmi l'ora"]


def test_after_is_max_ts_minus_300s(tmp_path):
    s, mb, svc, ch = setup(tmp_path)
    ts = NOW + timedelta(seconds=40)
    mb.mails = [mail("a", ts=ts)]
    poll(ch)
    poll(ch)
    assert mb.afters[-1] == ts - timedelta(seconds=300)


def test_same_mail_returned_twice_is_asked_once(tmp_path):
    s, mb, svc, ch = setup(tmp_path)
    mb.mails = [mail()]
    poll(ch, 2)
    assert len(svc.asks) == 1 and len(mb.replies) == 1


def test_seen_survives_a_new_channel_instance(tmp_path):
    s, mb, svc, ch = setup(tmp_path)
    mb.mails = [mail()]
    poll(ch)
    poll(EmailChannel(s, svc, mb))
    assert len(svc.asks) == 1


# ---------------- filtri ----------------
def test_sender_not_allowed_is_marked_and_ignored(tmp_path):
    s, mb, svc, ch = setup(tmp_path)
    mb.mails = [mail("x", sender="estraneo@altro.it")]
    poll(ch, 2)
    assert svc.asks == [] and mb.replies == [] and "x" in seen(s)


def test_own_message_is_ignored(tmp_path):
    s, mb, svc, ch = setup(tmp_path)
    mb.mails = [mail("own", sender="bot@agentmail.to")]
    poll(ch)
    assert svc.asks == [] and mb.replies == [] and "own" in seen(s)


def test_auto_reply_is_ignored(tmp_path):
    s, mb, svc, ch = setup(tmp_path)
    mb.mails = [mail("ooo", auto=True)]
    poll(ch)
    assert svc.asks == [] and mb.replies == [] and "ooo" in seen(s)


def test_unknown_sender_logs_sender_not_subject(tmp_path, caplog):
    s, mb, svc, ch = setup(tmp_path)
    mb.mails = [mail("x", sender="estraneo@altro.it", subject="SEGRETO-OGGETTO", text="SEGRETO-CORPO")]
    with caplog.at_level("INFO", logger="picobot.channels.email"):
        poll(ch)
    assert "estraneo@altro.it" in caplog.text and "SEGRETO" not in caplog.text


# ---------------- elaborazione e risposta ----------------
def test_allowed_mail_asks_with_email_ctx_and_replies_with_files(tmp_path):
    s, mb, svc, ch = setup(tmp_path)
    f = tmp_path / "out.docx"
    f.write_bytes(b"x")
    svc.reply = Reply("ecco **fatto**", [OutputFile(f, "out.docx", 1)])
    mb.mails = [mail("m9", thread="th7")]
    poll(ch)
    [a] = svc.asks
    assert a["session_id"] == session_for("th7", "mario@esempio.it")
    assert a["user_id"] == "123" and a["ctx"].user_id == "123"
    assert a["ctx"].channel == "email" and a["ctx"].pre_approved is True and a["ctx"].target == "mario@esempio.it"
    assert a["ctx"].confirm is None and a["target"] == "auto"
    assert mb.replies == [("m9", "ecco **fatto**", [f])]


def test_user_id_is_address_without_link(tmp_path):
    s, mb, svc, ch = setup(tmp_path)
    s2 = Settings(workspace_dir=tmp_path / "ws", data_dir=tmp_path / "data", agentmail_api_key="k",
                  inbox_id="bot@agentmail.to", email_allowed_senders="mario@esempio.it")
    ch2 = EmailChannel(s2, svc, mb)
    mb.mails = [mail()]
    poll(ch2)
    assert svc.asks[0]["user_id"] == "mario@esempio.it"


def test_empty_subject_and_body_text_is_stripped(tmp_path):
    s, mb, svc, ch = setup(tmp_path)
    mb.mails = [mail(subject="", text="solo corpo")]
    poll(ch)
    assert svc.asks[0]["text"] == "solo corpo"


def test_ask_error_replies_generic_and_marks_seen(tmp_path):
    s, mb, svc, ch = setup(tmp_path)
    svc.ask_exc = RuntimeError("boom")
    mb.mails = [mail("e1")]
    poll(ch, 2)
    assert mb.replies == [("e1", ERR, [])] and len(svc.asks) == 1 and "e1" in seen(s)


def test_document_error_replies_with_its_message(tmp_path):
    s, mb, svc, ch = setup(tmp_path)
    svc.ask_exc = DocumentError("PDF protetto da password.")
    mb.mails = [mail()]
    poll(ch)
    assert mb.replies[0][1] == "PDF protetto da password."


def test_reply_failure_still_marks_seen_and_does_not_reask(tmp_path):
    s, mb, svc, ch = setup(tmp_path)
    mb.reply_errors = [RuntimeError("429")]
    mb.mails = [mail("r1")]
    poll(ch, 2)
    assert len(svc.asks) == 1 and "r1" in seen(s) and mb.replies == []


def test_mail_too_large_replies_without_files_and_with_note(tmp_path):
    s, mb, svc, ch = setup(tmp_path)
    f = tmp_path / "big.csv"
    f.write_bytes(b"x")
    svc.reply = Reply("ecco", [OutputFile(f, "big.csv", 1)])
    mb.reply_errors = [MailTooLarge("troppo")]
    mb.mails = [mail("b1")]
    poll(ch)
    assert mb.replies == [("b1", "ecco\n\nAllegati oltre 6 MB: non inviati.", [])]


def test_one_failing_mail_does_not_stop_the_next(tmp_path):
    s, mb, svc, ch = setup(tmp_path)
    mb.reply_errors = [RuntimeError("x")]
    mb.mails = [mail("a", ts=NOW + timedelta(seconds=5)), mail("b", ts=NOW + timedelta(seconds=6))]
    poll(ch)
    assert len(svc.asks) == 2 and [r[0] for r in mb.replies] == ["b"]


# ---------------- errori di lettura ----------------
def test_list_since_error_does_not_raise_and_next_round_works(tmp_path, caplog):
    s, mb, svc, ch = setup(tmp_path)
    mb.mails = [mail("l1")]
    mb.list_errors = 1
    with caplog.at_level("WARNING", logger="picobot.channels.email"):
        poll(ch)
    assert svc.asks == [] and "l1" not in seen(s) and "casella" in caplog.text.lower()
    poll(ch)
    assert len(svc.asks) == 1 and "l1" in seen(s)


def test_run_survives_poll_exception_and_stops(tmp_path):
    s, mb, svc, ch = setup(tmp_path, poll_interval_s=0)
    calls = []

    async def boom():
        calls.append(1)
        if len(calls) >= 3:
            stop.set()
        raise RuntimeError("giro rotto")

    stop = None

    async def go():
        nonlocal stop
        stop = asyncio.Event()
        ch.poll_once = boom
        await asyncio.wait_for(ch.run(stop), 5)
    asyncio.run(go())
    assert len(calls) == 3


def test_run_returns_when_stop_is_set_during_wait(tmp_path):
    s, mb, svc, ch = setup(tmp_path, poll_interval_s=3600)

    async def go():
        stop = asyncio.Event()
        task = asyncio.create_task(ch.run(stop))
        await asyncio.sleep(0.05)
        stop.set()
        await asyncio.wait_for(task, 5)
    asyncio.run(go())


# ---------------- allegati ----------------
def att(aid, name, size=100, inline=False):
    return InAttachment(aid, name, size, inline)


def test_pdf_attachment_with_empty_body_asks_with_document_and_deletes_file(tmp_path):
    s, mb, svc, ch = setup(tmp_path)
    mb.mails = [mail(subject="", text="", attachments=[att("a1", "x.pdf")])]
    poll(ch)
    [a] = svc.asks
    assert a["text"] == "[Documento caricato: x.pdf]"
    assert a["ctx"].document_name == "x.pdf" and a["existed"] is True
    assert a["ctx"].document.parent == s.data_dir / "inbox" and a["ctx"].document.suffix == ".pdf"
    assert not a["ctx"].document.exists()
    assert mb.downloads == [("m1", "a1")]


def test_document_deleted_even_when_ask_fails(tmp_path):
    s, mb, svc, ch = setup(tmp_path)
    svc.ask_exc = RuntimeError("x")
    mb.mails = [mail(attachments=[att("a1", "x.pdf")])]
    poll(ch)
    assert not svc.asks[0]["ctx"].document.exists()


def test_prompt_has_document_marker_before_text(tmp_path):
    s, mb, svc, ch = setup(tmp_path)
    mb.mails = [mail(subject="Contratto", text="fanne un riassunto breve", attachments=[att("a1", "c.docx")])]
    poll(ch)
    assert svc.asks[0]["text"] == "[Documento caricato: c.docx] Contratto\n\nfanne un riassunto breve"


def test_first_supported_attachment_used_others_listed_as_ignored(tmp_path):
    s, mb, svc, ch = setup(tmp_path)
    mb.mails = [mail(attachments=[att("i", "firma.png", inline=True), att("a1", "foto.png"),
                                  att("a2", "dati.csv"), att("a3", "altro.txt")])]
    poll(ch)
    assert mb.downloads == [("m1", "a2")]
    reply = mb.replies[0][1]
    assert reply.startswith("risposta") and "foto.png" in reply and "altro.txt" in reply
    assert "firma.png" not in reply and "dati.csv" not in reply.split("ignorati")[1]


def test_oversized_attachment_not_downloaded_and_listed(tmp_path):
    s, mb, svc, ch = setup(tmp_path)
    mb.mails = [mail(attachments=[att("a1", "enorme.pdf", size=s.max_upload_mb * 1024 * 1024 + 1)])]
    poll(ch)
    assert mb.downloads == [] and svc.asks[0]["ctx"].document is None
    assert "enorme.pdf" in mb.replies[0][1]


def test_riassumi_in_subject_summarizes_attachment(tmp_path):
    s, mb, svc, ch = setup(tmp_path)
    mb.mails = [mail(subject="/riassumi in 3 punti", text="grazie", attachments=[att("a1", "r.pdf")])]
    poll(ch)
    [sm] = svc.summaries
    assert svc.asks == [] and sm["instruction"] == "in 3 punti" and sm["name"] == "r.pdf" and sm["existed"]
    assert sm["user_id"] == "123" and sm["session_id"] == session_for("t1", "mario@esempio.it")
    assert not sm["path"].exists()
    assert mb.replies == [("m1", "riassunto", [])]


def test_riassumi_first_body_line_summarizes_attachment(tmp_path):
    s, mb, svc, ch = setup(tmp_path)
    mb.mails = [mail(subject="Per te", text="\n/Riassumi breve\naltro", attachments=[att("a1", "r.txt")])]
    poll(ch)
    assert svc.summaries[0]["instruction"] == "breve" and svc.asks == []


def test_riassumi_without_attachment_goes_to_router(tmp_path):
    s, mb, svc, ch = setup(tmp_path)
    mb.mails = [mail(subject="/riassumi https://esempio.it/a", text="")]
    poll(ch)
    assert svc.summaries == [] and len(svc.asks) == 1


def test_summarize_document_error_replies_with_message(tmp_path):
    s, mb, svc, ch = setup(tmp_path)

    async def bad(*a, **k):
        raise DocumentError("File vuoto.")
    svc.summarize = bad
    mb.mails = [mail(subject="/riassumi", attachments=[att("a1", "r.pdf")])]
    poll(ch)
    assert mb.replies[0][1] == "File vuoto."


# ---------------- pulizia ----------------
def test_old_rows_purged_but_latest_kept(tmp_path):
    s, mb, svc, ch = setup(tmp_path)
    old = time.time() - 40 * 86400
    with sqlite3.connect(s.database_file) as c:
        c.executemany("INSERT INTO picobot_email_seen VALUES(?,?)", [("vecchia1", old), ("vecchia2", old - 5)])
    poll(ch)
    ids = seen(s)
    assert "vecchia1" not in ids and "vecchia2" not in ids and len(ids) == 1   # resta la sentinella


def test_latest_row_kept_even_if_older_than_30_days(tmp_path):
    s, mb, svc, ch = setup(tmp_path)
    old = time.time() - 40 * 86400
    with sqlite3.connect(s.database_file) as c:
        c.execute("DELETE FROM picobot_email_seen")
        c.executemany("INSERT INTO picobot_email_seen VALUES(?,?)", [("a", old), ("b", old - 100)])
    poll(ch)
    assert list(seen(s)) == ["a"]


# ---------------- notify ----------------
def test_notify_sends_new_mail_and_records_outgoing(tmp_path):
    s, mb, svc, ch = setup(tmp_path)
    text = "[Schedule #3] x\n\nesito"
    asyncio.run(ch.notify("io@jumpi.top", text))
    assert mb.sent == [(["io@jumpi.top"], "[Schedule #3] x", text, [])]
    assert svc.recorded == [("th-new", "io@jumpi.top", "[Schedule #3] x", text, [])]


def test_notify_subject_is_cut_to_120_chars(tmp_path):
    s, mb, svc, ch = setup(tmp_path)
    asyncio.run(ch.notify("io@jumpi.top", "a" * 300))
    assert mb.sent[0][1] == "a" * 120


# ---------------- runner / __main__ ----------------
class FakeScheduler:
    def __init__(self):
        self.notifiers = {}

    async def start(self):
        pass


class FakeRunnerService:
    def __init__(self, s):
        self.s, self.scheduler, self.mailbox = s, FakeScheduler(), object()
        self.events = []
        type(self).last = self

    async def start(self):
        self.events.append("start")

    async def stop(self):
        self.events.append("stop")


class AutoStop(asyncio.Event):
    def __init__(self):
        super().__init__()
        asyncio.get_running_loop().call_later(0.05, self.set)


def serve_with(monkeypatch, tmp_path, use_email):
    from picobot import runner
    import picobot.channels.email as email_mod
    created = []

    class FakeChannel:
        def __init__(self, s, service, mailbox):
            created.append(mailbox)
            self.service = service

        async def notify(self, target, text):
            pass

        async def run(self, stop):
            await stop.wait()
            self.service.events.append("channel-stopped")

    s = Settings(workspace_dir=tmp_path / "ws", data_dir=tmp_path / "data")
    monkeypatch.setattr(runner, "PicoBotService", FakeRunnerService)
    monkeypatch.setattr(email_mod, "EmailChannel", FakeChannel)
    monkeypatch.setattr(asyncio, "Event", AutoStop)
    asyncio.run(runner.serve(s, False, False, use_email))
    return created, FakeRunnerService.last


def test_serve_without_email_creates_no_channel(monkeypatch, tmp_path):
    created, svc = serve_with(monkeypatch, tmp_path, False)
    assert created == [] and "email" not in svc.scheduler.notifiers


def test_serve_with_email_runs_channel_registers_notifier_and_awaits_it_before_stop(monkeypatch, tmp_path):
    created, svc = serve_with(monkeypatch, tmp_path, True)
    assert created == [svc.mailbox] and "email" in svc.scheduler.notifiers
    assert svc.events == ["start", "channel-stopped", "stop"]


def run_main(monkeypatch, tmp_path, argv, **settings_kw):
    from picobot import __main__ as m, runner
    calls = []

    async def fake_serve(s, use_tg, use_api, use_email):
        calls.append((use_tg, use_api, use_email))

    s = Settings(workspace_dir=tmp_path / "ws", data_dir=tmp_path / "data", **settings_kw)
    monkeypatch.setattr(m, "_settings", lambda: s)
    monkeypatch.setattr(runner, "serve", fake_serve)
    monkeypatch.setattr(sys, "argv", ["picobot", "serve", *argv])
    m.main()
    return calls


def test_main_email_off_without_config(monkeypatch, tmp_path):
    assert run_main(monkeypatch, tmp_path, ["--no-telegram"]) == [(False, True, False)]


def test_main_email_on_with_config_and_no_email_flag(monkeypatch, tmp_path):
    cfg = dict(agentmail_api_key="k", inbox_id="bot@agentmail.to")
    assert run_main(monkeypatch, tmp_path, ["--no-telegram"], **cfg) == [(False, True, True)]
    assert run_main(monkeypatch, tmp_path, ["--no-telegram", "--no-email"], **cfg) == [(False, True, False)]


def test_main_email_alone_is_a_valid_channel(monkeypatch, tmp_path):
    cfg = dict(agentmail_api_key="k", inbox_id="bot@agentmail.to", api_tokens="")
    assert run_main(monkeypatch, tmp_path, ["--no-telegram"], **cfg) == [(False, False, True)]
