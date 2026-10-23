"""Avvio dei canali: `serve` (Telegram + API + scheduler nello stesso processo) e `cli`."""
import asyncio
import logging
import signal

from .config import Settings
from .service import PicoBotService

logger = logging.getLogger(__name__)


async def serve(s: Settings, use_telegram: bool, use_api: bool) -> None:
    service = PicoBotService(s)
    await service.start()
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:  # Windows
            pass

    tg_app = api_server = api_task = None
    if use_telegram:
        from .channels.common import split_text
        from .channels.telegram import build_application

        tg_app, _ = build_application(s, service)
        await tg_app.initialize()
        await tg_app.start()
        await tg_app.updater.start_polling()

        async def notify(target: str, text: str) -> None:
            for chunk in split_text(text):
                await tg_app.bot.send_message(int(target), chunk)

        service.scheduler.notifiers["telegram"] = notify
        logger.info("Telegram attivo.")
    if use_api:
        import uvicorn

        from .channels.api import create_app

        tls = ({"ssl_certfile": s.api_ssl_certfile, "ssl_keyfile": s.api_ssl_keyfile}
               if s.api_ssl_certfile and s.api_ssl_keyfile else {})
        api_server = uvicorn.Server(uvicorn.Config(create_app(s, service), host=s.api_host,
                                                   port=s.api_port, log_level="warning", **tls))
        api_server.install_signal_handlers = lambda: None  # i segnali li gestiamo noi
        api_task = asyncio.create_task(api_server.serve())
        logger.info("API su %s://%s:%s", "https" if tls else "http", s.api_host, s.api_port)

    await service.scheduler.start()
    try:
        await stop.wait()
    finally:
        logger.info("Arresto...")
        if api_server:
            api_server.should_exit = True
            await api_task
        if tg_app:
            await tg_app.updater.stop()
            await tg_app.stop()
            await tg_app.shutdown()
        await service.stop()


async def cli(s: Settings) -> None:
    from .channels.cli import run_cli

    service = PicoBotService(s)
    await service.start()
    try:
        await run_cli(s, service)
    finally:
        await service.stop()
