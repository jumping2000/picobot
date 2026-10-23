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
        await gw.on_document(update("a.txt"), ctx)
        assert replies[-1] == "RISPOSTA-FINTA"
        assert not list((s.data_dir / "inbox").glob("*"))      # file cancellato dopo l'uso
        assert "in 3 punti" in str(fake_llm.LOG[-1]["messages"])  # didascalia = istruzioni
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
