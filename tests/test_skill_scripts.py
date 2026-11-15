"""run_skill_script: gli script delle skill girano nel sandbox di PicoBot, con le stesse regole di run_python."""

import asyncio
import shutil

import pytest

from picobot.config import Settings
from picobot.context import RunCtx, reset_ctx, set_ctx
from picobot.skills import SkillRegistry
from picobot.tools.sandbox import CODE_DISABLED, NOT_ALLOWED, make_skill_script_tools

HELLO = (
    "import os, sys\n"
    "print('ARGS', sys.argv[1:])\n"
    "print('KEY', os.environ.get('OPENROUTER_API_KEY'))\n"
    "print('CWD', os.path.basename(os.getcwd()))\n"
)


def mk_skill(root, name="demo", scripts=None):
    d = root / name
    (d / "scripts").mkdir(parents=True)
    (d / "SKILL.md").write_text(f"---\nname: {name}\ndescription: Demo\n---\n# {name}\n", encoding="utf-8")
    for fname, code in (scripts or {"hello.py": HELLO}).items():
        (d / "scripts" / fname).write_text(code, encoding="utf-8")


def setup(tmp_path, scripts=None, **kw):
    skills = tmp_path / "skills"
    skills.mkdir(parents=True)
    mk_skill(skills, scripts=scripts)
    s = Settings(skills_dir=skills, workspace_dir=tmp_path / "ws", data_dir=tmp_path / "d", **kw)
    [tool] = make_skill_script_tools(s, SkillRegistry(s))
    return s, tool


def call(ctx, tool, *args):
    async def go():
        tok = set_ctx(ctx)
        try:
            return await tool(*args)
        finally:
            reset_ctx(tok)
    return asyncio.run(go())


def pre() -> RunCtx:
    return RunCtx("u", "api", pre_approved=True)


def test_runs_in_sandbox_with_args(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-segreta")
    _, tool = setup(tmp_path)
    out = call(pre(), tool, "demo", "hello.py", ["a", "b c"])
    assert out.startswith("exit=0"), out
    assert "ARGS ['a', 'b c']" in out and "KEY None" in out and "CWD ws" in out


def test_confirm_shows_script_source_once(tmp_path):
    seen = []

    async def yes(code, lang):
        seen.append((code, lang))
        return True

    _, tool = setup(tmp_path)
    ctx = RunCtx("u", "telegram", confirm=yes)
    call(ctx, tool, "demo", "hello.py", ["x"])
    call(ctx, tool, "demo", "hello.py")
    [(preview, lang)] = seen
    assert lang == "python" and "[skill demo] hello.py x" in preview and "sys.argv[1:]" in preview


def test_counts_toward_max_runs(tmp_path):
    _, tool = setup(tmp_path, code_max_runs=1)
    ctx = pre()
    assert call(ctx, tool, "demo", "hello.py").startswith("exit=0")
    assert "limite raggiunto" in call(ctx, tool, "demo", "hello.py")


def test_same_gate_as_run_python(tmp_path):
    _, tool = setup(tmp_path)
    assert call(RunCtx("u", "schedule"), tool, "demo", "hello.py") == NOT_ALLOWED
    _, off = setup(tmp_path / "off", allow_code=False)
    assert call(pre(), off, "demo", "hello.py") == CODE_DISABLED


@pytest.mark.parametrize("skill, script, expected", [
    ("nessuna", "hello.py", "non trovata"),
    ("demo", "manca.py", "non trovato"),
    ("demo", "../SKILL.md", "non trovato"),
    ("demo", "run.sh", "solo .py"),
])
def test_rejects_bad_requests(tmp_path, skill, script, expected):
    _, tool = setup(tmp_path, scripts={"hello.py": HELLO, "run.sh": "echo hi"})
    ctx = pre()
    assert expected in call(ctx, tool, skill, script)
    assert ctx.runs == 0                               # un rifiuto non consuma esecuzioni


def test_skills_disabled(tmp_path):
    _, tool = setup(tmp_path, enable_skills=False)
    assert "skill sono disattivate" in call(pre(), tool, "demo", "hello.py")


@pytest.mark.skipif(shutil.which("node") is None, reason="node non installato")
def test_node_script(tmp_path):
    _, tool = setup(tmp_path, scripts={"hi.js": "console.log('NODE', process.argv.slice(2).join(','))"})
    out = call(pre(), tool, "demo", "hi.js", ["1", "2"])
    assert out.startswith("exit=0") and "NODE 1,2" in out, out
