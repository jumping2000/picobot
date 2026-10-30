"""Struttura v0.5: router -> SimpleTeam (Web, Finance, Coder) / ComplexTeam / workflow riassunti."""

import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

import fake_llm
import pytest

from picobot import prompts
from picobot.agents import MESI
from picobot.config import Settings
from picobot.context import RunCtx
from picobot.service import PicoBotService
from picobot.skills import SkillRegistry
from picobot.scheduler import Scheduler
from picobot.team import build_router
from picobot.workflows.doc_summary import build_doc_workflow


def names(x):
    return {getattr(t, "__name__", getattr(t, "name", "")) for t in (x.tools or [])}


def member(team, name):
    return next(m for m in team.members if m.name == name)


def system_prompt(body):
    return next(
        m["content"] for m in body["messages"] if m["role"] in ("system", "developer")
    )


def tool_names(body):
    return {t["function"]["name"] for t in body.get("tools") or []}


@pytest.fixture
def s(tmp_path):
    return Settings(
        data_dir=tmp_path / "d",
        workspace_dir=tmp_path / "w",
        skills_dir=tmp_path / "skills",
    )


@pytest.fixture(scope="module")
def svc():
    sv = PicoBotService(Settings())
    asyncio.run(sv.start())
    return sv


def ask(svc, text, user, sid=None):
    return asyncio.run(
        svc.ask(
            text,
            user_id=user,
            session_id=sid or f"{user}-{text[:10]}",
            ctx=RunCtx(user, "t"),
        )
    )


def test_router_structure(s):
    r = build_router(s, SkillRegistry(s), doc_flow=build_doc_workflow(s))
    assert [m.name for m in r.members] == [
        "SimpleTeam",
        "ComplexTeam",
    ] and "summarize_document" in names(r)
    simple = member(r, "SimpleTeam")
    assert [m.name for m in simple.members] == ["Web", "Finance", "Coder"]
    assert simple.model.id == s.llm_model_id and all(
        m.model.id == s.llm_model_id for m in simple.members
    )
    assert {
        "save_text_file",
        "deliver_file",
        "run_python",
        "save_python_file",
    } <= names(member(simple, "Coder"))
    assert simple.skills is None and all(m.skills is None for m in simple.members)


def test_router_has_schedule_tools_and_rule(s):
    r = build_router(s, scheduler=Scheduler(s, run_fn=None))
    assert {"schedule_task", "list_scheduled_tasks"} <= names(r)
    text = " ".join(r.instructions())
    assert "schedule_task" in text and "pagine web" in text
    assert "una tantum" in text   # "domani alle 8": niente task annuale, lo si dice all'utente


def _tree(x):
    yield x
    for m in getattr(x, "members", None) or []:
        yield from _tree(m)


def test_every_agent_and_team_knows_current_date(s):
    r = build_router(s, SkillRegistry(s), doc_flow=build_doc_workflow(s))
    nodes = list(_tree(r))
    assert len(nodes) == 10   # router, SimpleTeam (+3), ComplexTeam (+4)
    # la data e' la prima istruzione, ricalcolata a ogni richiesta; niente "The current time is" in fondo al prompt
    assert [n.name for n in nodes if n.add_datetime_to_context or not n.instructions()[0].startswith("Oggi è ")] == []
    assert all("non eseguire codice per ottenerle" in p for p in (prompts.CODER, prompts.ANALYST))


def test_today_line_in_italian(s, monkeypatch):
    import picobot.agents

    class FakeDatetime:
        @staticmethod
        def now(tz):
            return datetime(2026, 10, 30, 13, 35, tzinfo=tz)

    monkeypatch.setattr(picobot.agents, "datetime", FakeDatetime)
    first = build_router(s).instructions()[0]
    assert first.startswith("Oggi è venerdì 30 ottobre 2026, ore 13:35 (Europe/Rome).")
    assert "'oggi'" in first and "'ieri'" in first


def test_yfinance_agents_know_index_tickers(s):
    """Senza elenco il modello inventa i simboli degli indici (^FTMIE, FTSE.MI -> 404)."""
    from agno.tools.yfinance import YFinanceTools

    r = build_router(s, SkillRegistry(s), doc_flow=build_doc_workflow(s))
    yf = [n for n in _tree(r) if any(isinstance(t, YFinanceTools) for t in n.tools or [])]
    assert [n.name for n in yf] == ["Finance", "Analyst"]
    assert all("FTSE MIB=FTSEMIB.MI" in " ".join(n.instructions()) for n in yf)


def test_web_agents_search_one_engine_at_a_time(s):
    """Web e Researcher usano la ricerca a cascata, non WebSearchTools (motori in parallelo, ordine casuale)."""
    from agno.tools.websearch import WebSearchTools

    r = build_router(s, SkillRegistry(s), doc_flow=build_doc_workflow(s))
    web = [n for n in _tree(r) if "web_search" in names(n)]
    assert [n.name for n in web] == ["Web", "Researcher"]
    assert all("search_news" in names(n) for n in web)
    assert not [n.name for n in _tree(r) if any(isinstance(t, WebSearchTools) for t in n.tools or [])]


def test_every_model_call_sees_todays_date(svc):
    ask(svc, "cerca le notizie di oggi su Stellantis", "dt")
    now = datetime.now(ZoneInfo(svc.s.timezone))
    today = f"{now.day} {MESI[now.month - 1]} {now.year}"
    assert len(fake_llm.LOG) >= 3
    # in cima: al piu' dopo il ruolo dell'agente, prima di team, memorie e riassunto
    assert [tool_names(b) for b in fake_llm.LOG
            if today not in system_prompt(b)[:400] or "The current time is" in system_prompt(b)] == []


def test_router_prompt_explicit_rule(s):
    text = " ".join(build_router(s).instructions())
    assert all(
        k in text
        for k in ("SimpleTeam", "ComplexTeam", "summarize_document", "esplicitamente")
    )


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
    lead = [
        b
        for b in fake_llm.LOG
        if "delegate_task_to_member" in tool_names(b)
        and "summarize_document" not in tool_names(b)
    ]
    assert lead and "Harbor" in system_prompt(lead[0])
    assert not ({"update_profile", "remember_about"} & tool_names(lead[0]))


# ---------------- ComplexTeam (Task 5) ----------------
from picobot.agents import build_complex_team
from picobot.storage import make_db


def probe(a: int, b: int) -> int:
    """Tool MCP finto."""
    return a + b


def test_complex_roles(s):
    ct = build_complex_team(s, SkillRegistry(s), mcp_tools=[probe], db=make_db(s))
    m = {x.name: x for x in ct.members}
    assert ct.model.id == s.strong_model_id and all(
        x.model.id == s.strong_model_id for x in ct.members
    )
    assert {
        "run_python",
        "run_node",
        "save_text_file",
        "deliver_file",
        "read_document",
    } <= names(m["Writer"])
    assert {"run_python", "run_node", "read_document"} <= names(
        m["Analyst"]
    ) and "deliver_file" not in names(m["Analyst"])
    assert not (
        {"run_python", "run_node", "deliver_file", "save_text_file"}
        & names(m["Critic"])
    )
    assert not ({"run_python", "run_node", "deliver_file"} & names(m["Researcher"]))
    assert all(probe in x.tools for x in ct.members) and ct.skills is not None
    assert (
        ct.db is not None and ct.learning is not None
    )  # leader: profilo ed entita' in sola lettura


def test_complex_prompts_split_roles():
    from picobot import prompts

    assert "Writer" in prompts.COMPLEX_LEADER and "Analyst" in prompts.COMPLEX_LEADER
    assert (
        "deliver_file" in prompts.WRITER
        and "save_text_file" in prompts.WRITER
        and "run_node" in prompts.WRITER
    )
    assert "deliver_file" not in prompts.ANALYST and "Writer" in prompts.ANALYST
