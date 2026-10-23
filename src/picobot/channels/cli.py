"""Canale CLI: REPL interattivo. Conferme codice via prompt y/N."""
import asyncio
import uuid
from pathlib import Path

from ..config import Settings
from ..context import RunCtx
from ..documents import DocumentError
from ..scheduler import ScheduleError
from ..service import PicoBotService
from .common import HELP, format_schedules, parse_schedule_args

CLI_HELP = HELP.replace("Invia un PDF/DOCX/TXT per ottenere un riassunto (nella didascalia puoi scrivere istruzioni).",
                        "/file <percorso> [istruzioni] - riassume un PDF/DOCX/TXT") + "\n/quit - esci"


async def _ainput(prompt: str) -> str:
    return await asyncio.to_thread(input, prompt)


async def run_cli(s: Settings, service: PicoBotService) -> None:
    uid = s.cli_user_id
    session = f"cli-{uuid.uuid4().hex[:8]}"

    async def confirm(preview: str) -> bool:
        print(f"\n--- Codice da eseguire ---\n{preview}\n--------------------------")
        try:
            ans = await asyncio.wait_for(_ainput("Eseguire? [y/N] "), timeout=s.confirm_timeout_s)
        except (asyncio.TimeoutError, EOFError):
            return False
        return ans.strip().lower() in {"y", "yes", "s", "si"}

    ctx = RunCtx(user_id=uid, channel="cli", confirm=confirm)
    print(f"PicoBot CLI (utente '{uid}'). /help per i comandi.")
    while True:
        try:
            line = (await _ainput("> ")).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if not line:
            continue
        cmd, _, arg = line.partition(" ")
        try:
            if cmd in {"/quit", "/exit"}:
                return
            elif cmd in {"/help", "/start"}:
                print(CLI_HELP)
            elif cmd == "/new":
                session = f"cli-{uuid.uuid4().hex[:8]}"
                print("Nuova conversazione.")
            elif cmd == "/memory":
                mems = await service.memories(uid)
                print("\n".join(f"- {m}" for m in mems) if mems else "Nessuna memoria.")
            elif cmd == "/forget":
                if (await _ainput("Cancellare TUTTA la memoria? [y/N] ")).strip().lower() in {"y", "s", "si", "yes"}:
                    await service.forget(uid)
                    print("Memoria cancellata.")
                else:
                    print("Annullato.")
            elif cmd == "/file":
                path_s, _, instr = arg.strip().partition(" ")
                p = Path(path_s).expanduser()
                if not p.is_file():
                    print("File non trovato.")
                    continue
                print(await service.summarize(p, instr, user_id=uid, session_id=session))
            elif cmd == "/schedule":
                cron, prompt = parse_schedule_args(arg)
                sid = service.scheduler.add(uid, "cli", uid, cron, prompt)
                print(f"Task #{sid} creato (gira nel processo `picobot serve`; risultati con /schedules).")
            elif cmd == "/schedules":
                rows = service.scheduler.list(uid)
                print(format_schedules(rows))
                for r in rows:
                    if r["last_result"]:
                        print(f"\n#{r['id']} ultimo risultato:\n{r['last_result'][:1500]}")
            elif cmd == "/unschedule":
                print("Eliminato." if service.scheduler.remove(uid, int(arg)) else "Task non trovato.")
            else:
                print("\n" + await service.ask(line, user_id=uid, session_id=session, ctx=ctx) + "\n")
        except (ValueError, ScheduleError, DocumentError) as e:
            print(e)
        except Exception as e:  # noqa: BLE001
            print(f"Errore: {type(e).__name__}: {e}")
