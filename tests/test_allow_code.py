"""Interruttore code.allow_code: con false nessun canale esegue codice, qualunque approvazione."""

import asyncio
import logging

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


# ---------- conferma unica per richiesta e log delle esecuzioni ----------
def _confirm(answer: bool):
    calls = []

    async def confirm(code, lang):
        calls.append(code)
        return answer
    return calls, confirm


def _run_many(s: Settings, ctx: RunCtx, n: int) -> list[str]:
    async def go():
        return [await _execute(s, ctx, f"print({i})", "python") for i in range(n)]
    return asyncio.run(go())


def test_confirm_once_per_request(tmp_path):
    calls, confirm = _confirm(True)
    s = Settings(workspace_dir=tmp_path)
    outs = _run_many(s, RunCtx("u", "telegram", confirm=confirm), 3)
    assert all(o.startswith("exit=0") for o in outs), outs
    assert calls == ["print(0)"]                       # una sola conferma, con il primo codice
    _run_many(s, RunCtx("u", "telegram", confirm=confirm), 1)
    assert len(calls) == 2                             # richiesta nuova = ctx nuovo: chiede di nuovo


def test_refusal_applies_to_whole_request(tmp_path):
    calls, confirm = _confirm(False)
    outs = _run_many(Settings(workspace_dir=tmp_path), RunCtx("u", "cli", confirm=confirm), 2)
    assert all("RIFIUTATO" in o for o in outs) and len(calls) == 1


def test_repeated_refusal_is_logged_as_already_refused(tmp_path, caplog):
    caplog.set_level(logging.INFO, logger="picobot.tools.sandbox")
    _, confirm = _confirm(False)
    _run_many(Settings(workspace_dir=tmp_path), RunCtx("u", "telegram", confirm=confirm), 3)
    assert caplog.text.count("motivo=rifiutato dall'utente") == 1
    assert caplog.text.count("motivo=gia' rifiutato in questa richiesta") == 2


def test_refusal_adds_one_notice_for_the_user(tmp_path):
    _, confirm = _confirm(False)
    ctx = RunCtx("u", "telegram", confirm=confirm)
    _run_many(Settings(workspace_dir=tmp_path), ctx, 3)
    assert ctx.notices == ["⚠️ Codice non eseguito: conferma negata o scaduta."]
    off = RunCtx("u", "api", pre_approved=True)
    _run(Settings(workspace_dir=tmp_path, allow_code=False), off)
    assert off.notices == ["⚠️ Codice non eseguito: code.allow_code e' disattivato."]
    ok = RunCtx("u", "api", pre_approved=True)
    _run(Settings(workspace_dir=tmp_path), ok)
    assert ok.notices == []


def test_max_runs_still_applies_after_approval(tmp_path):
    calls, confirm = _confirm(True)
    outs = _run_many(Settings(workspace_dir=tmp_path, code_max_runs=2), RunCtx("u", "telegram", confirm=confirm), 3)
    assert [o.startswith("exit=0") for o in outs] == [True, True, False]
    assert "limite raggiunto (2" in outs[2] and len(calls) == 1


def test_executions_and_refusals_are_logged(tmp_path, caplog):
    caplog.set_level(logging.INFO, logger="picobot.tools.sandbox")
    _run(Settings(workspace_dir=tmp_path), RunCtx("u", "api", pre_approved=True))
    _run(Settings(workspace_dir=tmp_path, allow_code=False), RunCtx("u", "api", pre_approved=True))
    _run(Settings(workspace_dir=tmp_path), RunCtx("u", "schedule"))
    text = caplog.text
    assert "Codice: utente=u canale=api tipo=python esecuzione 1/6 exit=0" in text
    assert "Codice rifiutato: utente=u canale=api tipo=python motivo=disattivato" in text
    assert "Codice rifiutato: utente=u canale=schedule tipo=python motivo=non consentito" in text
    assert "print(1)" not in text                     # il codice non finisce nel log
