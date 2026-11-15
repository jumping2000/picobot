"""Logging: formato text/json, contesto della richiesta in ogni riga, hook sui tool, esito delle richieste."""
import asyncio
import io
import json
import logging

import pytest

from pydantic import ValidationError

from picobot.config import Settings
from picobot.context import RunCtx, reset_ctx, set_ctx
from picobot.logs import JsonFormatter, RequestContextFilter, TEXT_FORMAT, log_tool_call, setup_logging


def _emit(formatter: logging.Formatter, ctx: RunCtx | None, msg="ciao", exc=False, **extra) -> str:
    stream = io.StringIO()
    h = logging.StreamHandler(stream)
    h.setFormatter(formatter)
    h.addFilter(RequestContextFilter())
    lg = logging.getLogger("picobot.test_logging")
    lg.addHandler(h)
    lg.propagate = False
    token = set_ctx(ctx)
    try:
        if exc:
            try:
                raise ValueError("rotto")
            except ValueError:
                lg.exception(msg)
        else:
            lg.warning(msg, extra=extra or None)
    finally:
        reset_ctx(token)
        lg.removeHandler(h)
        lg.propagate = True
    return stream.getvalue()


def test_text_format_carries_request_context():
    ctx = RunCtx("42", "telegram")
    line = _emit(logging.Formatter(TEXT_FORMAT), ctx)
    assert f"[{ctx.req_id} telegram/42] ciao" in line
    assert "[- -/-] ciao" in _emit(logging.Formatter(TEXT_FORMAT), None)


def test_json_format_is_one_valid_object_per_event():
    ctx = RunCtx("7", "email")
    rec = json.loads(_emit(JsonFormatter(), ctx, "evento", tool="run_python"))
    assert rec["msg"] == "evento" and rec["level"] == "WARNING" and rec["logger"] == "picobot.test_logging"
    assert (rec["req"], rec["user"], rec["channel"], rec["tool"]) == (ctx.req_id, "7", "email", "run_python")
    assert rec["ts"].endswith("+00:00")
    err = json.loads(_emit(JsonFormatter(), None, "fallito", exc=True))
    assert "ValueError: rotto" in err["exc"] and err["req"] == "-"


def test_req_id_differs_per_request():
    assert RunCtx("1", "cli").req_id != RunCtx("1", "cli").req_id


@pytest.fixture
def restore_logging():
    root = logging.getLogger()
    handlers, level = root.handlers[:], root.level
    yield
    root.handlers[:] = handlers
    root.setLevel(level)


def test_setup_logging_levels_and_agno(restore_logging):
    setup_logging("DEBUG", "json")
    root = logging.getLogger()
    assert root.level == logging.DEBUG and isinstance(root.handlers[0].formatter, JsonFormatter)
    assert logging.getLogger("httpx").level == logging.WARNING      # il token Telegram e' negli URL
    agno = logging.getLogger("agno")
    assert agno.propagate and not agno.handlers                      # stesso formato delle nostre righe
    setup_logging("ERROR", "text")
    assert logging.getLogger("httpx").level == logging.ERROR
    assert root.handlers[0].level == logging.ERROR


def test_log_level_config(monkeypatch):
    assert Settings(log_level="debug", log_format="JSON").log_level == "DEBUG"
    monkeypatch.setenv("LOG_LEVEL", "verbose")
    with pytest.raises(ValidationError):
        Settings()


def _call(fn, **args):
    out = log_tool_call("mio_tool", fn, args)
    return asyncio.run(out) if asyncio.iscoroutine(out) else out


def test_tool_hook_logs_success_without_arguments(caplog):
    caplog.set_level(logging.DEBUG, logger="picobot.tools")
    assert _call(lambda code: "fatto", code="SEGRETO") == "fatto"

    async def aio(code):
        return "async-fatto"
    assert _call(aio, code="SEGRETO") == "async-fatto"
    lines = [r.getMessage() for r in caplog.records]
    assert len(lines) == 2 and all("Tool: nome=mio_tool parametri=code" in l and "risultato=" in l for l in lines)
    assert "SEGRETO" not in caplog.text


def test_tool_hook_logs_failure_and_reraises(caplog):
    caplog.set_level(logging.INFO, logger="picobot.tools")

    def boom(x):
        raise RuntimeError("niente rete")

    async def aboom(x):
        raise RuntimeError("niente rete async")
    with pytest.raises(RuntimeError):
        _call(boom, x=1)
    with pytest.raises(RuntimeError):
        _call(aboom, x=1)
    warns = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warns) == 2 and "Tool fallito: nome=mio_tool" in warns[0].getMessage()
    assert "RuntimeError: niente rete async" in warns[1].getMessage()
    assert not [r for r in caplog.records if r.levelno == logging.DEBUG]   # a INFO i successi non compaiono


def test_request_outcome_logged_without_trace(caplog):
    """Con il trace spento la riga di esito c'e' comunque, e tool e richiesta hanno lo stesso req."""
    import fake_llm  # noqa: F401  server LLM finto (conftest)
    from picobot.service import PicoBotService

    caplog.set_level(logging.DEBUG)
    caplog.handler.addFilter(RequestContextFilter())

    async def go():
        svc = PicoBotService(Settings(trace_enabled=False))
        await svc.start()
        try:
            async def yes(code, language):
                return True
            ctx = RunCtx("1", "telegram", confirm=yes)
            await svc.ask("scrivi un programma", user_id="1", session_id="log1", ctx=ctx)
            return ctx
        finally:
            await svc.stop()
    ctx = asyncio.run(go())
    done = [r for r in caplog.records if r.getMessage().startswith("Richiesta: ")]
    assert len(done) == 1 and "esito=completed" in done[0].getMessage() and done[0].req == ctx.req_id
    tools = [r for r in caplog.records if r.getMessage().startswith("Tool: nome=run_python")]
    assert tools and tools[0].req == ctx.req_id
