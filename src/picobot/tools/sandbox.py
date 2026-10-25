"""Tool per scrivere ed eseguire piccoli programmi (Python, Node), con human-in-the-loop.

- scrittura file: libera, solo in workspace/scripts
- esecuzione: SOLO dopo conferma umana a ogni esecuzione (o approve_code esplicito via API); mai negli schedule
- subprocess separato, env ripulito (niente chiavi API), timeout, limiti CPU/RAM/file, output troncato
- tetto di esecuzioni approvate per richiesta (CODE_MAX_RUNS)
"""
import asyncio
import os
import re
import sys
import uuid
from pathlib import Path

from ..config import Settings
from ..context import RunCtx, get_ctx

_NAME = re.compile(r"^[A-Za-z0-9_\-]{1,60}(\.py)?$")
_MB = 1024 * 1024
_PYTHON_AS_MB = 768

NOT_ALLOWED = ("Esecuzione NON consentita in questo contesto (nessuna conferma umana possibile). "
               "Puoi salvare il codice con save_python_file e mostrarlo all'utente.")


def _limits_for(as_mb: int, fsize_mb: int):
    def apply() -> None:  # eseguito nel figlio, prima dell'exec
        import resource

        resource.setrlimit(resource.RLIMIT_CPU, (60, 60))
        resource.setrlimit(resource.RLIMIT_AS, (as_mb * _MB, as_mb * _MB))
        resource.setrlimit(resource.RLIMIT_FSIZE, (fsize_mb * _MB, fsize_mb * _MB))
    return apply


async def _execute(s: Settings, ctx: RunCtx | None, code: str, language: str) -> str:
    """Gate umano + tetto + esecuzione isolata. language: 'python' | 'node'."""
    if ctx is None or not ctx.can_run_code:
        return NOT_ALLOWED
    if ctx.runs >= s.code_max_runs:
        return (f"Esecuzione rifiutata: limite raggiunto ({s.code_max_runs} esecuzioni approvate per richiesta). "
                "Fermati e riferisci all'utente cosa non funziona.")
    if ctx.confirm is not None and not await ctx.confirm(code, language):
        return "L'utente ha RIFIUTATO l'esecuzione (o nessuna risposta entro il timeout)."
    ctx.runs += 1

    scripts = s.workspace_dir / "scripts"
    scripts.mkdir(parents=True, exist_ok=True)
    script = scripts / f"_run-{uuid.uuid4().hex}{'.py' if language == 'python' else '.js'}"
    script.write_text(code, encoding="utf-8")
    env = {"PATH": os.environ.get("PATH", ""), "HOME": str(s.workspace_dir), "PYTHONIOENCODING": "utf-8"}
    if os.name == "nt":  # senza SYSTEMROOT su Windows node abortisce e Python non importa asyncio
        env["SYSTEMROOT"] = os.environ.get("SYSTEMROOT", "")
    if language == "node":
        if s.node_path:
            env["NODE_PATH"] = s.node_path
        cmd, as_mb = ["node", str(script)], s.code_node_mem_mb
    else:
        cmd, as_mb = [sys.executable, str(script)], _PYTHON_AS_MB
    try:
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd, cwd=str(s.workspace_dir), env=env,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
                preexec_fn=_limits_for(as_mb, 2 * s.max_output_mb) if os.name == "posix" else None,
            )
        except FileNotFoundError:
            return f"Errore: eseguibile '{cmd[0]}' non trovato nel PATH del sandbox."
        try:
            out, _ = await asyncio.wait_for(proc.communicate(), timeout=s.code_timeout_s)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return f"Timeout: esecuzione interrotta dopo {s.code_timeout_s}s."
        text = out.decode("utf-8", "replace")
        if len(text) > s.code_max_output:
            text = text[: s.code_max_output] + "\n... (output troncato)"
        return f"exit={proc.returncode}\n{text}"
    finally:
        script.unlink(missing_ok=True)


def _ensure_dirs(s: Settings) -> Path:
    scripts = s.workspace_dir / "scripts"
    scripts.mkdir(parents=True, exist_ok=True)
    (s.workspace_dir / "outputs").mkdir(parents=True, exist_ok=True)
    return scripts


def make_code_tools(s: Settings) -> list:
    scripts = _ensure_dirs(s)

    def _path(name: str) -> Path:
        if not _NAME.match(name):
            raise ValueError("nome file non valido (solo lettere, numeri, _ e -)")
        return scripts / (name if name.endswith(".py") else f"{name}.py")

    async def save_python_file(filename: str, code: str) -> str:
        """Salva un programma Python nel workspace (non lo esegue).

        Args:
            filename: nome file senza percorso, es. "calcolo_mutuo.py"
            code: codice sorgente completo
        """
        try:
            p = _path(filename)
        except ValueError as e:
            return f"Errore: {e}"
        scripts.mkdir(parents=True, exist_ok=True)
        p.write_text(code, encoding="utf-8")
        return f"Salvato {p.relative_to(s.workspace_dir)}"

    async def run_python(code: str) -> str:
        """Esegue codice Python nel workspace e restituisce stdout/stderr.
        Richiede conferma dell'utente: se rifiutata, riferiscilo senza insistere.

        Args:
            code: programma Python completo da eseguire
        """
        return await _execute(s, get_ctx(), code, "python")

    return [save_python_file, run_python]


def make_node_tools(s: Settings) -> list:
    _ensure_dirs(s)

    async def run_node(code: str) -> str:
        """Esegue uno script Node.js nel workspace (cartella corrente = workspace; scrivi i file in outputs/)
        e restituisce stdout/stderr. Richiede conferma dell'utente a ogni esecuzione:
        se rifiutata, riferiscilo senza insistere.

        Args:
            code: script Node.js completo da eseguire
        """
        return await _execute(s, get_ctx(), code, "node")

    return [run_node]
