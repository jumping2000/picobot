"""Tool di schedulazione del router: creano task veri, rifiutano senza un umano, errori come testo."""
import asyncio
from types import SimpleNamespace

import pytest

from picobot.config import Settings
from picobot.context import RunCtx, reset_ctx, set_ctx
from picobot.scheduler import Scheduler
from picobot.tools.schedule import make_schedule_tools


@pytest.fixture
def sch(tmp_path):
    async def fake(*a, **k): return ""
    return Scheduler(Settings(data_dir=tmp_path), run_fn=fake)


@pytest.fixture
def tools(sch):
    return SimpleNamespace(**{f.__name__: f for f in make_schedule_tools(sch.s, sch)})


def call(ctx, fn, *args):
    token = set_ctx(ctx)
    try:
        return asyncio.run(fn(*args))
    finally:
        reset_ctx(token)


def test_schedule_task_creates_task_visible_in_list(sch, tools):
    out = call(RunCtx("u1", "telegram", target="777"), tools.schedule_task, "0 8 * * 1-5", "quotazioni AAPL")
    assert "Task #" in out and "Prossima esecuzione" in out and "Europe/Rome" in out
    [row] = sch.list("u1")
    assert (row["channel"], row["target"], row["cron"], row["prompt"]) == ("telegram", "777", "0 8 * * 1-5", "quotazioni AAPL")
    assert "quotazioni AAPL" in call(RunCtx("u1", "telegram"), tools.list_scheduled_tasks)


def test_target_defaults_to_user_id(sch, tools):
    call(RunCtx("u2", "cli"), tools.schedule_task, "0 8 * * *", "meteo")
    assert sch.list("u2")[0]["target"] == "u2"


@pytest.mark.parametrize("ctx", [None, RunCtx("u3", "schedule")])
def test_schedule_task_refused_without_human_context(sch, tools, ctx):
    assert call(ctx, tools.schedule_task, "0 8 * * *", "x").startswith("Rifiutato")
    assert sch.list("u3") == []


def test_invalid_cron_returns_message_not_exception(sch, tools):
    out = call(RunCtx("u4", "cli"), tools.schedule_task, "*/5 * * * *", "x")
    assert "Intervallo minimo" in out and sch.list("u4") == []


def test_docstring_mentions_timezone_and_min_interval(tools):
    assert "Europe/Rome" in tools.schedule_task.__doc__ and "30 minuti" in tools.schedule_task.__doc__
