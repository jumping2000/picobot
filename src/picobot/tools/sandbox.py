"""Tool per scrivere ed eseguire piccoli programmi Python, con human-in-the-loop.

- scrittura file: libera, solo in workspace/scripts
- esecuzione: SOLO dopo conferma umana (o approve_code esplicito via API); mai negli schedule
- subprocess separato, env ripulito (niente chiavi API), timeout, limiti CPU/RAM, output troncato
"""
import asyncio
import os
import re
import sys
from pathlib import Path

from ..config import Settings
from ..context import get_ctx

_NAME = re.compile(r"^[A-Za-z0-9_\-]{1,60}(\.py)?$")


def _limits() -> None:  # eseguito nel figlio, prima dell'exec
    import resource

    resource.setrlimit(resource.RLIMIT_CPU, (60, 60))
    resource.setrlimit(resource.RLIMIT_AS, (768 * 1024 * 1024, 768 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_FSIZE, (20 * 1024 * 1024, 20 * 1024 * 1024))


def make_code_tools(s: Settings) -> list:
    scripts = s.workspace_dir / "scripts"

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
        ctx = get_ctx()
        if ctx is None or not ctx.can_run_code:
            return ("Esecuzione NON consentita in questo contesto (nessuna conferma umana possibile). "
                    "Puoi salvare il codice con save_python_file e mostrarlo all'utente.")
        if ctx.confirm is not None:
            preview = code if len(code) <= 1500 else code[:1500] + "\n... (troncato)"
            if not await ctx.confirm(preview):
                return "L'utente ha RIFIUTATO l'esecuzione (o nessuna risposta entro il timeout)."

        scripts.mkdir(parents=True, exist_ok=True)
        f = scripts / "_run.py"
        f.write_text(code, encoding="utf-8")
        env = {"PATH": os.environ.get("PATH", ""), "HOME": str(s.workspace_dir), "PYTHONIOENCODING": "utf-8"}
        proc = await asyncio.create_subprocess_exec(
            sys.executable, str(f), cwd=str(s.workspace_dir), env=env,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
            preexec_fn=_limits if os.name == "posix" else None,
        )
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

    return [save_python_file, run_python]
