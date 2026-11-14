"""Interruttore code.allow_code: con false nessun canale esegue codice, qualunque approvazione."""

import asyncio

import pytest

from picobot.config import Settings
from picobot.context import RunCtx
from picobot.tools.sandbox import CODE_DISABLED, NOT_ALLOWED, _execute


def _run(s: Settings, ctx: RunCtx | None) -> str:
    return asyncio.run(_execute(s, ctx, "print(1)", "python"))


def test_code_disabled_text():
    assert CODE_DISABLED == "Esecuzione di codice disattivata dalla configurazione (code.allow_code: false)."


def test_disabled_does_not_ask_confirm(tmp_path):
    calls = []

    async def confirm(code, lang):
        calls.append(code)
        return True

    s = Settings(workspace_dir=tmp_path, allow_code=False)
    assert _run(s, RunCtx("u", "telegram", confirm=confirm)) == CODE_DISABLED
    assert calls == []


@pytest.mark.parametrize("ctx", [
    RunCtx("u", "api", pre_approved=True),
    RunCtx("u", "schedule"),
    None,
])
def test_disabled_overrides_everything(tmp_path, ctx):
    s = Settings(workspace_dir=tmp_path, allow_code=False)
    assert _run(s, ctx) == CODE_DISABLED


def test_enabled_pre_approved_runs(tmp_path):
    s = Settings(workspace_dir=tmp_path, allow_code=True)
    assert _run(s, RunCtx("u", "api", pre_approved=True)).startswith("exit=0")


def test_enabled_without_approval_not_allowed(tmp_path):
    s = Settings(workspace_dir=tmp_path, allow_code=True)
    assert _run(s, RunCtx("u", "schedule")) == NOT_ALLOWED
