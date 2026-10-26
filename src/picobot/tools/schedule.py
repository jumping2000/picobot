"""Tool del router per i task programmati chiesti in linguaggio naturale ("ogni mattina alle 8 ...").

Scrivono nello Scheduler come /schedule: stessi limiti, stesso elenco. Mai da un run schedulato.
"""
from ..config import Settings
from ..context import get_ctx
from ..scheduler import ScheduleError, Scheduler, format_schedules

NO_CTX = "Rifiutato: nessuna richiesta attiva."


def make_schedule_tools(s: Settings, scheduler: Scheduler) -> list:
    async def schedule_task(cron: str, richiesta: str) -> str:
        ctx = get_ctx()
        if ctx is None:
            return NO_CTX
        if ctx.channel == "schedule":
            return "Rifiutato: un task programmato non puo' crearne altri."
        try:
            sid = scheduler.add(ctx.user_id, ctx.channel, ctx.target or ctx.user_id, cron, richiesta)
            n = scheduler.next_run(cron)
        except ScheduleError as e:
            return str(e)
        when = f"{n:%d/%m/%Y %H:%M} ({s.timezone})" if n else "nessuna"
        return (f"Task #{sid} creato: [{cron.strip()}] {richiesta.strip()[:60]}. Prossima esecuzione: {when}. "
                f"Si elimina con /unschedule {sid}.")

    schedule_task.__doc__ = f"""Crea un task ricorrente chiesto dall'utente: la richiesta viene eseguita a ogni scadenza del cron
        e l'esito arriva sul suo canale.

        Args:
            cron: espressione cron a 5 campi 'min ora giorno mese giorno_sett' nel fuso {s.timezone},
                es. "0 8 * * 1-5" (alle 8 dal lunedi al venerdi); intervallo minimo {s.schedule_min_interval_min} minuti
            richiesta: cosa eseguire a ogni scadenza, senza la parte sull'orario, es. "quotazioni AAPL e MSFT"
        """

    async def list_scheduled_tasks() -> str:
        """Elenca i task programmati dell'utente (id, cron, richiesta, ultima esecuzione)."""
        ctx = get_ctx()
        if ctx is None:
            return NO_CTX
        return format_schedules(scheduler.list(ctx.user_id))

    return [schedule_task, list_scheduled_tasks]
