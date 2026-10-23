"""Documento della richiesta: read_document (ComplexTeam) e summarize_document (router)."""
import asyncio

import pytest

import fake_llm
from picobot.config import Settings
from picobot.context import RunCtx, reset_ctx, set_ctx
from picobot.service import PicoBotService
from picobot.tools.documents import make_read_tools, make_summary_tools


def txt(tmp_path, content, name="a.txt"):
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return p


def run_in_ctx(ctx, fn, *args):
    async def go():
        tok = set_ctx(ctx)
        try:
            return await fn(*args)
        finally:
            reset_ctx(tok)
    return asyncio.run(go())


@pytest.fixture(scope="module")
def svc():
    s = PicoBotService(Settings())
    asyncio.run(s.start())
    return s


def summarize_tool(svc):
    return make_summary_tools(svc.s, svc.doc_flow)[0]


def test_read_document_chunks_and_marks_untrusted(tmp_path):
    read = make_read_tools(Settings())[0]
    ctx = RunCtx("u", "t", document=txt(tmp_path, "a" * 45000), document_name="a.txt")
    first, third = run_in_ctx(ctx, read, 0), run_in_ctx(ctx, read, 40000)
    assert "<documento" in first and "NON FIDATO" in first and "inizio=20000" in first
    assert "a" * 5000 in third and "inizio=" not in third.split("</documento>")[1]


def test_document_tools_without_document(svc):
    read = make_read_tools(Settings())[0]
    assert "nessun documento" in run_in_ctx(RunCtx("u", "t"), read, 0).lower()
    assert "nessun documento" in run_in_ctx(RunCtx("u", "t"), summarize_tool(svc), "").lower()
    assert "nessun documento" in run_in_ctx(None, read, 0).lower()


def test_summarize_document_tool(svc, tmp_path):
    ctx = RunCtx("u", "t", document=txt(tmp_path, "contenuto"), document_name="n.txt")
    fake_llm.LOG.clear()
    assert run_in_ctx(ctx, summarize_tool(svc), "in 3 punti") == "RISPOSTA-FINTA"
    assert "in 3 punti" in str(fake_llm.LOG[-1]["messages"]) and "n.txt" in str(fake_llm.LOG[-1]["messages"])


def test_unreadable_document_message(svc, tmp_path):     # Review Focus 2
    ctx = RunCtx("u", "t", document=txt(tmp_path, "   ", "vuoto.txt"), document_name="vuoto.txt")
    assert "Nessun testo" in run_in_ctx(ctx, summarize_tool(svc), "")
    assert "Nessun testo" in run_in_ctx(ctx, make_read_tools(Settings())[0], 0)


def test_doc_chunk_default():
    assert Settings().doc_chunk_chars == 100000
