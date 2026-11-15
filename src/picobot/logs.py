"""Logging di PicoBot: livello e formato da config, contesto della richiesta in ogni riga, hook sui tool.

Ogni riga emessa durante una richiesta porta req (id della richiesta), canale e utente, letti dal RunCtx corrente:
servono a raggruppare le righe di una stessa richiesta (es. `jq 'select(.req=="ab12cd34")'` con il formato json).
"""
import inspect
import json
import logging
import logging.config
import time
from datetime import datetime, timezone

from .context import get_ctx

logger = logging.getLogger("picobot.tools")

TEXT_FORMAT = "%(asctime)s %(levelname)-7s %(name)s [%(req)s %(channel)s/%(user)s] %(message)s"
# librerie che a INFO/DEBUG scrivono troppo o mettono segreti negli URL (il token Telegram): sempre almeno WARNING
# openai a DEBUG scrive il corpo delle richieste (i prompt): sempre almeno WARNING
_NOISY = ("httpx", "httpx2", "httpcore", "httpcore2", "apscheduler", "openai")
_AGNO = ("agno", "agno-team", "agno-workflow")
_STD = frozenset(logging.LogRecord("", 0, "", 0, "", None, None).__dict__) | {"message", "asctime", "req", "user",
                                                                               "channel"}


class RequestContextFilter(logging.Filter):
    """Aggiunge req, user e channel del RunCtx corrente ('-' fuori da una richiesta)."""

    def filter(self, record: logging.LogRecord) -> bool:
        ctx = get_ctx()
        record.req = ctx.req_id if ctx else "-"
        record.user = ctx.user_id if ctx else "-"
        record.channel = ctx.channel if ctx else "-"
        return True


class JsonFormatter(logging.Formatter):
    """Una riga JSON per evento: ts, level, logger, msg, req, user, channel, exc e gli eventuali campi extra."""

    def format(self, record: logging.LogRecord) -> str:
        out = {"ts": datetime.fromtimestamp(record.created, timezone.utc).isoformat(timespec="milliseconds"),
               "level": record.levelname, "logger": record.name, "msg": record.getMessage(),
               "req": getattr(record, "req", "-"), "user": getattr(record, "user", "-"),
               "channel": getattr(record, "channel", "-")}
        out.update({k: v for k, v in record.__dict__.items() if k not in _STD and not k.startswith("_")})
        if record.exc_info:
            out["exc"] = self.formatException(record.exc_info)
        return json.dumps(out, ensure_ascii=False, default=str)


def setup_logging(level: str = "INFO", fmt: str = "text") -> None:
    """Configura il logging del processo; si puo' richiamare (es. prima e dopo aver letto la config)."""
    import agno.utils.log  # noqa: F401  crea i logger di Agno, che qui perdono il loro handler

    formatter = {"()": JsonFormatter} if fmt == "json" else {"format": TEXT_FORMAT}
    logging.config.dictConfig({
        "version": 1,
        "disable_existing_loggers": False,
        "filters": {"request": {"()": RequestContextFilter}},
        "formatters": {"main": formatter},
        "handlers": {"stderr": {"class": "logging.StreamHandler", "formatter": "main", "filters": ["request"],
                                "level": level}},
        "root": {"level": level, "handlers": ["stderr"]},
    })
    noisy = max(logging.getLevelName(level), logging.WARNING)
    for name in _NOISY:
        logging.getLogger(name).setLevel(noisy)
    for name in _AGNO:   # Agno imposta da solo il livello dei suoi logger a ogni run: il filtro lo fa l'handler
        lg = logging.getLogger(name)
        lg.handlers.clear()
        lg.propagate = True


def log_tool_call(function_name: str, function_call, arguments: dict):
    """Hook di Agno attorno a ogni tool (MCP compresi): durata ed esito. Gli argomenti non vanno mai nel log."""
    t0 = time.monotonic()

    def ok(result):
        if logger.isEnabledFor(logging.DEBUG):
            params = ",".join(sorted(arguments)) or "-"
            if inspect.isasyncgen(result) or inspect.isgenerator(result):   # es. delega a un membro: in streaming
                logger.debug("Tool: nome=%s parametri=%s risultato in streaming", function_name, params)
            else:
                logger.debug("Tool: nome=%s parametri=%s durata=%.1fs risultato=%d caratteri", function_name,
                             params, time.monotonic() - t0, len(str(result)))
        return result

    def failed(e: BaseException) -> None:
        logger.warning("Tool fallito: nome=%s durata=%.1fs errore=%s: %s", function_name, time.monotonic() - t0,
                       type(e).__name__, str(e)[:300])

    try:
        result = function_call(**arguments)
    except Exception as e:
        failed(e)
        raise
    if not inspect.isawaitable(result):
        return ok(result)

    async def timed():
        try:
            return ok(await result)
        except Exception as e:
            failed(e)
            raise
    return timed()
