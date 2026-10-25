"""Canale CLI: REPL interattivo. Conferme codice via prompt y/N."""
import asyncio
import uuid
from pathlib import Path

from ..config import Settings
from ..context import RunCtx
from ..documents import DocumentError
from ..scheduler import ScheduleError
from ..service import PicoBotService
from ..web import is_url
from .common import HELP, format_memory_report, format_schedules, parse_schedule_args

CLI_HELP = (HELP
            .replace("Invia un messaggio vocale o un file audio: lo trascrivo e lo eseguo come un messaggio scritto.\n", "")
            .replace("Invia un PDF/DOCX/TXT: lo riassumo, oppure scrivi nella didascalia cosa farne.",
                     "/file <percorso> [richiesta] - usa un documento (decide il router: riassunto o altro)")
            .replace("/riassumi [istruzioni] - riassunto diretto: come didascalia di un documento o in risposta a un documento",
                     "/riassumi <percorso> [istruzioni] - riassunto diretto di un documento")
            + "\n/quit - esci")


async def _ainput(prompt: str) -> str:
    return await asyncio.to_thread(input, prompt)


def _print_reply(reply) -> None:
    print("\n" + reply.text + "\n")
    for f in reply.files:
        print(f"File: {f.path}")


async def run_cli(s: Settings, service: PicoBotService) -> None:
    uid = s.cli_user_id
    session = f"cli-{uuid.uuid4().hex[:8]}"

    async def confirm(code: str, language: str) -> bool:
        print(f"\n--- Codice da eseguire ({language}) ---\n{code}\n--------------------------")
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
            elif cmd == "/skills":
                info = service.skill_info()
                print("\n".join(f"{i.name}: {i.description[:120]}" for i in info) if info else "Nessuna skill installata.")
            elif cmd == "/memory":
                print(format_memory_report(await service.memory_report(uid)))
            elif cmd == "/forget":
                if (await _ainput("Cancellare TUTTA la memoria? [y/N] ")).strip().lower() in {"y", "s", "si", "yes"}:
                    await service.forget(uid)
                    print("Memoria, profilo ed entita' cancellati.")
                else:
                    print("Annullato.")
            elif cmd in {"/simple", "/complex"}:
                if not arg.strip():
                    print(f"Uso: {cmd} <richiesta>")
                    continue
                reply = await service.ask(arg.strip(), user_id=uid, session_id=session, ctx=ctx, target=cmd[1:])
                _print_reply(reply)
            elif cmd in {"/file", "/riassumi"}:
                path_s, _, instr = arg.strip().partition(" ")
                if cmd == "/riassumi" and is_url(path_s):   # pagina web
                    print(await service.summarize_url(path_s, instr, user_id=uid, session_id=session))
                    continue
                p = Path(path_s).expanduser()
                if not p.is_file():
                    print("File non trovato.")
                    continue
                if cmd == "/riassumi":   # workflow diretto
                    print(await service.summarize(p, instr, user_id=uid, session_id=session))
                else:                    # decide il router (il file dell'utente non viene mai cancellato)
                    doc_ctx = RunCtx(user_id=uid, channel="cli", confirm=confirm, document=p, document_name=p.name)
                    reply = await service.ask(f"[Documento caricato: {p.name}] {instr}".strip(), user_id=uid,
                                              session_id=session, ctx=doc_ctx)
                    _print_reply(reply)
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
                _print_reply(await service.ask(line, user_id=uid, session_id=session, ctx=ctx))
        except (ValueError, ScheduleError, DocumentError) as e:
            print(e)
        except Exception as e:  # noqa: BLE001
            print(f"Errore: {type(e).__name__}: {e}")
