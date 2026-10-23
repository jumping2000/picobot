"""Struttura v0.5: router -> SimpleTeam (Web, Finance, Coder) / ComplexTeam / workflow riassunti."""
import asyncio

import pytest

import fake_llm
from picobot.config import Settings
from picobot.context import RunCtx
from picobot.service import PicoBotService
from picobot.skills import SkillRegistry
from picobot.team import build_router
from picobot.workflows.doc_summary import build_doc_workflow


def names(x):
    return {getattr(t, "__name__", getattr(t, "name", "")) for t in (x.tools or [])}


def member(team, name):
    return next(m for m in team.members if m.name == name)


def system_prompt(body):
    return next(m["content"] for m in body["messages"] if m["role"] in ("system", "developer"))


def tool_names(body):
    return {t["function"]["name"] for t in body.get("tools") or []}


@pytest.fixture
def s(tmp_path):
    return Settings(data_dir=tmp_path / "d", workspace_dir=tmp_path / "w", skills_dir=tmp_path / "skills")


@pytest.fixture(scope="module")
def svc():
    sv = PicoBotService(Settings())
    asyncio.run(sv.start())
    return sv


def ask(svc, text, user, sid=None):
    return asyncio.run(svc.ask(text, user_id=user, session_id=sid or f"{user}-{text[:10]}", ctx=RunCtx(user, "t")))


def test_router_structure(s):
    r = build_router(s, SkillRegistry(s), doc_flow=build_doc_workflow(s))
    assert [m.name for m in r.members] == ["SimpleTeam", "ComplexTeam"] and "summarize_document" in names(r)
    simple = member(r, "SimpleTeam")
    assert [m.name for m in simple.members] == ["Web", "Finance", "Coder"]
    assert simple.model.id == s.llm_model_id and all(m.model.id == s.llm_model_id for m in simple.members)
    assert {"save_text_file", "deliver_file", "run_python", "save_python_file"} <= names(member(simple, "Coder"))
    assert simple.skills is None and all(m.skills is None for m in simple.members)


def test_router_prompt_explicit_rule(s):
    text = " ".join(build_router(s).instructions)
    assert all(k in text for k in ("SimpleTeam", "ComplexTeam", "summarize_document", "esplicitamente"))


def test_finance_sees_followed_tickers_nested(svc):
    ask(svc, "seguo AAPL e ENI", "t4a")
    fake_llm.LOG.clear()
    ask(svc, "quotazione dei miei titoli", "t4a")
    fin = [b for b in fake_llm.LOG if "get_current_stock_price" in tool_names(b)]
    assert fin and "AAPL, ENI" in system_prompt(fin[0])
    assert not ({"update_profile", "remember_about"} & tool_names(fin[0]))


def test_simple_leader_sees_entities(svc):
    ask(svc, "lavoro al progetto Harbor", "t4b")
    fake_llm.LOG.clear()
    ask(svc, "quotazione AAPL", "t4b")
    lead = [b for b in fake_llm.LOG if "delegate_task_to_member" in tool_names(b) and "summarize_document" not in tool_names(b)]
    assert lead and "Harbor" in system_prompt(lead[0])
    assert not ({"update_profile", "remember_about"} & tool_names(lead[0]))
