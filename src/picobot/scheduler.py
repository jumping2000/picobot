"""Task schedulati: stessi prompt dell'utente, eseguiti con cron. Tabella SQLite + APScheduler.

Un solo processo (`picobot serve`) esegue i job; CLI/API/Telegram si limitano a scrivere nella tabella
(il processo la riallinea ogni 30s). I run schedulati NON possono eseguire codice (nessun umano per confermare).
"""
import asyncio
import logging
import sqlite3
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from .config import Settings
from .context import RunCtx

logger = logging.getLogger(__name__)
Notifier = Callable[[str, str], Awaitable[None]]  # (target, testo)
RunFn = Callable[..., Awaitable[str]]


class ScheduleError(ValueError):
    pass


class Scheduler:
    def __init__(self, s: Settings, run_fn: RunFn):
        self.s, self.run_fn = s, run_fn
        self.notifiers: dict[str, Notifier] = {}
        self._aps = AsyncIOScheduler(timezone=s.timezone)
        self._known: dict[int, str] = {}  # id -> cron attivo
        s.data_dir.mkdir(parents=True, exist_ok=True)
        with self._db() as c:
            c.execute("""CREATE TABLE IF NOT EXISTS picobot_schedules(
                id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT NOT NULL, channel TEXT NOT NULL,
                target TEXT NOT NULL, cron TEXT NOT NULL, prompt TEXT NOT NULL,
                created_at TEXT NOT NULL, last_run TEXT, last_result TEXT)""")

    def _db(self) -> sqlite3.Connection:
        c = sqlite3.connect(self.s.database_file, timeout=10)
        c.row_factory = sqlite3.Row
        return c

    # -- CRUD ---------------------------------------------------------------
    def validate(self, cron: str) -> CronTrigger:
        try:
            trig = CronTrigger.from_crontab(cron.strip(), timezone=self.s.timezone)
        except ValueError as e:
            raise ScheduleError(f"Cron non valido ({cron!r}): usa 5 campi 'min ora giorno mese giorno_sett'.") from e
        now = datetime.now(timezone.utc)
        n1 = trig.get_next_fire_time(None, now)
        n2 = trig.get_next_fire_time(n1, n1) if n1 else None
        if n1 and n2 and (n2 - n1).total_seconds() < self.s.schedule_min_interval_min * 60:
            raise ScheduleError(f"Intervallo minimo {self.s.schedule_min_interval_min} minuti (controllo costi).")
        return trig

    def add(self, user_id: str, channel: str, target: str, cron: str, prompt: str) -> int:
        prompt = prompt.strip()
        if not prompt or len(prompt) > 1000:
            raise ScheduleError("Prompt vuoto o troppo lungo (max 1000 caratteri).")
        self.validate(cron)
        with self._db() as c:
            n = c.execute("SELECT COUNT(*) FROM picobot_schedules WHERE user_id=?", (user_id,)).fetchone()[0]
            if n >= self.s.max_schedules_per_user:
                raise ScheduleError(f"Massimo {self.s.max_schedules_per_user} schedule per utente.")
            cur = c.execute(
                "INSERT INTO picobot_schedules(user_id,channel,target,cron,prompt,created_at) VALUES(?,?,?,?,?,?)",
                (user_id, channel, target, cron.strip(), prompt, datetime.now(timezone.utc).isoformat()),
            )
            return cur.lastrowid

    def list(self, user_id: str) -> list[dict]:
        with self._db() as c:
            rows = c.execute("SELECT * FROM picobot_schedules WHERE user_id=? ORDER BY id", (user_id,)).fetchall()
        return [dict(r) for r in rows]

    def remove(self, user_id: str, sid: int) -> bool:
        with self._db() as c:
            return c.execute("DELETE FROM picobot_schedules WHERE id=? AND user_id=?", (sid, user_id)).rowcount > 0

    # -- esecuzione ---------------------------------------------------------
    async def sync(self) -> None:
        with self._db() as c:
            rows = {r["id"]: r["cron"] for r in c.execute("SELECT id, cron FROM picobot_schedules")}
        for sid in set(self._known) - set(rows):
            self._drop(sid)
        for sid, cron in rows.items():
            if self._known.get(sid) != cron:
                self._drop(sid)
                self._aps.add_job(self._fire, self.validate_quiet(cron), args=[sid], id=f"s{sid}",
                                  misfire_grace_time=300, coalesce=True, max_instances=1)
                self._known[sid] = cron

    def validate_quiet(self, cron: str) -> CronTrigger:
        return CronTrigger.from_crontab(cron, timezone=self.s.timezone)

    def _drop(self, sid: int) -> None:
        self._known.pop(sid, None)
        if self._aps.get_job(f"s{sid}"):
            self._aps.remove_job(f"s{sid}")

    async def run_now(self, sid: int) -> str:
        with self._db() as c:
            r = c.execute("SELECT * FROM picobot_schedules WHERE id=?", (sid,)).fetchone()
        if not r:
            return ""
        stamp = datetime.now().strftime("%Y%m%d%H%M")
        ctx = RunCtx(user_id=r["user_id"], channel="schedule")  # niente confirm -> niente codice
        try:
            text = await self.run_fn(r["prompt"], user_id=r["user_id"], session_id=f"sched-{sid}-{stamp}", ctx=ctx)
        except Exception:
            logger.exception("Schedule %s fallito", sid)
            text = "Errore nell'esecuzione dello schedule."
        with self._db() as c:
            c.execute("UPDATE picobot_schedules SET last_run=?, last_result=? WHERE id=?",
                      (datetime.now(timezone.utc).isoformat(), text[:8000], sid))
        notifier = self.notifiers.get(r["channel"])
        if notifier:
            try:
                await notifier(r["target"], f"[Schedule #{sid}] {r['prompt'][:60]}\n\n{text}")
            except Exception:
                logger.exception("Notifica schedule %s fallita", sid)
        return text

    async def _fire(self, sid: int) -> None:
        await self.run_now(sid)

    async def start(self) -> None:
        self._aps.add_job(self.sync, "interval", seconds=30, id="sync", max_instances=1)
        self._aps.start()
        await self.sync()
        logger.info("Scheduler attivo (%d job).", len(self._known))

    async def stop(self) -> None:
        if self._aps.running:
            self._aps.shutdown(wait=False)
