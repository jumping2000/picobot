"""Tool del router per i task programmati chiesti in linguaggio naturale ("ogni mattina alle 8 ...").

Scrivono nello Scheduler come /schedule: stessi limiti, stesso elenco. Mai da un run schedulato.
"""

from ..config import Settings
from ..context import get_ctx
from ..scheduler import ScheduleError, Scheduler, code_approval_prompt, format_schedules

NO_CTX = "Rifiutato: nessuna richiesta attiva."


def make_schedule_tools(s: Settings, scheduler: Scheduler) -> list:
    async def schedule_task(cron: str, richiesta: str, con_codice: bool = False) -> str:
        ctx = get_ctx()
        if ctx is None:
            return NO_CTX
        if ctx.channel == "schedule":
            return "Rifiutato: un task programmato non puo' crearne altri."
        try:
            scheduler.validate(cron)   # cron invalido: errore subito, senza chiedere conferma
            approve = con_codice and (
                ctx.pre_approved
                or (ctx.ask is not None and await ctx.ask(code_approval_prompt(cron, richiesta)))
            )
            sid = scheduler.add(
                ctx.user_id, ctx.channel, ctx.target or ctx.user_id, cron, richiesta, approve_code=approve
            )
            n = scheduler.next_run(cron)
        except ScheduleError as e:
            return str(e)
        when = f"{n:%d/%m/%Y %H:%M} ({s.timezone})" if n else "nessuna"
        code = " Con codice approvato." if approve else (" Creato senza codice." if con_codice else "")
        return (
            f"Task #{sid} creato: [{cron.strip()}] {richiesta.strip()[:120]}.{code} Prossima esecuzione: {when}. "
            f"Si elimina con /unschedule {sid} o chiedendomelo."
        )

    schedule_task.__doc__ = f"""Crea un task ricorrente chiesto dall'utente: la richiesta viene eseguita a ogni scadenza del cron
        e l'esito arriva sul suo canale.

        Args:
            cron: espressione cron a 5 campi 'min ora giorno mese giorno_sett' nel fuso {s.timezone},
                es. "0 8 * * 1-5" (alle 8 dal lunedi al venerdi); intervallo minimo {s.schedule_min_interval_min} minuti
            richiesta: cosa eseguire a ogni scadenza, senza la parte sull'orario, es. "quotazioni AAPL e MSFT"
            con_codice: true solo se la richiesta schedulata deve eseguire codice (l'utente lo approva una volta
                alla creazione); altrimenti false
        """

    async def list_scheduled_tasks() -> str:
        """Elenca i task programmati dell'utente (id, cron, richiesta, ultima esecuzione)."""
        ctx = get_ctx()
        if ctx is None:
            return NO_CTX
        return format_schedules(scheduler.list(ctx.user_id))

    async def unschedule_task(task_id: int) -> str:
        """Elimina un task programmato dell'utente, dato il suo id (lo vedi con list_scheduled_tasks)."""
        ctx = get_ctx()
        if ctx is None:
            return NO_CTX
        if ctx.channel == "schedule":
            return "Rifiutato: un task programmato non puo' eliminare altri task."
        return "Eliminato." if scheduler.remove(ctx.user_id, task_id) else "Task non trovato."

    return [schedule_task, list_scheduled_tasks, unschedule_task]
