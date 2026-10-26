"""Traccia del percorso di una richiesta (TRACE_ENABLED): una riga JSON per richiesta in data/trace.jsonl.

Il percorso viene dal risultato del run di Agno: team e agenti coinvolti (member_responses annidati), tool chiamati
con argomenti ed esito, durata e token. Testi troncati a 200 caratteri su una riga.
"""
import json
import os
from datetime import datetime, timezone

from .config import Settings
from .context import RunCtx

CUT = 200
_MIB = 1024 * 1024


def _cut(x, n: int = CUT) -> str:
    text = x if isinstance(x, str) else json.dumps(x, ensure_ascii=False, default=str)
    return " ".join(text.split())[:n]


def _walk(run, depth: int, path: list[dict]) -> None:
    m = getattr(run, "metrics", None)
    path.append({"depth": depth, "agent": getattr(run, "team_name", None) or getattr(run, "agent_name", None) or "?",
                 "duration_s": round(getattr(m, "duration", None) or 0.0, 2),
                 "tokens": getattr(m, "total_tokens", None) or 0})
    for t in getattr(run, "tools", None) or []:
        path.append({"depth": depth, "tool": t.tool_name, "args": _cut(t.tool_args or {}),
                     "result": _cut("" if t.result is None else t.result), "error": bool(t.tool_call_error)})
    for member in getattr(run, "member_responses", None) or []:
        _walk(member, depth + 1, path)


def build_trace(out, *, text: str, ctx: RunCtx, session_id: str, target: str, duration_s: float,
                error: BaseException | None = None) -> dict:
    path: list[dict] = []
    if out is not None:
        _walk(out, 0, path)
    status = getattr(out, "status", None)
    rec = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"), "user": ctx.user_id,
           "channel": ctx.channel, "session": session_id, "target": target, "request": _cut(text),
           "status": "error" if error is not None else str(getattr(status, "value", status)).lower(),
           "duration_s": round(duration_s, 2), "tokens": sum(n["tokens"] for n in path if "agent" in n),
           "path": path, "files": [f.name for f in ctx.outputs]}
    if error is not None:
        rec["error"] = _cut(f"{type(error).__name__}: {error}")
    return rec


def write_trace(s: Settings, rec: dict) -> None:
    f = s.trace_file
    f.parent.mkdir(parents=True, exist_ok=True)
    if f.is_file() and f.stat().st_size > s.trace_max_mb * _MIB:
        os.replace(f, f.with_name(f.name + ".1"))
    with f.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


def last_trace(s: Settings, user_id: str) -> dict | None:
    try:
        lines = s.trace_file.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return None
    for line in reversed(lines):
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if isinstance(rec, dict) and rec.get("user") == user_id:
            return rec
    return None


def format_trace(rec: dict) -> str:
    out = [f"{rec['ts'][:16]} {rec['channel']} | {rec['duration_s']:.1f}s | {rec['tokens']} token | {rec['status']}",
           f"Richiesta: {rec['request']}"]
    for n in rec["path"]:
        pad = "  " * n["depth"]
        if "agent" in n:
            out.append(f"{pad}{n['agent']} ({n['duration_s']:.1f}s, {n['tokens']} tok)")
        else:
            out.append(f"{pad}  - {n['tool']}({n['args']}) -> {n['result']}" + (" [ERRORE]" if n["error"] else ""))
    if rec["files"]:
        out.append("File: " + ", ".join(rec["files"]))
    if rec.get("error"):
        out.append(f"Errore: {rec['error']}")
    return "\n".join(out)


def summary_line(rec: dict) -> str:
    agents = list(dict.fromkeys(n["agent"] for n in rec["path"] if "agent" in n))
    tools = list(dict.fromkeys(n["tool"] for n in rec["path"] if "tool" in n))
    return (f"trace {rec['channel']}/{rec['user']} {rec['duration_s']:.1f}s {rec['tokens']}tok {rec['status']}: "
            f"{' > '.join(agents)} [{', '.join(tools)}]")
