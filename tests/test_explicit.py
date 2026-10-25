"""Richiamo esplicito: target simple/complex salta il router e lo scambio resta nella sessione del router."""

import asyncio

import fake_llm
import httpx
import pytest

from picobot.channels.api import create_app
from picobot.config import Settings
from picobot.context import RunCtx
from picobot.service import PicoBotService


@pytest.fixture(scope="module")
def svc():
    sv = PicoBotService(Settings())
    asyncio.run(sv.start())
    return sv


def tool_names(b):
    return {t["function"]["name"] for t in b.get("tools") or []}


def ask(svc, text, user, sid, target="auto"):
    return asyncio.run(
        svc.ask(
            text, user_id=user, session_id=sid, ctx=RunCtx(user, "t"), target=target
        )
    )


@pytest.mark.parametrize(
    "target,leader_tool", [("simple", None), ("complex", "list_skills")]
)
def test_target_skips_router(svc, target, leader_tool):
    fake_llm.LOG.clear()
    ask(svc, "quotazione AAPL", "x1", f"skip-{target}", target=target)
    assert fake_llm.LOG and not any(
        "summarize_document" in tool_names(b) for b in fake_llm.LOG
    )
    first = tool_names(fake_llm.LOG[0])
    assert "delegate_task_to_member" in first and (
        (leader_tool in first) if leader_tool else ("list_skills" not in first)
    )


def test_target_recorded_and_router_session_intact(svc):  # Review Focus 1
    ask(svc, "ciao", "x2", "sess")
    ask(svc, "quotazione AAPL", "x2", "sess", target="simple")
    fake_llm.LOG.clear()
    ask(svc, "e domani?", "x2", "sess")
    seen = str(fake_llm.LOG[0]["messages"])
    assert "ciao" in seen and "[/simple] quotazione AAPL" in seen


def test_unknown_target(svc):
    with pytest.raises(ValueError):
        ask(svc, "x", "x3", "s3", target="nope")


def test_api_target():
    async def go():
        s = Settings()
        sv = PicoBotService(s)
        await sv.start()
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=create_app(s, sv)), base_url="http://t"
        ) as c:
            h = {"Authorization": "Bearer tok-a"}
            bad = await c.post(
                "/v1/chat", json={"message": "x", "target": "nope"}, headers=h
            )
            fake_llm.LOG.clear()
            ok = await c.post(
                "/v1/chat",
                json={"message": "quotazione AAPL", "target": "simple"},
                headers=h,
            )
            return (
                bad.status_code,
                ok.status_code,
                [tool_names(b) for b in fake_llm.LOG],
            )

    bad, ok, calls = asyncio.run(go())
    assert (
        bad == 422 and ok == 200 and not any("summarize_document" in c for c in calls)
    )
