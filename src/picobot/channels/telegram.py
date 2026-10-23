"""Canale Telegram: auth fail-closed, sessioni persistenti, HITL a bottoni, documenti, schedule."""
import asyncio
import logging
import uuid
from io import BytesIO
from collections import defaultdict
from pathlib import Path

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatAction, ParseMode
from telegram.error import BadRequest
from telegram.ext import (
    Application, ApplicationBuilder, CallbackQueryHandler, CommandHandler,
    ContextTypes, MessageHandler, PicklePersistence, filters,
)

from ..config import Settings
from ..context import Reply, RunCtx
from ..documents import SUPPORTED, DocumentError
from ..scheduler import ScheduleError
from ..service import PicoBotService
from .common import HELP, format_schedules, parse_schedule_args, split_text

logger = logging.getLogger(__name__)


async def send_safe(update: Update, text: str) -> None:
    for chunk in split_text(text):
        try:
            await update.message.reply_text(chunk, parse_mode=ParseMode.MARKDOWN)
        except BadRequest:  # Markdown non valido: ripiega su testo semplice
            await update.message.reply_text(chunk)


class TelegramGateway:
    def __init__(self, s: Settings, service: PicoBotService):
        self.s, self.service = s, service
        self._locks: defaultdict[int, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._pending: dict[str, tuple[asyncio.Future, int]] = {}

    # -- auth / sessione ------------------------------------------------------
    def authorized(self, update: Update) -> bool:
        user = update.effective_user
        if not user:
            return False
        if self.s.allow_all_users:
            return True
        ok = user.id in self.s.allowed_ids
        if not ok:
            logger.warning("Accesso negato: user_id=%s", user.id)
        return ok

    @staticmethod
    def session_id(ctx: ContextTypes.DEFAULT_TYPE, chat_id: int) -> str:
        return ctx.chat_data.setdefault("session_id", f"tg-{chat_id}-{uuid.uuid4().hex[:8]}")

    # -- human in the loop: bottoni inline -----------------------------------------
    async def ask_yes_no(self, bot, chat_id: int, user_id: int, prompt: str) -> bool:
        token = uuid.uuid4().hex[:10]
        fut: asyncio.Future = asyncio.get_running_loop().create_future()
        self._pending[token] = (fut, user_id)
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("Conferma", callback_data=f"cf:{token}:y"),
                                    InlineKeyboardButton("Annulla", callback_data=f"cf:{token}:n")]])
        msg = await bot.send_message(chat_id, prompt[:3900], reply_markup=kb)
        try:
            return await asyncio.wait_for(fut, timeout=self.s.confirm_timeout_s)
        except asyncio.TimeoutError:
            return False
        finally:
            self._pending.pop(token, None)
            try:
                await msg.edit_reply_markup(None)
            except Exception:  # noqa: BLE001
                pass

    async def confirm_code(self, bot, chat_id: int, user_id: int, code: str, language: str) -> bool:
        """Mostra il codice COMPLETO prima dei bottoni: inline se corto, come allegato se lungo."""
        if len(code) > 1500:
            try:
                await bot.send_document(chat_id, document=BytesIO(code.encode("utf-8")),
                                        filename=f"codice.{'js' if language == 'node' else 'py'}")
            except Exception:  # noqa: BLE001  senza codice visibile non si chiede conferma
                logger.exception("Invio del codice da confermare fallito")
                await bot.send_message(chat_id, "Impossibile mostrare il codice: esecuzione annullata.")
                return False
            prompt = f"Eseguire il codice {language} allegato ({len(code)} caratteri)?"
        else:
            prompt = f"Eseguire questo codice {language}?\n\n{code}"
        return await self.ask_yes_no(bot, chat_id, user_id, prompt)

    async def send_reply(self, update: Update, reply: Reply) -> None:
        await send_safe(update, reply.text)
        for f in reply.files:
            try:
                with f.path.open("rb") as fh:
                    await update.message.reply_document(document=fh, filename=f.name)
            except Exception:  # noqa: BLE001
                logger.exception("Invio file %s fallito", f.name)
                await update.message.reply_text(f"Impossibile inviare il file {f.name}.")

    async def on_callback(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        q = update.callback_query
        try:
            _, token, ans = q.data.split(":")
        except ValueError:
            return await q.answer()
        entry = self._pending.get(token)
        if not entry or entry[1] != q.from_user.id:   # solo chi ha chiesto puo' confermare
            return await q.answer("Richiesta scaduta o non tua.", show_alert=True)
        if not entry[0].done():
            entry[0].set_result(ans == "y")
        await q.answer("Ok" if ans == "y" else "Annullato")

    # -- comandi ----------------------------------------------------------------------
    async def on_help(self, update, ctx):
        if self.authorized(update):
            await update.message.reply_text(HELP)

    async def on_new(self, update, ctx):
        if self.authorized(update):
            ctx.chat_data.pop("session_id", None)
            await update.message.reply_text("Nuova conversazione. La memoria su di te e' conservata.")

    async def on_memory(self, update, ctx):
        if not self.authorized(update):
            return
        mems = await self.service.memories(str(update.effective_user.id))
        await send_safe(update, "Ricordo:\n" + "\n".join(f"- {m}" for m in mems) if mems else "Non ho memorie su di te.")

    async def on_forget(self, update, ctx):
        if not self.authorized(update):
            return
        ok = await self.ask_yes_no(ctx.bot, update.effective_chat.id, update.effective_user.id,
                                   "Cancellare TUTTA la memoria su di te? L'operazione non e' reversibile.")
        if ok:
            await self.service.forget(str(update.effective_user.id))
            await update.message.reply_text("Memoria cancellata.")
        else:
            await update.message.reply_text("Annullato, memoria intatta.")

    async def on_schedule(self, update, ctx):
        if not self.authorized(update):
            return
        arg = (update.message.text.split(maxsplit=1) + [""])[1]
        try:
            cron, prompt = parse_schedule_args(arg)
            sid = self.service.scheduler.add(str(update.effective_user.id), "telegram",
                                             str(update.effective_chat.id), cron, prompt)
            await update.message.reply_text(f"Task #{sid} creato. Fuso orario: {self.s.timezone}.")
        except (ValueError, ScheduleError) as e:
            await update.message.reply_text(str(e))

    async def on_skills(self, update, ctx):
        if not self.authorized(update):
            return
        info = self.service.skill_info()
        text = "\n".join(f"{i.name}: {i.description[:120]}" for i in info) if info else "Nessuna skill installata."
        await update.message.reply_text(text)

    async def on_schedules(self, update, ctx):
        if self.authorized(update):
            await update.message.reply_text(format_schedules(self.service.scheduler.list(str(update.effective_user.id))))

    async def on_unschedule(self, update, ctx):
        if not self.authorized(update):
            return
        try:
            sid = int(ctx.args[0])
        except (IndexError, ValueError):
            return await update.message.reply_text("Uso: /unschedule <id>")
        ok = self.service.scheduler.remove(str(update.effective_user.id), sid)
        await update.message.reply_text("Eliminato." if ok else "Task non trovato.")

    # -- messaggi ------------------------------------------------------------------------
    async def _with_typing(self, ctx, chat_id, coro):
        async def typing():
            while True:
                await ctx.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
                await asyncio.sleep(4)
        task = asyncio.create_task(typing())
        try:
            return await coro
        finally:
            task.cancel()

    async def on_message(self, update, ctx):
        if not self.authorized(update) or not update.message or not update.message.text:
            return
        chat_id, uid = update.effective_chat.id, update.effective_user.id
        logger.info("Messaggio user=%s chat=%s len=%d", uid, chat_id, len(update.message.text))
        run_ctx = RunCtx(user_id=str(uid), channel="telegram",
                         confirm=lambda code, language: self.confirm_code(ctx.bot, chat_id, uid, code, language))
        async with self._locks[chat_id]:
            try:
                reply = await self._with_typing(ctx, chat_id, self.service.ask(
                    update.message.text, user_id=str(uid), session_id=self.session_id(ctx, chat_id), ctx=run_ctx))
                await self.send_reply(update, reply)
            except Exception:
                logger.exception("Errore nel run")
                await update.message.reply_text("Errore interno durante l'elaborazione. Riprova tra poco.")

    async def on_document(self, update, ctx):
        if not self.authorized(update) or not update.message or not update.message.document:
            return
        doc, chat_id, uid = update.message.document, update.effective_chat.id, str(update.effective_user.id)
        ext = Path(doc.file_name or "").suffix.lower()
        if ext not in SUPPORTED:
            return await update.message.reply_text("Formato non supportato. Ammessi: PDF, DOCX, TXT, MD, CSV, JSON, LOG.")
        if (doc.file_size or 0) > self.s.max_upload_mb * 1024 * 1024:
            return await update.message.reply_text(f"File troppo grande (max {self.s.max_upload_mb} MB).")
        inbox = self.s.data_dir / "inbox"
        inbox.mkdir(parents=True, exist_ok=True)
        path = inbox / f"{uuid.uuid4().hex}{ext}"
        async with self._locks[chat_id]:
            try:
                tg_file = await doc.get_file()
                await tg_file.download_to_drive(custom_path=path)
                text = await self._with_typing(ctx, chat_id, self.service.summarize(
                    path, update.message.caption or "", user_id=uid, name=doc.file_name,
                    session_id=self.session_id(ctx, chat_id)))
                await send_safe(update, text)
            except DocumentError as e:
                await update.message.reply_text(str(e))
            except Exception:
                logger.exception("Errore riassunto documento")
                await update.message.reply_text("Errore durante il riassunto del documento.")
            finally:
                path.unlink(missing_ok=True)   # il documento non resta sul server


def build_application(s: Settings, service: PicoBotService) -> tuple[Application, TelegramGateway]:
    s.data_dir.mkdir(parents=True, exist_ok=True)
    gw = TelegramGateway(s, service)
    app = (ApplicationBuilder().token(s.telegram_bot_token)
           .persistence(PicklePersistence(filepath=str(s.data_dir / "telegram_state.pkl")))
           .concurrent_updates(True)   # indispensabile: il bottone di conferma arriva mentre il run e' in attesa
           .build())
    app.add_handler(CommandHandler(["start", "help"], gw.on_help))
    app.add_handler(CommandHandler("new", gw.on_new))
    app.add_handler(CommandHandler("memory", gw.on_memory))
    app.add_handler(CommandHandler("forget", gw.on_forget))
    app.add_handler(CommandHandler("schedule", gw.on_schedule))
    app.add_handler(CommandHandler("schedules", gw.on_schedules))
    app.add_handler(CommandHandler("skills", gw.on_skills))
    app.add_handler(CommandHandler("unschedule", gw.on_unschedule))
    app.add_handler(CallbackQueryHandler(gw.on_callback, pattern=r"^cf:"))
    app.add_handler(MessageHandler(filters.Document.ALL, gw.on_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, gw.on_message))
    return app, gw
