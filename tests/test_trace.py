"""Traccia del percorso di una richiesta: struttura, troncamento, file JSONL, formato per /trace."""
from pathlib import Path
from types import SimpleNamespace as NS

from picobot.config import Settings
from picobot.context import OutputFile, RunCtx
from picobot.trace import build_trace, format_trace, last_trace, summary_line, write_trace


def _tool(name, args, result="ok", error=False):
    return NS(tool_name=name, tool_args=args, result=result, tool_call_error=error)


def _run(name, tokens, tools=(), members=(), agent=False):
    return NS(team_name=None if agent else name, agent_name=name if agent else None,
              status=NS(value="completed"), metrics=NS(total_tokens=tokens, duration=0.2),
              tools=list(tools), member_responses=list(members))


def _out():
    finance = _run("Finance", 2, [_tool("get_current_stock_price", {"symbol": "AAPL"}, "187.3")], agent=True)
    simple = _run("SimpleTeam", 4, [_tool("delegate_task_to_member", {"member_id": "finance"})], [finance])
    return _run("PicoBot", 4, [_tool("delegate_task_to_member", {"member_id": "simpleteam"})], [simple])


def _ctx():
    ctx = RunCtx("1", "cli")
    ctx.outputs.append(OutputFile(Path("/x/a.docx"), "a.docx", 3))
    return ctx


def _rec(out=None, text="quotazione AAPL", error=None):
    return build_trace(out if out is not None or error else _out(), text=text, ctx=_ctx(), session_id="s1",
                       target="auto", duration_s=1.5, error=error)


def test_build_trace_flattens_nested_runs():
    rec = _rec()
    runs = [n for n in rec["path"] if "agent" in n]
    assert [n["agent"] for n in runs] == ["PicoBot", "SimpleTeam", "Finance"]
    assert runs[2]["depth"] == 2 and rec["tokens"] == 4 + 4 + 2
    assert rec["files"] == ["a.docx"] and rec["status"] == "completed" and rec["channel"] == "cli"


def test_build_trace_truncates_long_multiline_fields():
    out = _run("PicoBot", 1, [_tool("run_node", {"code": "x\n" * 500}, "y\n" * 500)])
    rec = _rec(out, text="z" * 1000)
    tool = next(n for n in rec["path"] if "tool" in n)
    assert len(tool["args"]) <= 200 and "\n" not in tool["args"]
    assert len(tool["result"]) <= 200 and "\n" not in tool["result"]
    assert len(rec["request"]) <= 200


def test_build_trace_error():
    rec = _rec(error=RuntimeError("boom"))
    assert rec["status"] == "error" and "RuntimeError: boom" in rec["error"] and rec["path"] == []


def test_write_and_last_trace_per_user_skips_bad_lines(tmp_path):
    s = Settings(data_dir=tmp_path)
    write_trace(s, {**_rec(), "user": "a"})
    with s.trace_file.open("a", encoding="utf-8") as f:
        f.write("non json\n")
    write_trace(s, {**_rec(), "user": "b"})
    assert last_trace(s, "a")["user"] == "a"
    assert last_trace(s, "zzz") is None


def test_last_trace_without_file(tmp_path):
    assert last_trace(Settings(data_dir=tmp_path / "nuova"), "a") is None


def test_write_trace_rotates(tmp_path):
    s = Settings(data_dir=tmp_path, trace_max_mb=0)
    write_trace(s, _rec())
    write_trace(s, _rec())
    assert (tmp_path / "trace.jsonl.1").is_file() and s.trace_file.is_file()


def test_format_trace_and_summary():
    rec = _rec()
    text = format_trace(rec)
    assert "Richiesta: quotazione AAPL" in text and "\n    Finance" in text and "delegate_task_to_member(" in text
    assert "File: a.docx" in text
    assert "PicoBot > SimpleTeam > Finance" in summary_line(rec)


def test_trace_disabled_by_default():
    assert Settings().trace_enabled is False
