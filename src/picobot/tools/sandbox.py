"""Tool per scrivere ed eseguire piccoli programmi (Python, Node) e gli script delle skill, con human-in-the-loop.

- scrittura file: libera, solo in workspace/scripts
- esecuzione, stesse regole per run_python, run_node e run_skill_script:
  - code.allow_code=false: non si esegue nulla, su nessun canale
  - Telegram, CLI: una conferma umana per richiesta, alla prima esecuzione (vale per le successive; un no le
    rifiuta tutte); API: approve_code esplicito; schedule: solo se approvati alla creazione; email: pre-approvate
- subprocess separato, env ripulito (niente chiavi API), timeout, limiti CPU/RAM/file, output troncato
- tetto di esecuzioni approvate per richiesta (CODE_MAX_RUNS); ogni esecuzione e ogni rifiuto vanno nel log
"""
import asyncio
import logging
import os
import re
import sys
import time
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

from agno.exceptions import PathSecurityError
from agno.utils.path_safety import safe_join_relative_path

from ..config import Settings
from ..context import RunCtx, get_ctx

if TYPE_CHECKING:
    from ..skills import SkillRegistry

logger = logging.getLogger(__name__)

_NAME = re.compile(r"^[A-Za-z0-9_\-]{1,60}(\.py)?$")
_MB = 1024 * 1024
_PYTHON_AS_MB = 768
_NODE_EXT = {".js", ".mjs", ".cjs"}

NOT_ALLOWED = ("Esecuzione NON consentita in questo contesto (nessuna conferma umana possibile). "
               "Puoi salvare il codice con save_python_file e mostrarlo all'utente.")
CODE_DISABLED = "Esecuzione di codice disattivata dalla configurazione (code.allow_code: false)."
REFUSED = ("L'utente ha RIFIUTATO l'esecuzione di codice per questa richiesta (o nessuna risposta entro il "
           "timeout): non riprovare, riferisci all'utente.")


def _limits_for(as_mb: int, fsize_mb: int):
    def apply() -> None:  # eseguito nel figlio, prima dell'exec
        import resource

        resource.setrlimit(resource.RLIMIT_CPU, (60, 60))
        resource.setrlimit(resource.RLIMIT_AS, (as_mb * _MB, as_mb * _MB))
        resource.setrlimit(resource.RLIMIT_FSIZE, (fsize_mb * _MB, fsize_mb * _MB))
    return apply


def _who(ctx: RunCtx | None) -> tuple[str, str]:
    return (ctx.user_id, ctx.channel) if ctx else ("-", "-")


async def _gate(s: Settings, ctx: RunCtx | None, preview: str, language: str, kind: str) -> str | None:
    """None se l'esecuzione puo' partire (e la conta), altrimenti il messaggio di rifiuto per l'agente."""
    reason, msg = None, None
    if not s.allow_code:
        reason, msg = "disattivato", CODE_DISABLED
    elif ctx is None or not ctx.can_run_code:
        reason, msg = "non consentito", NOT_ALLOWED
    elif ctx.runs >= s.code_max_runs:
        reason = "limite"
        msg = (f"Esecuzione rifiutata: limite raggiunto ({s.code_max_runs} esecuzioni approvate per richiesta). "
               "Fermati e riferisci all'utente cosa non funziona.")
    elif ctx.confirm is not None:
        first = ctx.code_approval is None
        if first:   # prima esecuzione della richiesta: si chiede una volta sola
            ctx.code_approval = bool(await ctx.confirm(preview, language))
        if not ctx.code_approval:   # annullato o scaduto: il canale lo registra al momento della risposta
            reason, msg = ("rifiutato dall'utente" if first else "gia' rifiutato in questa richiesta"), REFUSED
    user, channel = _who(ctx)
    if msg is not None:
        logger.info("Codice rifiutato: utente=%s canale=%s tipo=%s motivo=%s", user, channel, kind, reason)
        if ctx is not None:   # avviso fisso alla risposta: un modello che dichiara "fatto" non puo' nasconderlo
            why = {"disattivato": "code.allow_code e' disattivato", "non consentito": "questo canale non puo' approvarlo",
                   "limite": f"raggiunto il limite di {s.code_max_runs} esecuzioni"}.get(reason, "conferma negata o scaduta")
            note = f"⚠️ Codice non eseguito: {why}."
            if note not in ctx.notices:
                ctx.notices.append(note)
        return msg
    ctx.runs += 1
    return None


async def _spawn(s: Settings, ctx: RunCtx, cmd: list[str], as_mb: int, kind: str) -> str:
    """Esegue cmd nel workspace con env ripulito, limiti e timeout; registra l'esito nel log."""
    env = {"PATH": os.environ.get("PATH", ""), "HOME": str(s.workspace_dir), "PYTHONIOENCODING": "utf-8"}
    if os.name == "nt":  # senza SYSTEMROOT su Windows node abortisce e Python non importa asyncio
        env["SYSTEMROOT"] = os.environ.get("SYSTEMROOT", "")
    if cmd[0] == "node" and s.node_path:
        env["NODE_PATH"] = s.node_path
    t0, exit_code = time.monotonic(), "errore"
    try:
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd, cwd=str(s.workspace_dir), env=env,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
                preexec_fn=_limits_for(as_mb, 2 * s.max_output_mb) if os.name == "posix" else None,
            )
        except FileNotFoundError:
            logger.warning("Codice: eseguibile '%s' non trovato nel PATH del sandbox", cmd[0])
            return f"Errore: eseguibile '{cmd[0]}' non trovato nel PATH del sandbox."
        try:
            out, _ = await asyncio.wait_for(proc.communicate(), timeout=s.code_timeout_s)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            exit_code = "timeout"
            return f"Timeout: esecuzione interrotta dopo {s.code_timeout_s}s."
        exit_code = proc.returncode
        text = out.decode("utf-8", "replace")
        if exit_code != 0:   # solo DEBUG: l'output puo' contenere dati dell'utente
            logger.debug("Codice: tipo=%s exit=%s, fine dell'output: %s", kind, exit_code, text[-500:])
        if len(text) > s.code_max_output:
            text = text[: s.code_max_output] + "\n... (output troncato)"
        return f"exit={proc.returncode}\n{text}"
    finally:
        logger.info("Codice: utente=%s canale=%s tipo=%s esecuzione %d/%d exit=%s durata=%.1fs",
                    ctx.user_id, ctx.channel, kind, ctx.runs, s.code_max_runs, exit_code, time.monotonic() - t0)


async def _execute(s: Settings, ctx: RunCtx | None, code: str, language: str) -> str:
    """Gate + esecuzione isolata di codice scritto dall'agente. language: 'python' | 'node'."""
    if (refusal := await _gate(s, ctx, code, language, language)) is not None:
        return refusal
    scripts = s.workspace_dir / "scripts"
    scripts.mkdir(parents=True, exist_ok=True)
    script = scripts / f"_run-{uuid.uuid4().hex}{'.py' if language == 'python' else '.js'}"
    script.write_text(code, encoding="utf-8")
    try:
        if language == "node":
            return await _spawn(s, ctx, ["node", str(script)], s.code_node_mem_mb, language)
        return await _spawn(s, ctx, [sys.executable, str(script)], _PYTHON_AS_MB, language)
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
        La prima esecuzione della richiesta chiede conferma all'utente e vale per le successive:
        se rifiutata, riferiscilo senza insistere.

        Args:
            code: programma Python completo da eseguire
        """
        return await _execute(s, get_ctx(), code, "python")

    return [save_python_file, run_python]


def make_node_tools(s: Settings) -> list:
    _ensure_dirs(s)

    async def run_node(code: str) -> str:
        """Esegue uno script Node.js nel workspace (cartella corrente = workspace; scrivi i file in outputs/)
        e restituisce stdout/stderr. La prima esecuzione della richiesta chiede conferma all'utente e vale
        per le successive: se rifiutata, riferiscilo senza insistere.

        Args:
            code: script Node.js completo da eseguire
        """
        return await _execute(s, get_ctx(), code, "node")

    return [run_node]


def make_skill_script_tools(s: Settings, registry: "SkillRegistry") -> list:
    _ensure_dirs(s)

    async def run_skill_script(skill_name: str, script_path: str, args: list[str] | None = None) -> str:
        """Esegue uno script della cartella scripts/ di una skill (.py o .js) nel sandbox, con gli argomenti dati.
        La cartella corrente e' il workspace: i file vanno in outputs/. Leggi prima lo script con get_skill_script.
        Stesse regole di run_python: la prima esecuzione della richiesta chiede conferma all'utente.

        Args:
            skill_name: nome della skill, es. "docx"
            script_path: nome del file in scripts/, es. "unpack.py"
            args: argomenti da riga di comando (facoltativi)
        """
        args = [str(a) for a in (args or [])]
        if registry.skills is None:
            return "Le skill sono disattivate (skills.enable_skills: false)."
        skill = registry.skills.get_skill(skill_name)
        if skill is None:
            return f"Skill '{skill_name}' non trovata. Installate: {', '.join(registry.skills.get_skill_names())}"
        if script_path not in skill.scripts:
            return f"Script '{script_path}' non trovato nella skill '{skill_name}'. Disponibili: {', '.join(skill.scripts)}"
        suffix = Path(script_path).suffix.lower()
        if suffix != ".py" and suffix not in _NODE_EXT:
            return f"Script '{script_path}' non eseguibile: solo .py (Python) e .js/.mjs/.cjs (Node)."
        try:
            path = safe_join_relative_path(Path(skill.source_path) / "scripts", script_path).resolve()
            source = path.read_text(encoding="utf-8")
        except (PathSecurityError, OSError, UnicodeDecodeError) as e:
            return f"Script '{script_path}' illeggibile: {e}"
        language = "python" if suffix == ".py" else "node"
        kind = f"skill:{skill_name}/{script_path}"
        preview = f"[skill {skill_name}] {' '.join([script_path, *args])}\n\n{source}"
        ctx = get_ctx()
        if (refusal := await _gate(s, ctx, preview, language, kind)) is not None:
            return refusal
        if language == "node":
            return await _spawn(s, ctx, ["node", str(path), *args], s.code_node_mem_mb, kind)
        return await _spawn(s, ctx, [sys.executable, str(path), *args], _PYTHON_AS_MB, kind)

    return [run_skill_script]
