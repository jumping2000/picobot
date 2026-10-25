"""Profilo personalizzato ed entity memory: solo il router scrive, privati per utente."""

import asyncio

import fake_llm
import pytest

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


# ---------------- /memory e /forget completi (Task 8) ----------------
from picobot.channels.common import format_memory_report   # noqa: E402
from picobot.service import MemoryReport                    # noqa: E402


def test_memory_report_and_forget_everything(svc):           # Review Focus 3, 4
    ask(svc, "ricorda che mi chiamo Gianpi", "m8")
    ask(svc, "seguo AAPL e ENI", "m8")
    ask(svc, "lavoro al progetto Harbor", "m8")
    r = asyncio.run(svc.memory_report("m8"))
    assert r.memories and r.profile["titoli_seguiti"] == "AAPL, ENI" and r.profile["lingua"] == "italiano"
    assert r.entities[0][:2] == ("Harbor", "project")
    assert "user_id" not in r.profile
    assert asyncio.run(svc.memory_report("m8-altro")) == MemoryReport([], {}, [])
    asyncio.run(svc.forget("m8"))
    assert asyncio.run(svc.memory_report("m8")) == MemoryReport([], {}, [])
    fake_llm.LOG.clear()
    ask(svc, "ciao", "m8")
    sp = system_prompt(fake_llm.LOG[0])
    assert "AAPL" not in sp and "Harbor" not in sp


def test_forget_raises_if_learnings_fail(svc, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("db non disponibile")
    monkeypatch.setattr(svc.team.db, "delete_user_learnings", boom)
    import pytest as _pt
    with _pt.raises(RuntimeError):
        asyncio.run(svc.forget("m8-err"))


def test_format_memory_report():
    text = format_memory_report(MemoryReport(["Si chiama Gianpi"], {"titoli_seguiti": "AAPL, ENI"},
                                             [("Harbor", "project", "migrazione rete")]))
    assert "Memorie" in text and "Profilo" in text and "Entita'" in text
    assert "titoli seguiti: AAPL, ENI" in text and "Harbor (project): migrazione rete" in text
    assert format_memory_report(MemoryReport([], {}, [])) == "Non ho memorie su di te."
