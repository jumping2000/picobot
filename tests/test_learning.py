"""Profilo personalizzato ed entity memory: solo il router scrive, privati per utente."""
import asyncio

import pytest

import fake_llm
from picobot.config import Settings
from picobot.context import RunCtx
from picobot.service import PicoBotService
from picobot.storage import make_db, make_learning_view


def system_prompt(body):
    return next(m["content"] for m in body["messages"] if m["role"] in ("system", "developer"))


def tool_schemas(body):
    return {t["function"]["name"]: t["function"]["parameters"] for t in body.get("tools") or []}


@pytest.fixture(scope="module")
def svc():
    s = PicoBotService(Settings())
    asyncio.run(s.start())
    return s


def ask(svc, text, user, sid=None):
    return asyncio.run(svc.ask(text, user_id=user, session_id=sid or f"{user}-{text[:12]}", ctx=RunCtx(user, "t")))


def test_router_profile_fields_and_entity_tools(svc):
    fake_llm.LOG.clear()
    ask(svc, "ciao", "l1")
    tools = tool_schemas(fake_llm.LOG[0])
    assert {"lingua", "fuso_orario", "formato_risposta", "titoli_seguiti"} <= set(tools["update_profile"]["properties"])
    assert {"remember_about", "link_entities", "search_entities", "forget"} <= set(tools)


def test_profile_and_entities_saved_and_private(svc):
    ask(svc, "seguo AAPL e ENI", "l2")
    ask(svc, "lavoro al progetto Harbor", "l2")
    fake_llm.LOG.clear()
    ask(svc, "ciao", "l2")
    sp = system_prompt(fake_llm.LOG[0])
    assert "AAPL, ENI" in sp and "Harbor" in sp
    fake_llm.LOG.clear()
    ask(svc, "ciao", "l2-altro")
    sp = system_prompt(fake_llm.LOG[0])
    assert "AAPL" not in sp and "Harbor" not in sp


def test_view_is_read_only(tmp_path):
    s = Settings(data_dir=tmp_path / "d")
    assert make_learning_view(s, make_db(s)).get_tools(user_id="u", session_id="x") == []
