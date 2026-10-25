"""Canali: API (auth, endpoint), Telegram (auth, bottoni di conferma, documenti), CLI."""
import asyncio
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from telegram.error import BadRequest

import fake_llm
from picobot.channels import cli as cli_mod
from picobot.channels.api import create_app
from picobot.channels.common import parse_schedule_args, split_text
from picobot.channels.telegram import TelegramGateway, send_safe
from picobot.config import Settings
from picobot.context import OutputFile, Reply
from picobot.service import PicoBotService

A, B = {"Authorization": "Bearer tok-a"}, {"Authorization": "Bearer tok-b"}


def with_api(fn):
    async def inner():
        s = Settings(); svc = PicoBotService(s); await svc.start()
        app = create_app(s, svc)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
            await fn(c, svc)
    asyncio.run(inner())


# ---------------- API ----------------
def test_api_auth():
    async def t(c, svc):
        assert (await c.get("/health")).status_code == 200            # health pubblico
        assert (await c.post("/v1/chat", json={"message": "x"})).status_code == 401
        assert (await c.post("/v1/chat", json={"message": "x"}, headers={"Authorization": "Bearer sbagliato"})).status_code == 401
        assert (await c.post("/v1/chat", json={"message": "x"}, headers={"Authorization": "Basic tok-a"})).status_code == 401
        r = await c.post("/v1/chat", json={"message": "ciao"}, headers=A)
        assert r.status_code == 200 and r.json()["answer"] == "RISPOSTA-FINTA" and r.json()["session_id"]
    with_api(t)


def test_api_validation_and_code_gate():
    async def t(c, svc):
        assert (await c.post("/v1/chat", json={"message": ""}, headers=A)).status_code == 422
        assert (await c.post("/v1/chat", json={"message": "x", "session_id": "../x"}, headers=A)).status_code == 422
        fake_llm.LOG.clear()
        await c.post("/v1/chat", json={"message": "scrivi un programma"}, headers=A)
        res = [m["content"] for b in fake_llm.LOG for m in b["messages"] if m["role"] == "tool"]
        assert any("NON consentita" in r for r in res)               # senza approve_code niente esecuzione
        fake_llm.LOG.clear()
        await c.post("/v1/chat", json={"message": "scrivi un programma", "approve_code": True}, headers=A)
        res = [m["content"] for b in fake_llm.LOG for m in b["messages"] if m["role"] == "tool"]
        assert any("42" in r for r in res)
    with_api(t)


def test_api_summarize_upload(tmp_path):
    async def t(c, svc):
        r = await c.post("/v1/summarize", headers=A, files={"file": ("n.txt", b"contenuto")}, data={"instruction": "breve"})
        assert r.status_code == 200 and r.json()["summary"] == "RISPOSTA-FINTA"
        assert (await c.post("/v1/summarize", headers=A, files={"file": ("n.exe", b"x")})).status_code == 415
        assert (await c.post("/v1/summarize", headers=A, files={"file": ("e.txt", b"  ")})).status_code == 422
        big = b"a" * (svc.s.max_upload_mb * 1024 * 1024 + 1)
        assert (await c.post("/v1/summarize", headers=A, files={"file": ("b.txt", big)})).status_code == 413
        assert not list((svc.s.data_dir / "inbox").glob("*"))        # nessun file residuo
        assert (await c.post("/v1/summarize", files={"file": ("n.txt", b"x")})).status_code == 401
        bad = await c.post("/v1/summarize", headers=A, files={"file": ("n.txt", b"x")}, data={"session_id": "../x"})
        assert bad.status_code == 422
    with_api(t)


def test_api_summary_enters_session_for_followup():
    async def t(c, svc):
        r = await c.post("/v1/summarize", headers=A, files={"file": ("bilancio.txt", b"ricavi 100")})
        sid = r.json()["session_id"]
        fake_llm.LOG.clear()
        await c.post("/v1/chat", json={"message": "dimmi di piu'", "session_id": sid}, headers=A)
        assert "[Documento caricato: bilancio.txt]" in str(fake_llm.LOG[0]["messages"])
        fake_llm.LOG.clear()                                        # altro utente, stesso session_id: nessuna fuga
        await c.post("/v1/chat", json={"message": "dimmi di piu'", "session_id": sid}, headers=B)
        assert "bilancio.txt" not in str(fake_llm.LOG[0]["messages"])
    with_api(t)


def test_api_memory_and_schedules_isolated_per_user():
    async def t(c, svc):
        await c.post("/v1/chat", json={"message": "ricorda che mi chiamo Gianpi"}, headers=A)
        assert (await c.get("/v1/memory", headers=A)).json()["memories"]
        assert (await c.get("/v1/memory", headers=B)).json()["memories"] == []
        assert (await c.delete("/v1/memory", headers=A)).status_code == 400          # serve confirm=true
        assert (await c.delete("/v1/memory?confirm=true", headers=A)).status_code == 204
        assert (await c.get("/v1/memory", headers=A)).json()["memories"] == []
        r = await c.post("/v1/schedules", json={"cron": "0 9 * * 1-5", "prompt": "quotazione AAPL"}, headers=A)
        sid = r.json()["id"]
        assert r.status_code == 201
        assert (await c.post("/v1/schedules", json={"cron": "* * * * *", "prompt": "x"}, headers=A)).status_code == 422
        assert len((await c.get("/v1/schedules", headers=A)).json()["schedules"]) >= 1
        assert (await c.get("/v1/schedules", headers=B)).json()["schedules"] == []
        assert (await c.delete(f"/v1/schedules/{sid}", headers=B)).status_code == 404   # non i task altrui
        assert (await c.delete(f"/v1/schedules/{sid}", headers=A)).status_code == 204
    with_api(t)


# ---------------- Telegram ----------------
def make_gw(**kw):
    s = Settings(telegram_allowed_user_ids="1,2", **kw)
    return TelegramGateway(s, PicoBotService(s))


def test_telegram_auth_fail_closed():
    gw = make_gw()
    assert gw.authorized(NS(effective_user=NS(id=1))) and not gw.authorized(NS(effective_user=NS(id=3)))
    assert not TelegramGateway(Settings(telegram_allowed_user_ids=""), None).authorized(NS(effective_user=NS(id=1)))


def _bot():
    msg = MagicMock(); msg.edit_reply_markup = AsyncMock()
    bot = MagicMock(); bot.send_message = AsyncMock(return_value=msg)
    return bot


def _press(gw, token, ans, user_id):
    q = NS(data=f"cf:{token}:{ans}", from_user=NS(id=user_id), answer=AsyncMock())
    asyncio.get_running_loop()
    return gw.on_callback(NS(callback_query=q), None), q


def test_confirm_buttons_yes_no_wrong_user_timeout():
    async def t():
        gw = make_gw(confirm_timeout_s=1)
        # conferma dell'utente giusto
        task = asyncio.create_task(gw.ask_yes_no(_bot(), 10, 1, "Eseguire?"))
        await asyncio.sleep(0.05)
        token = next(iter(gw._pending))
        await _press(gw, token, "y", 1)[0]
        assert await task is True
        # annulla
        task = asyncio.create_task(gw.ask_yes_no(_bot(), 10, 1, "Eseguire?"))
        await asyncio.sleep(0.05)
        await _press(gw, next(iter(gw._pending)), "n", 1)[0]
        assert await task is False
        # utente sbagliato: il bottone non vale, scade -> False
        task = asyncio.create_task(gw.ask_yes_no(_bot(), 10, 1, "Eseguire?"))
        await asyncio.sleep(0.05)
        coro, q = _press(gw, next(iter(gw._pending)), "y", 2)
        await coro
        q.answer.assert_awaited()
        assert await task is False
        assert not gw._pending
    asyncio.run(t())


def test_markdown_fallback_and_split():
    calls = []
    async def reply(text, parse_mode=None):
        calls.append(parse_mode)
        if parse_mode: raise BadRequest("can't parse entities")
    asyncio.run(send_safe(NS(message=NS(reply_text=reply)), "snake_case *rotto"))
    assert calls == ["Markdown", None]
    txt = "parola " * 1500
    assert all(len(p) <= 4000 for p in split_text(txt))


def test_telegram_document_flow(tmp_path):
    async def t():
        s = Settings(telegram_allowed_user_ids="1"); svc = PicoBotService(s); await svc.start()
        gw = TelegramGateway(s, svc)
        replies = []
        async def reply(text, **kw): replies.append(text)
        async def dl(custom_path): custom_path.write_text("testo del documento")
        def update(name, size=10):
            doc = NS(file_name=name, file_size=size, get_file=AsyncMock(return_value=NS(download_to_drive=dl)))
            return NS(effective_user=NS(id=1), effective_chat=NS(id=9),
                      message=NS(document=doc, caption="in 3 punti", reply_text=reply))
        ctx = NS(bot=MagicMock(send_chat_action=AsyncMock()), chat_data={})
        await gw.on_document(update("a.exe"), ctx)
        assert "non supportato" in replies[-1]
        await gw.on_document(update("a.txt", size=s.max_upload_mb * 1024 * 1024 + 1), ctx)
        assert "troppo grande" in replies[-1]
        fake_llm.LOG.clear()
        await gw.on_document(update("a.txt"), ctx)                  # v0.5: passa dal router
        assert replies[-1] == "RISPOSTA-FINTA"
        assert not list((s.data_dir / "inbox").glob("*"))      # file cancellato dopo l'uso
        assert "[Documento caricato: a.txt] in 3 punti" in str(fake_llm.LOG[0]["messages"])
        sid = ctx.chat_data["session_id"]                          # il riassunto e' nella sessione della chat
        fake_llm.LOG.clear()
        await svc.ask("e il punto 2?", user_id="1", session_id=sid)
        assert "[Documento caricato: a.txt]" in str(fake_llm.LOG[0]["messages"])
    asyncio.run(t())


def test_schedule_arg_parsing():
    assert parse_schedule_args("0 8 * * 1-5 | quotazioni AAPL") == ("0 8 * * 1-5", "quotazioni AAPL")
    with pytest.raises(ValueError):
        parse_schedule_args("0 8 * * 1-5 quotazioni")


# ---------------- CLI ----------------
def test_cli_session(monkeypatch, capsys):
    inputs = iter(["/help", "ciao", "scrivi un programma", "y", "/memory", "/quit"])
    async def fake_input(prompt): return next(inputs)
    monkeypatch.setattr(cli_mod, "_ainput", fake_input)
    async def t():
        s = Settings(); svc = PicoBotService(s); await svc.start()
        fake_llm.LOG.clear()
        await cli_mod.run_cli(s, svc)
    asyncio.run(t())
    out = capsys.readouterr().out
    assert "/forget" in out and "RISPOSTA-FINTA" in out and "Codice da eseguire" in out and "print(6*7)" in out
    res = [m["content"] for b in fake_llm.LOG for m in b["messages"] if m["role"] == "tool"]
    assert any("42" in r for r in res)


# ---------------- consegna file Telegram ----------------
def _files(tmp_path, *names):
    out = []
    for n in names:
        f = tmp_path / n
        f.write_bytes(b"data")
        out.append(OutputFile(f, n, 4))
    return out


def test_send_reply_documents(tmp_path):
    order = []
    async def reply_text(text, **kw): order.append("text")
    async def reply_document(document, **kw): order.append(f"doc:{kw['filename']}")
    upd = NS(message=NS(reply_text=reply_text, reply_document=reply_document))
    asyncio.run(make_gw().send_reply(upd, Reply("ecco", _files(tmp_path, "a.docx", "Relazione città.pptx"))))
    assert order == ["text", "doc:a.docx", "doc:Relazione città.pptx"]


def test_send_failure_is_reported(tmp_path):
    texts, names = [], []
    async def reply_text(text, **kw): texts.append(text)
    async def reply_document(document, **kw):
        names.append(kw["filename"])
        raise RuntimeError("boom")
    upd = NS(message=NS(reply_text=reply_text, reply_document=reply_document))
    asyncio.run(make_gw().send_reply(upd, Reply("ecco", _files(tmp_path, "Relazione città.docx"))))
    assert names == ["Relazione città.docx"] and any("Impossibile inviare il file" in t for t in texts)


def _confirm_bot(events):
    msg = MagicMock(); msg.edit_reply_markup = AsyncMock()
    async def send_message(chat_id, text, **kw): events.append(("msg", text)); return msg
    async def send_document(chat_id, document, **kw): events.append(("doc", kw["filename"], document.getvalue()))
    return NS(send_message=send_message, send_document=send_document)


def test_confirm_code_long_is_attached():
    async def t():
        gw, events, code = make_gw(confirm_timeout_s=1), [], "x" * 2000
        task = asyncio.create_task(gw.confirm_code(_confirm_bot(events), 10, 1, code, "node"))
        await asyncio.sleep(0.05)
        assert [e[0] for e in events] == ["doc", "msg"]                 # allegato PRIMA dei bottoni
        assert events[0][1:] == ("codice.js", code.encode()) and code not in events[1][1]
        await _press(gw, next(iter(gw._pending)), "y", 1)[0]
        assert await task is True
    asyncio.run(t())


def test_confirm_code_short_inline():
    async def t():
        gw, events, code = make_gw(confirm_timeout_s=1), [], "print('ciao')"
        task = asyncio.create_task(gw.confirm_code(_confirm_bot(events), 10, 1, code, "python"))
        await asyncio.sleep(0.05)
        assert [e[0] for e in events] == ["msg"] and code in events[0][1]
        await _press(gw, next(iter(gw._pending)), "n", 1)[0]
        assert await task is False
    asyncio.run(t())


# ---------------- consegna file CLI e API ----------------
def _fake_reply_with_file(svc, name="Relazione città.docx", data=b"hello"):
    svc.s.outputs_dir.mkdir(parents=True, exist_ok=True)
    f = svc.s.outputs_dir / name
    f.write_bytes(data)
    async def fake_ask(text, **kw):
        return Reply("ok", [OutputFile(f, f.name, len(data))])
    svc.ask = fake_ask
    return f


def test_api_chat_returns_files_and_download():
    async def t(c, svc):
        _fake_reply_with_file(svc)
        r = (await c.post("/v1/chat", json={"message": "x"}, headers=A)).json()
        f = r["files"][0]
        assert r["answer"] == "ok" and f["name"] == "Relazione città.docx" and f["size"] == 5
        d = await c.get(f"/v1/files/{f['id']}", headers=A)
        assert d.status_code == 200 and d.content == b"hello" and "filename*" in d.headers["content-disposition"]
        assert (await c.get(f"/v1/files/{f['id']}", headers=B)).status_code == 404
        assert (await c.get("/v1/files/" + "0" * 32, headers=A)).status_code == 404
        assert (await c.get("/v1/files/not-an-id", headers=A)).status_code == 404
        assert (await c.get(f"/v1/files/{f['id']}")).status_code == 401
    with_api(t)


def test_api_chat_without_files_has_empty_list():
    async def t(c, svc):
        r = (await c.post("/v1/chat", json={"message": "ciao"}, headers=A)).json()
        assert r["files"] == []
    with_api(t)


def test_cli_prints_file_path(monkeypatch, capsys):
    inputs = iter(["fammi un file", "/quit"])
    async def fake_input(prompt): return next(inputs)
    monkeypatch.setattr(cli_mod, "_ainput", fake_input)
    async def t():
        s = Settings(); svc = PicoBotService(s); await svc.start()
        f = _fake_reply_with_file(svc)
        await cli_mod.run_cli(s, svc)
        return f
    f = asyncio.run(t())
    assert f"File: {f}" in capsys.readouterr().out


def test_startup_purges_old_outbox(tmp_path):
    import os, time
    s = Settings(data_dir=tmp_path / "data")
    old = s.outbox_dir / "u" / ("a" * 32)
    old.mkdir(parents=True)
    (old / "x.docx").write_bytes(b"x")
    past = time.time() - 25 * 3600
    os.utime(old, (past, past))
    asyncio.run(PicoBotService(s).start())
    assert not old.exists()


# ---------------- /skills (Task 9) ----------------
def test_telegram_skills_command(tmp_path):
    from picobot.channels.common import HELP
    root = tmp_path / "skills"
    (root / "docx").mkdir(parents=True)
    (root / "docx" / "SKILL.md").write_text("---\nname: docx\ndescription: Crea documenti Word\n---\n")
    def run_cmd(gw, uid):
        out = []
        async def reply_text(text, **kw): out.append(text)
        upd = NS(effective_user=NS(id=uid), message=NS(reply_text=reply_text))
        asyncio.run(gw.on_skills(upd, None))
        return out
    gw = make_gw(skills_dir=root)
    assert run_cmd(gw, 1) == ["docx: Crea documenti Word"]
    assert run_cmd(gw, 3) == []                                # non autorizzato: nessuna risposta
    assert run_cmd(make_gw(skills_dir=tmp_path / "vuota"), 1) == ["Nessuna skill installata."]
    assert "/skills" in HELP


def test_cli_skills_command(monkeypatch, capsys, tmp_path):
    root = tmp_path / "skills"
    (root / "docx").mkdir(parents=True)
    (root / "docx" / "SKILL.md").write_text("---\nname: docx\ndescription: Crea documenti Word\n---\n")
    inputs = iter(["/skills", "/quit"])
    async def fake_input(prompt): return next(inputs)
    monkeypatch.setattr(cli_mod, "_ainput", fake_input)
    async def t():
        s = Settings(skills_dir=root); svc = PicoBotService(s); await svc.start()
        fake_llm.LOG.clear()
        await cli_mod.run_cli(s, svc)
    asyncio.run(t())
    assert "docx: Crea documenti Word" in capsys.readouterr().out and fake_llm.LOG == []


# ---------------- comandi /simple /complex /riassumi e upload via router (v0.5) ----------------
def _tg(tmp_path, svc_started=True):
    s = Settings(telegram_allowed_user_ids="1")
    svc = PicoBotService(s)
    return s, svc, TelegramGateway(s, svc)


def _doc_update(replies, name="a.txt", caption=None, content="testo del documento", reply_doc=None, text=None):
    async def reply(text, **kw): replies.append(text)
    async def reply_document(document, **kw): replies.append(f"FILE:{kw['filename']}")
    async def dl(custom_path): custom_path.write_text(content)
    doc = NS(file_name=name, file_size=10, get_file=AsyncMock(return_value=NS(download_to_drive=dl))) if name else None
    rdoc = NS(file_name=reply_doc, file_size=10, get_file=AsyncMock(return_value=NS(download_to_drive=dl))) if reply_doc else None
    msg = NS(document=doc, caption=caption, text=text, reply_text=reply, reply_document=reply_document,
             reply_to_message=NS(document=rdoc) if rdoc else None)
    return NS(effective_user=NS(id=1), effective_chat=NS(id=9), message=msg)


def _ctx():
    return NS(bot=MagicMock(send_chat_action=AsyncMock()), chat_data={}, args=[])


def _calls_router():
    return any("summarize_document" in {t["function"]["name"] for t in b.get("tools") or []} for b in fake_llm.LOG)


def test_telegram_document_goes_to_router_and_can_summarize(tmp_path):
    async def t():
        s, svc, gw = _tg(tmp_path); await svc.start(); replies = []
        fake_llm.LOG.clear()
        await gw.on_document(_doc_update(replies, caption="riassumi in 3 punti"), _ctx())
        bodies = str([b["messages"] for b in fake_llm.LOG])
        assert _calls_router() and "<documento" in bodies and "in 3 punti" in bodies   # router -> summarize_document
        fake_llm.LOG.clear()
        await gw.on_document(_doc_update(replies, caption=None), _ctx())             # didascalia vuota -> riassunto
        assert "<documento" in str([b["messages"] for b in fake_llm.LOG])
        assert not list((s.data_dir / "inbox").glob("*"))
    asyncio.run(t())


def test_telegram_unreadable_document_via_router(tmp_path):     # Review Focus 2
    async def t():
        s, svc, gw = _tg(tmp_path); await svc.start(); replies = []
        await gw.on_document(_doc_update(replies, caption=None, content="   "), _ctx())
        return replies
    replies = asyncio.run(t())
    assert replies and "errore" not in replies[-1].lower()


def test_telegram_caption_riassumi_is_direct(tmp_path):
    async def t():
        s, svc, gw = _tg(tmp_path); await svc.start(); replies = []
        fake_llm.LOG.clear()
        await gw.on_document(_doc_update(replies, caption="/riassumi in 3 punti"), _ctx())
        assert not _calls_router() and "in 3 punti" in str(fake_llm.LOG[-1]["messages"]) and replies[-1] == "RISPOSTA-FINTA"
        replies.clear()
        await gw.on_document(_doc_update(replies, caption="/riassumi", content="  "), _ctx())
        assert "Nessun testo" in replies[-1]
    asyncio.run(t())


def test_telegram_riassumi_reply_to_document(tmp_path):
    async def t():
        s, svc, gw = _tg(tmp_path); await svc.start(); replies = []
        fake_llm.LOG.clear()
        ctx = _ctx(); ctx.args = ["breve"]
        await gw.on_riassumi(_doc_update(replies, name=None, reply_doc="b.txt", text="/riassumi breve"), ctx)
        assert not _calls_router() and "breve" in str(fake_llm.LOG[-1]["messages"]) and replies[-1] == "RISPOSTA-FINTA"
        replies.clear()
        await gw.on_riassumi(_doc_update(replies, name=None, text="/riassumi"), _ctx())
        assert replies == ["Uso: /riassumi <link> [istruzioni], oppure rispondi a un documento con /riassumi (o usalo come didascalia)."]
        assert not list((s.data_dir / "inbox").glob("*"))
    asyncio.run(t())


def test_telegram_simple_complex_commands(tmp_path):
    async def t():
        s, svc, gw = _tg(tmp_path); await svc.start(); replies = []
        seen = []
        orig = svc.ask
        async def spy(text, **kw):
            seen.append((text, kw.get("target")))
            return await orig(text, **kw)
        svc.ask = spy
        await gw.on_simple(_doc_update(replies, name=None, text="/simple quotazione AAPL"), _ctx())
        await gw.on_complex(_doc_update(replies, name=None, text="/complex"), _ctx())
        return seen, replies
    seen, replies = asyncio.run(t())
    assert seen == [("quotazione AAPL", "simple")] and replies[-1] == "Uso: /complex <richiesta>"


def test_cli_v05_commands(monkeypatch, capsys, tmp_path):
    f = tmp_path / "doc.txt"; f.write_text("contenuto")
    inputs = iter([f"/simple quotazione AAPL", f"/complex scrivi una relazione", f"/riassumi {f} breve",
                   f"/file {f} riassumi", "/quit"])
    async def fake_input(prompt): return next(inputs)
    monkeypatch.setattr(cli_mod, "_ainput", fake_input)
    seen = []
    async def t():
        s = Settings(); svc = PicoBotService(s); await svc.start()
        orig_ask, orig_sum = svc.ask, svc.summarize
        async def ask(text, **kw):
            seen.append(("ask", text, kw.get("target", "auto"), kw["ctx"].document is not None)); return await orig_ask(text, **kw)
        async def summ(path, instr="", **kw):
            seen.append(("summarize", instr)); return await orig_sum(path, instr, **kw)
        svc.ask, svc.summarize = ask, summ
        await cli_mod.run_cli(s, svc)
    asyncio.run(t())
    assert seen == [("ask", "quotazione AAPL", "simple", False), ("ask", "scrivi una relazione", "complex", False),
                    ("summarize", "breve"), ("ask", f"[Documento caricato: doc.txt] riassumi", "auto", True)]
    assert f.exists()                                   # la CLI non cancella mai i file dell'utente


def test_help_lists_new_commands():
    from picobot.channels.cli import CLI_HELP
    from picobot.channels.common import HELP
    assert all(c in HELP for c in ("/simple", "/complex", "/riassumi"))
    assert all(c in CLI_HELP for c in ("/simple", "/complex", "/riassumi <percorso>", "/file <percorso>"))
    assert "/riassumi <link>" in HELP and "/riassumi <link>" in CLI_HELP   # pagine web su tutti i canali


# ---------------- /memory e /forget completi (v0.5) ----------------
def test_api_memory_sections():
    async def t(c, svc):
        await c.post("/v1/chat", json={"message": "seguo AAPL e ENI"}, headers=A)
        await c.post("/v1/chat", json={"message": "lavoro al progetto Harbor"}, headers=A)
        r = (await c.get("/v1/memory", headers=A)).json()
        assert set(r) == {"memories", "profile", "entities"} and r["profile"]["titoli_seguiti"] == "AAPL, ENI"
        assert r["entities"][0]["name"] == "Harbor" and r["entities"][0]["type"] == "project"
        assert (await c.get("/v1/memory", headers=B)).json() == {"memories": [], "profile": {}, "entities": []}
        assert (await c.delete("/v1/memory?confirm=true", headers=A)).status_code == 204
        assert (await c.get("/v1/memory", headers=A)).json() == {"memories": [], "profile": {}, "entities": []}
    with_api(t)


def test_telegram_forget_failure_is_not_confirmed(tmp_path):
    async def t():
        s, svc, gw = _tg(tmp_path); await svc.start(); replies = []
        async def boom(user_id): raise RuntimeError("x")
        svc.forget = boom
        gw.ask_yes_no = AsyncMock(return_value=True)
        await gw.on_forget(_doc_update(replies, name=None, text="/forget"), _ctx())
        return replies
    replies = asyncio.run(t())
    assert replies == ["Errore: la memoria non e' stata cancellata del tutto. Riprova."]


def test_telegram_memory_shows_sections(tmp_path):
    async def t():
        s, svc, gw = _tg(tmp_path); await svc.start(); replies = []
        await svc.ask("seguo AAPL e ENI", user_id="1", session_id="mm")
        await gw.on_memory(_doc_update(replies, name=None, text="/memory"), _ctx())
        return replies
    replies = asyncio.run(t())
    assert "Profilo" in replies[-1] and "AAPL, ENI" in replies[-1]


# ---------------- vocali e audio (v0.6) ----------------
import picobot.channels.telegram as tg_mod  # noqa: E402
from pathlib import Path  # noqa: E402
from picobot.stt import SttError, Transcript  # noqa: E402

VOICE_LONG = "Vocale troppo lungo (max 5 minuti)."


def _tg_voice(stt_url="http://stt:8000"):
    s = Settings(telegram_allowed_user_ids="1", stt_url=stt_url)
    svc = PicoBotService(s)
    return s, svc, TelegramGateway(s, svc)


def _fake_stt(monkeypatch, result):
    calls = []

    async def fake(s, path, filename):
        calls.append((Path(path), filename, Path(path).exists()))
        if isinstance(result, SttError):
            raise result
        return Transcript(result, "it")
    monkeypatch.setattr(tg_mod, "transcribe", fake)
    return calls


def _voice_update(replies, kws, kind="voice", duration=5, file_size=1000, mime="audio/ogg", file_name=None,
                  caption=None, dl_fails=False, uid=1):
    async def reply(text, **kw):
        replies.append(text)
        kws.append(kw)

    async def reply_document(document, **kw):
        replies.append(f"FILE:{kw['filename']}")

    async def dl(custom_path):
        if dl_fails:
            raise RuntimeError("rete")
        Path(custom_path).write_bytes(b"OggS")
    media = NS(duration=duration, file_size=file_size, mime_type=mime, file_name=file_name,
               get_file=AsyncMock(return_value=NS(download_to_drive=dl)))
    msg = NS(voice=None, audio=None, document=None, caption=caption, text=None, reply_text=reply,
             reply_document=reply_document, reply_to_message=None)
    setattr(msg, kind, media)
    return NS(effective_user=NS(id=uid), effective_chat=NS(id=9), message=msg), media


def _send(gw, upd, kind="voice"):
    handler = gw.on_document if kind == "document" else gw.on_voice
    return handler(upd, _ctx())


def _inbox_empty(s):
    return not list((s.data_dir / "inbox").glob("*"))


def test_voice_echo_then_router(monkeypatch):
    calls = _fake_stt(monkeypatch, "quotazione di AAPL")

    async def t():
        s, svc, gw = _tg_voice(); await svc.start(); replies, kws = [], []
        fake_llm.LOG.clear()
        upd, _ = _voice_update(replies, kws)
        await _send(gw, upd)
        return s, replies, kws
    s, replies, kws = asyncio.run(t())
    assert replies[0] == "🎤 quotazione di AAPL" and "parse_mode" not in kws[0]
    assert "quotazione di AAPL" in str(fake_llm.LOG[0]["messages"]) and replies[-1] == "RISPOSTA-FINTA"
    assert calls[0][2] and calls[0][0].suffix == ".ogg" and _inbox_empty(s)    # file presente durante, poi cancellato


def test_voice_empty_transcript_skips_router(monkeypatch):
    _fake_stt(monkeypatch, "   ")

    async def t():
        s, svc, gw = _tg_voice(); await svc.start(); replies, kws = [], []
        fake_llm.LOG.clear()
        await _send(gw, _voice_update(replies, kws)[0])
        return s, replies
    s, replies = asyncio.run(t())
    assert replies == ["Non ho capito il vocale, puoi ripeterlo o scriverlo?"] and fake_llm.LOG == [] and _inbox_empty(s)


def test_voice_disabled_without_stt_url(monkeypatch):
    calls = _fake_stt(monkeypatch, "x")

    async def t():
        s, svc, gw = _tg_voice(stt_url=""); await svc.start(); replies, kws = [], []
        upd, media = _voice_update(replies, kws)
        await _send(gw, upd)
        return replies, media
    replies, media = asyncio.run(t())
    assert replies == ["I messaggi vocali non sono abilitati."] and calls == []
    media.get_file.assert_not_called()


def test_voice_too_long_rejected_before_download(monkeypatch):
    calls = _fake_stt(monkeypatch, "x")

    async def t():
        s, svc, gw = _tg_voice(); await svc.start(); replies, kws = [], []
        upd, media = _voice_update(replies, kws, duration=301)
        await _send(gw, upd)
        return replies, media
    replies, media = asyncio.run(t())
    assert replies == [VOICE_LONG] and calls == []
    media.get_file.assert_not_called()


def test_voice_too_big_rejected_before_download(monkeypatch):
    calls = _fake_stt(monkeypatch, "x")

    async def t():
        s, svc, gw = _tg_voice(); await svc.start(); replies, kws = [], []
        upd, media = _voice_update(replies, kws, file_size=15 * 1024 * 1024 + 1)
        await _send(gw, upd)
        return replies, media
    replies, media = asyncio.run(t())
    assert replies == ["File troppo grande (max 15 MB)."] and calls == []
    media.get_file.assert_not_called()


@pytest.mark.parametrize("kind,msg", [
    ("unavailable", "Trascrizione non disponibile al momento: riprova o scrivi il messaggio."),
    ("unreadable", "Non riesco a leggere questo audio."),
    ("too_long", VOICE_LONG),                                   # Review Focus 1 (audio lungo senza durata)
])
def test_voice_stt_errors(monkeypatch, kind, msg):
    _fake_stt(monkeypatch, SttError(kind))

    async def t():
        s, svc, gw = _tg_voice(); await svc.start(); replies, kws = [], []
        fake_llm.LOG.clear()
        upd, _ = _voice_update(replies, kws, kind="document", duration=None, mime="audio/mpeg", file_name="n.mp3")
        await _send(gw, upd, "document")
        return s, replies
    s, replies = asyncio.run(t())
    assert replies[-1] == msg and fake_llm.LOG == [] and _inbox_empty(s)


def test_voice_download_failure(monkeypatch):
    calls = _fake_stt(monkeypatch, "x")

    async def t():
        s, svc, gw = _tg_voice(); await svc.start(); replies, kws = [], []
        await _send(gw, _voice_update(replies, kws, dl_fails=True)[0])
        return s, replies
    s, replies = asyncio.run(t())
    assert replies[-1] == "Impossibile scaricare il vocale, riprova." and calls == [] and _inbox_empty(s)


def test_audio_document_is_transcribed(monkeypatch):
    calls = _fake_stt(monkeypatch, "nota audio")

    async def t():
        s, svc, gw = _tg_voice(); await svc.start(); replies, kws = [], []
        upd, _ = _voice_update(replies, kws, kind="document", duration=None, mime="audio/mpeg", file_name="nota.mp3")
        await _send(gw, upd, "document")
        return replies
    replies = asyncio.run(t())
    assert replies[0] == "🎤 nota audio" and calls[0][1] == "nota.mp3" and calls[0][0].suffix == ".mp3"


def test_audio_caption_is_combined(monkeypatch):
    _fake_stt(monkeypatch, "testo")

    async def t():
        s, svc, gw = _tg_voice(); await svc.start(); replies, kws = [], []
        fake_llm.LOG.clear()
        upd, _ = _voice_update(replies, kws, kind="audio", mime="audio/mpeg", file_name="a.mp3", caption="riassumi")
        await _send(gw, upd)
    asyncio.run(t())
    assert "riassumi\\n\\n[Trascrizione audio]: testo" in str(fake_llm.LOG[0]["messages"])


def test_voice_unauthorized_is_ignored(monkeypatch):
    calls = _fake_stt(monkeypatch, "x")

    async def t():
        s, svc, gw = _tg_voice(); await svc.start(); replies, kws = [], []
        await _send(gw, _voice_update(replies, kws, uid=99)[0])
        return replies
    assert asyncio.run(t()) == [] and calls == []


def test_voice_echo_with_markdown_chars(monkeypatch):           # Review Focus 2
    _fake_stt(monkeypatch, "a_b *c* [d")

    async def t():
        s, svc, gw = _tg_voice(); await svc.start(); replies, kws = [], []
        await _send(gw, _voice_update(replies, kws)[0])
        return replies, kws
    replies, kws = asyncio.run(t())
    assert replies[0] == "🎤 a_b *c* [d" and "parse_mode" not in kws[0]


def test_voice_long_echo_is_split(monkeypatch):                 # Review Focus 3
    _fake_stt(monkeypatch, "parola " * 1300)

    async def t():
        s, svc, gw = _tg_voice(); await svc.start(); replies, kws = [], []
        await _send(gw, _voice_update(replies, kws)[0])
        return replies
    replies = asyncio.run(t())
    echo = replies[:-1]                                         # l'ultima risposta e' quella del router
    assert len(echo) >= 3 and echo[0].startswith("🎤 ") and all(len(e) <= 4000 for e in echo)


def test_text_after_stt_down_still_answered(monkeypatch):       # Review Focus 4
    _fake_stt(monkeypatch, SttError("unavailable"))

    async def t():
        s, svc, gw = _tg_voice(); await svc.start(); replies, kws = [], []
        await _send(gw, _voice_update(replies, kws)[0])
        async def reply(text, **kw): replies.append(text)
        text_upd = NS(effective_user=NS(id=1), effective_chat=NS(id=9),
                      message=NS(text="ciao", reply_text=reply, reply_document=AsyncMock()))
        await asyncio.wait_for(gw.on_message(text_upd, _ctx()), 5)
        return replies
    replies = asyncio.run(t())
    assert replies[0].startswith("Trascrizione non disponibile") and replies[-1] == "RISPOSTA-FINTA"


def test_forwarded_audio_without_name(monkeypatch):             # Review Focus 5
    calls = _fake_stt(monkeypatch, "inoltrato")

    async def t():
        s, svc, gw = _tg_voice(); await svc.start(); replies, kws = [], []
        upd, _ = _voice_update(replies, kws, kind="document", duration=None, mime="audio/ogg", file_name=None)
        await _send(gw, upd, "document")
        return replies
    replies = asyncio.run(t())
    assert calls[0][0].suffix == ".ogg" and replies[0] == "🎤 inoltrato"


# ---------------- /riassumi <link> su tutti i canali ----------------
URL = "https://microservices.io/post/architecture/2026/09/29/architecting-with-llms.html"


@pytest.fixture
def fake_page(monkeypatch):  # niente rete: la pagina "scaricata" e' fissa; 'blocked' simula un indirizzo privato
    from picobot.documents import DocumentError
    seen = []

    async def fetch(url):
        seen.append(url)
        if "blocked" in url:
            raise DocumentError("Indirizzo non consentito (rete locale o privata).")
        return "Testo ARTICOLO-XYZ della pagina."
    monkeypatch.setattr("picobot.service.fetch_article", fetch)
    return seen


def test_telegram_riassumi_link(tmp_path, fake_page):
    async def t():
        s, svc, gw = _tg(tmp_path); await svc.start(); replies = []
        fake_llm.LOG.clear()
        ctx = _ctx(); ctx.args = [URL, "breve"]
        await gw.on_riassumi(_doc_update(replies, name=None, text=f"/riassumi {URL} breve"), ctx)
        assert not _calls_router() and replies[-1] == "RISPOSTA-FINTA"
        assert "ARTICOLO-XYZ" in str(fake_llm.LOG[-1]["messages"]) and "breve" in str(fake_llm.LOG[-1]["messages"])
        ctx.args = ["http://blocked.local/"]
        await gw.on_riassumi(_doc_update(replies, name=None, text="/riassumi http://blocked.local/"), ctx)
        assert replies[-1] == "Indirizzo non consentito (rete locale o privata)."
    asyncio.run(t())
    assert fake_page == [URL, "http://blocked.local/"]


def test_cli_riassumi_link(monkeypatch, capsys, fake_page):
    inputs = iter([f"/riassumi {URL} breve", "/riassumi http://blocked.local/", "/quit"])
    async def fake_input(prompt): return next(inputs)
    monkeypatch.setattr(cli_mod, "_ainput", fake_input)
    async def t():
        s = Settings(); svc = PicoBotService(s); await svc.start()
        fake_llm.LOG.clear()
        await cli_mod.run_cli(s, svc)
    asyncio.run(t())
    out = capsys.readouterr().out
    assert fake_page == [URL, "http://blocked.local/"] and "RISPOSTA-FINTA" in out and "Indirizzo non consentito" in out
    assert "breve" in str(fake_llm.LOG[0]["messages"])


def test_api_summarize_url(fake_page, tmp_path):
    async def t(c, svc):
        r = await c.post("/v1/summarize", headers=A, data={"url": URL, "instruction": "breve"})
        assert r.status_code == 200 and r.json()["summary"] == "RISPOSTA-FINTA"
        sid = r.json()["session_id"]
        fake_llm.LOG.clear()
        await c.post("/v1/chat", json={"message": "dimmi di piu'", "session_id": sid}, headers=A)
        assert f"[Pagina web: {URL}] breve" in str(fake_llm.LOG[0]["messages"])
        blocked = await c.post("/v1/summarize", headers=A, data={"url": "http://blocked.local/"})
        assert blocked.status_code == 422 and "non consentito" in blocked.json()["detail"]
        assert (await c.post("/v1/summarize", headers=A, data={"instruction": "x"})).status_code == 422   # ne' file ne' url
        both = await c.post("/v1/summarize", headers=A, files={"file": ("n.txt", b"x")}, data={"url": URL})
        assert both.status_code == 422
        assert (await c.post("/v1/summarize", headers=A, data={"url": "ftp://x/y"})).status_code == 422
    with_api(t)
