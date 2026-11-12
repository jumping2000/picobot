"""Tool di schedulazione del router: creano task veri, rifiutano senza un umano, errori come testo."""
import asyncio
import sqlite3
from types import SimpleNamespace

import pytest

from picobot.config import Settings
from picobot.context import RunCtx, reset_ctx, set_ctx
from picobot.scheduler import Scheduler, format_schedules
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


def test_schedule_approve_code_runs_with_pre_approved(tmp_path):
    seen = []

    async def fake(prompt, **k):
        seen.append(k["ctx"])
        return "ok"
    sch = Scheduler(Settings(data_dir=tmp_path), run_fn=fake)
    yes = sch.add("u1", "api", "u1", "0 8 * * 1", "con codice", approve_code=True)
    no = sch.add("u1", "api", "u1", "0 9 * * 1", "senza codice")
    asyncio.run(sch.run_now(yes))
    asyncio.run(sch.run_now(no))
    assert seen[0].pre_approved is True and seen[0].channel == "schedule"
    assert seen[1].pre_approved is False and seen[1].channel == "schedule"


def test_schedule_column_migration(tmp_path):
    s = Settings(data_dir=tmp_path)
    s.data_dir.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(s.database_file)
    c.execute("""CREATE TABLE picobot_schedules(
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT NOT NULL, channel TEXT NOT NULL,
        target TEXT NOT NULL, cron TEXT NOT NULL, prompt TEXT NOT NULL,
        created_at TEXT NOT NULL, last_run TEXT, last_result TEXT)""")
    c.execute("INSERT INTO picobot_schedules(user_id,channel,target,cron,prompt,created_at) VALUES(?,?,?,?,?,?)",
              ("u1", "api", "u1", "0 8 * * 1", "vecchio", "2026-01-01T00:00:00"))
    c.commit()
    c.close()

    async def fake(*a, **k): return ""
    sch = Scheduler(s, run_fn=fake)
    assert sch.list("u1")[0]["approve_code"] == 0
    sch.add("u1", "api", "u1", "0 9 * * 1", "nuovo", approve_code=True)
    assert [r["approve_code"] for r in sch.list("u1")] == [0, 1]


def test_format_schedules_marks_code():
    row = {"id": 3, "cron": "0 8 * * 1", "prompt": "report", "last_run": None, "approve_code": 1}
    assert "[0 8 * * 1] [codice]" in format_schedules([row])
    assert "[codice]" not in format_schedules([{**row, "approve_code": 0}])
