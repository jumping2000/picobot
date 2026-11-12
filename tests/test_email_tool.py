"""Mailbox (wrapper AgentMail) e tool send_email: client finto, nessuna chiamata reale."""
import asyncio
import base64
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from picobot.config import Settings
from picobot.context import RunCtx, reset_ctx, set_ctx
from picobot.mailbox import MAX_SEND_BYTES, MailTooLarge, Mailbox, session_for
from picobot.tools.email import make_email_tools

T0 = datetime(2026, 11, 12, 9, 0, tzinfo=timezone.utc)


class FakeMessages:
    def __init__(self):
        self.calls = []
        self.pages = []          # lista di (items, next_page_token)
        self.full = {}           # message_id -> messaggio completo

    async def send(self, **kw):
        self.calls.append(("send", kw))
        return SimpleNamespace(message_id="m-out", thread_id="th-1")

    async def reply(self, **kw):
        self.calls.append(("reply", kw))
        return SimpleNamespace(message_id="m-rep", thread_id="th-1")

    async def list(self, **kw):
        self.calls.append(("list", kw))
        items, nxt = self.pages[len(self.calls_of("list")) - 1]
        return SimpleNamespace(messages=items, next_page_token=nxt)

    async def get(self, **kw):
        self.calls.append(("get", kw))
        return self.full[kw["message_id"]]

    async def get_attachment(self, **kw):
        self.calls.append(("get_attachment", kw))
        return SimpleNamespace(download_url="https://cdn.example/att")

    def calls_of(self, name):
        return [kw for n, kw in self.calls if n == name]


def fake_client():
    msgs = FakeMessages()
    return SimpleNamespace(inboxes=SimpleNamespace(messages=msgs)), msgs


def settings(tmp_path, **kw):
    return Settings(workspace_dir=tmp_path / "ws", data_dir=tmp_path / "data", agentmail_api_key="k",
                    inbox_id="Bot@Agentmail.to", email_allowed_senders="mario@esempio.it:123", **kw)


def message(mid, frm="Mario <MARIO@Esempio.it>", text=None, extracted=None, headers=None, attachments=None,
            ts=T0, thread="t1", subject="Ciao"):
    return SimpleNamespace(message_id=mid, thread_id=thread, from_=frm, subject=subject, text=text,
                           extracted_text=extracted, headers=headers, attachments=attachments, timestamp=ts)


def run(coro):
    return asyncio.run(coro)


# ---------------- session_for ----------------
def test_session_for_is_case_insensitive_and_prefixed():
    assert session_for("t1", "A@x.it") == session_for("t1", "a@x.it")
    assert session_for("t1", "a@x.it").startswith("mail-t1-")
    assert session_for("t1", "a@x.it") != session_for("t1", "b@x.it")
    assert len(session_for("t1", "a@x.it").rsplit("-", 1)[1]) == 8


# ---------------- Mailbox.send / reply ----------------
def test_send_passes_body_html_and_base64_attachment(tmp_path):
    client, msgs = fake_client()
    f = tmp_path / "r.txt"
    f.write_bytes(b"ciao mondo")
    mb = Mailbox(settings(tmp_path), client=client)
    assert mb.address == "bot@agentmail.to"
    assert run(mb.send(["mario@esempio.it"], "Oggetto", "ecco **x**", [f])) == "th-1"
    [kw] = msgs.calls_of("send")
    assert kw["inbox_id"] == "Bot@Agentmail.to"
    assert kw["to"] == ["mario@esempio.it"] and kw["subject"] == "Oggetto" and kw["text"] == "ecco **x**"
    assert "<strong>x</strong>" in kw["html"]
    [att] = kw["attachments"]
    assert base64.b64decode(att["content"]) == b"ciao mondo"
    assert att["filename"] == "r.txt" and att["content_type"] == "text/plain"


def test_send_too_large_raises_before_sdk_call(tmp_path):
    client, msgs = fake_client()
    f = tmp_path / "big.csv"
    f.write_bytes(b"x" * (5 * 1024 * 1024))     # 5 MB raw -> ~6.7 MB in base64
    with pytest.raises(MailTooLarge):
        run(Mailbox(settings(tmp_path), client=client).send(["a@x.it"], "s", "b", [f]))
    assert msgs.calls == []


def test_send_size_check_counts_base64_and_margin(tmp_path):
    client, msgs = fake_client()
    ok = tmp_path / "ok.csv"
    ok.write_bytes(b"x" * int((MAX_SEND_BYTES - 64 * 1024) * 3 / 4 - 10))   # appena sotto il limite
    run(Mailbox(settings(tmp_path), client=client).send(["a@x.it"], "s", "b", [ok]))
    assert len(msgs.calls_of("send")) == 1
    over = tmp_path / "over.csv"
    over.write_bytes(b"x" * int((MAX_SEND_BYTES - 64 * 1024) * 3 / 4 + 10))  # appena sopra
    with pytest.raises(MailTooLarge):
        run(Mailbox(settings(tmp_path), client=client).send(["a@x.it"], "s", "b", [over]))
    assert len(msgs.calls_of("send")) == 1


def test_reply_uses_message_id_and_attachments(tmp_path):
    client, msgs = fake_client()
    f = tmp_path / "r.md"
    f.write_bytes(b"# t")
    assert run(Mailbox(settings(tmp_path), client=client).reply("m-in", "**ok**", [f])) is None
    [kw] = msgs.calls_of("reply")
    assert kw["message_id"] == "m-in" and kw["text"] == "**ok**" and "<strong>ok</strong>" in kw["html"]
    assert base64.b64decode(kw["attachments"][0]["content"]) == b"# t"


# ---------------- Mailbox.list_since ----------------
def test_list_since_maps_sender_text_and_flags(tmp_path):
    client, msgs = fake_client()
    att = SimpleNamespace(attachment_id="a1", filename="f.pdf", size=12, content_disposition="attachment")
    inl = SimpleNamespace(attachment_id="a2", filename=None, size=3, content_disposition="inline")
    msgs.pages = [([message("m1")], None)]
    msgs.full = {"m1": message("m1", text="ciao", extracted="", attachments=[att, inl],
                               headers={"auto-submitted": "auto-replied"})}
    [m] = run(Mailbox(settings(tmp_path), client=client).list_since(T0))
    assert m.sender == "mario@esempio.it"
    assert m.text == "ciao"                       # extracted_text vuoto: ripiega su text
    assert (m.message_id, m.thread_id, m.subject, m.timestamp) == ("m1", "t1", "Ciao", T0)
    assert m.auto_reply is True
    assert [(a.attachment_id, a.filename, a.size, a.inline) for a in m.attachments] == [
        ("a1", "f.pdf", 12, False), ("a2", "", 3, True)]


def test_list_since_prefers_extracted_text_and_no_auto_reply(tmp_path):
    client, msgs = fake_client()
    msgs.pages = [([message("m1")], None)]
    msgs.full = {"m1": message("m1", text="citazione\nnuovo", extracted="nuovo", headers={"Auto-Submitted": "no"})}
    [m] = run(Mailbox(settings(tmp_path), client=client).list_since(None))
    assert m.text == "nuovo" and m.auto_reply is False and m.attachments == []


def test_list_since_missing_text_and_headers(tmp_path):
    client, msgs = fake_client()
    msgs.pages = [([message("m1")], None)]
    msgs.full = {"m1": message("m1")}
    [m] = run(Mailbox(settings(tmp_path), client=client).list_since(None))
    assert m.text == "" and m.auto_reply is False


def test_list_since_filters_ascending_all_pages_in_ascending_order(tmp_path):
    client, msgs = fake_client()
    msgs.pages = [([message("m1")], "tok"), ([message("m2")], None)]
    msgs.full = {"m1": message("m1", text="a"), "m2": message("m2", text="b")}
    out = run(Mailbox(settings(tmp_path), client=client).list_since(T0))
    assert [m.message_id for m in out] == ["m1", "m2"]
    first, second = msgs.calls_of("list")
    for kw in (first, second):
        assert kw["include_unauthenticated"] is False and kw["include_spam"] is False
        assert kw["include_blocked"] is False and kw["ascending"] is True and kw["after"] == T0
    assert "page_token" not in first or first["page_token"] is None
    assert second["page_token"] == "tok"


def test_list_since_orders_ascending_even_if_sdk_returns_descending(tmp_path):
    client, msgs = fake_client()
    later = datetime(2026, 11, 12, 10, 0, tzinfo=timezone.utc)
    msgs.pages = [([message("m2", ts=later), message("m1")], None)]
    msgs.full = {"m1": message("m1", text="a"), "m2": message("m2", text="b", ts=later)}
    out = run(Mailbox(settings(tmp_path), client=client).list_since(None))
    assert [m.message_id for m in out] == ["m1", "m2"]


# ---------------- Mailbox.download ----------------
def test_download_fetches_bytes_from_signed_url(tmp_path, monkeypatch):
    import httpx
    client, msgs = fake_client()
    real = httpx.AsyncClient

    def handler(req):
        assert str(req.url) == "https://cdn.example/att"
        return httpx.Response(200, content=b"BYTES")
    monkeypatch.setattr("picobot.mailbox.httpx.AsyncClient",
                        lambda **kw: real(transport=httpx.MockTransport(handler), **kw))
    dest = tmp_path / "d" / "f.pdf"
    dest.parent.mkdir()
    run(Mailbox(settings(tmp_path), client=client).download("m1", "a1", dest))
    assert dest.read_bytes() == b"BYTES"
    [kw] = msgs.calls_of("get_attachment")
    assert (kw["message_id"], kw["attachment_id"]) == ("m1", "a1")


# ---------------- tool send_email ----------------
class FakeMailbox:
    def __init__(self, raises=None):
        self.sent, self.raises = [], raises

    async def send(self, to, subject, body_md, files):
        if self.raises:
            raise self.raises
        self.sent.append((to, subject, body_md, files))
        return "th-9"


@pytest.fixture
def env(tmp_path):
    s = settings(tmp_path)
    s.outputs_dir.mkdir(parents=True)
    (s.outputs_dir / "r.txt").write_text("dati")
    (s.workspace_dir / "segreto.txt").write_text("no")
    return s


def call(s, mb, record, *args, ctx=True):
    send = make_email_tools(s, mb, record)[0]
    token = set_ctx(RunCtx("u", "api") if ctx else None)
    try:
        return asyncio.run(send(*args))
    finally:
        reset_ctx(token)


def test_send_email_schema_exposes_attachments_to_the_model(env):
    """Agno nasconde al modello il parametro `files` (riservato ai media): l'allegato deve avere un altro nome."""
    from agno.tools.function import Function
    props = Function.from_callable(make_email_tools(env, FakeMailbox(), None)[0]).parameters["properties"]
    assert {"to", "subject", "body", "attachments"} <= set(props)


def test_send_email_ok_records_once_per_recipient(env):
    mb, rec = FakeMailbox(), []

    async def record(*a): rec.append(a)
    out = call(env, mb, record, ["Mario <a@x.it>", "b@x.it"], "Oggetto", "corpo", ["outputs/r.txt"])
    assert out.startswith("Inviata a") and "a@x.it" in out and "b@x.it" in out
    [(to, subject, body, files)] = mb.sent
    assert to == ["Mario <a@x.it>", "b@x.it"] and files == [env.outputs_dir / "r.txt"]
    assert rec == [("th-9", "a@x.it", "Oggetto", "corpo", ["r.txt"]), ("th-9", "b@x.it", "Oggetto", "corpo", ["r.txt"])]


def test_send_email_refuses_path_outside_outputs(env):
    mb = FakeMailbox()

    async def record(*a): raise AssertionError
    out = call(env, mb, record, ["a@x.it"], "s", "b", ["segreto.txt"])
    assert out.startswith("Rifiutato:") and mb.sent == []


def test_send_email_too_large_mentions_6_mb(env):
    async def record(*a): raise AssertionError
    out = call(env, FakeMailbox(raises=MailTooLarge("x")), record, ["a@x.it"], "s", "b", [])
    assert out.startswith("Rifiutato:") and "6 MB" in out


def test_send_email_record_failure_keeps_outcome(env):
    async def record(*a): raise RuntimeError("db giu'")
    out = call(env, FakeMailbox(), record, ["a@x.it"], "s", "b", [])
    assert out.startswith("Inviata a")


def test_send_email_sdk_failure_is_text_not_exception(env):
    async def record(*a): raise AssertionError
    out = call(env, FakeMailbox(raises=RuntimeError("boom")), record, ["a@x.it"], "s", "b", [])
    assert out.startswith("Errore") and "boom" not in out


def test_send_email_no_recipients_or_no_ctx(env):
    async def record(*a): raise AssertionError
    assert call(env, FakeMailbox(), record, [], "s", "b", []).startswith("Rifiutato:")
    assert call(env, FakeMailbox(), record, ["a@x.it"], "s", "b", [], ctx=False).startswith("Rifiutato:")


# ---------------- service.record_outgoing_mail ----------------
def test_record_outgoing_mail_only_for_allowed_senders(tmp_path):
    from picobot.service import PicoBotService
    svc = PicoBotService(settings(tmp_path))
    calls = []

    async def fake(session_id, user_id, user_text, answer): calls.append((session_id, user_id, user_text, answer))
    svc._record_in_session = fake
    run(svc.record_outgoing_mail("t1", "estraneo@x.it", "Oggetto", "corpo", []))
    assert calls == []
    run(svc.record_outgoing_mail("t1", "Mario@Esempio.it", "Oggetto", "corpo", ["r.txt", "s.csv"]))
    [(sid, uid, user_text, answer)] = calls
    assert sid == session_for("t1", "mario@esempio.it") and uid == "123"
    assert user_text == "[Email inviata da PicoBot] Oggetto"
    assert answer.startswith("corpo") and "r.txt" in answer and "s.csv" in answer
