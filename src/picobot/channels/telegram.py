"""Canale Telegram: auth fail-closed, sessioni persistenti, HITL a bottoni, documenti, schedule."""
import asyncio
import logging
import mimetypes
import uuid
from io import BytesIO
from collections import defaultdict
from pathlib import Path

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatAction
from telegram.ext import (
    Application, ApplicationBuilder, CallbackQueryHandler, CommandHandler,
    ContextTypes, MessageHandler, PicklePersistence, filters,
)

from ..config import Settings
from ..context import Reply, RunCtx
from ..documents import SUPPORTED, DocumentError
from ..scheduler import ScheduleError
from ..service import PicoBotService
from ..stt import SttError, transcribe
from ..web import is_url
from .common import (
    HELP, SKILL_ADMIN_OFF, SKILL_ADMIN_ONLY, add_skill_flow, format_memory_report, format_schedules,
    parse_schedule_args, remove_skill_flow, split_text, trace_text,
)
from .tg_format import send_formatted

logger = logging.getLogger(__name__)
_RIASSUMI_USAGE = "Uso: /riassumi <link> [istruzioni], oppure rispondi a un documento con /riassumi (o usalo come didascalia)."

_SKILL_ADD_USAGE = ("Uso: /skill_add <link https:// di uno .zip o di un repository git>, "
                    "oppure allega uno .zip con didascalia /skill_add.")

# estensione del file audio scaricato quando manca il nome (mimetypes da' ".oga" per audio/ogg, niente per wav)
_AUDIO_EXT = {"audio/ogg": ".ogg", "audio/opus": ".ogg", "audio/mpeg": ".mp3", "audio/mp4": ".m4a",
              "audio/x-m4a": ".m4a", "audio/wav": ".wav", "audio/x-wav": ".wav"}
_STT_MESSAGES = {
    "unavailable": "Trascrizione non disponibile al momento: riprova o scrivi il messaggio.",
    "unreadable": "Non riesco a leggere questo audio.",
}


async def send_safe(update: Update, text: str, fmt: str = "markdown") -> None:
    await send_formatted(update.message.reply_text, text, fmt)


def make_notify(bot, fmt: str):
    """Notifica dei task programmati: stesso formato e stesso ripiego delle risposte."""
    async def notify(target: str, text: str) -> None:
        await send_formatted(lambda t, **kw: bot.send_message(int(target), t, **kw), text, fmt)
    return notify


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

    def is_admin(self, update: Update) -> bool:
        """Autorizzato e in ADMIN_USER_IDS (con ALLOW_ALL_USERS=true e lista vuota nessuno e' admin)."""
        return self.authorized(update) and update.effective_user.id in self.s.admin_ids

    async def _skill_gate(self, update: Update) -> bool:
        """True se l'utente puo' gestire le skill; altrimenti risponde (agli autorizzati) e ritorna False."""
        if not self.authorized(update):
            return False
        if self.is_admin(update):
            return True
        await update.message.reply_text(SKILL_ADMIN_ONLY if self.s.admin_ids else SKILL_ADMIN_OFF)
        return False

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
        await send_safe(update, reply.text, self.s.reply_format)
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
        await send_safe(update, format_memory_report(await self.service.memory_report(str(update.effective_user.id))),
                        self.s.reply_format)

    async def on_forget(self, update, ctx):
        if not self.authorized(update):
            return
        ok = await self.ask_yes_no(ctx.bot, update.effective_chat.id, update.effective_user.id,
                                   "Cancellare TUTTA la memoria su di te? L'operazione non e' reversibile.")
        if ok:
            try:
                await self.service.forget(str(update.effective_user.id))
            except Exception:
                logger.exception("Cancellazione memoria fallita")
                return await update.message.reply_text("Errore: la memoria non e' stata cancellata del tutto. Riprova.")
            await update.message.reply_text("Memoria, profilo ed entita' cancellati.")
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

    async def _skill_add(self, update, ctx, source: str, allow_local: bool, label: str | None = None) -> None:
        chat_id, uid = update.effective_chat.id, update.effective_user.id
        text = await self._with_typing(ctx, chat_id, add_skill_flow(
            self.service, source, allow_local=allow_local, user=str(uid), channel="telegram", label=label,
            ask=lambda q: self.ask_yes_no(ctx.bot, chat_id, uid, q)))
        await send_safe(update, text, self.s.reply_format)   # il testo ha backtick: formattato, con ripiego su testo semplice

    async def on_skill_add(self, update, ctx):
        if not await self._skill_gate(update):
            return
        source = " ".join(ctx.args or []).strip()
        if not source:
            return await update.message.reply_text(_SKILL_ADD_USAGE)
        await self._skill_add(update, ctx, source, allow_local=False)   # da Telegram mai percorsi locali

    async def on_skill_remove(self, update, ctx):
        if not await self._skill_gate(update):
            return
        name = " ".join(ctx.args or []).strip()
        if not name:
            return await update.message.reply_text("Uso: /skill_remove <nome>")
        await update.message.reply_text(await remove_skill_flow(
            self.service, name, user=str(update.effective_user.id), channel="telegram"))

    async def _skill_from_attachment(self, update, ctx, doc) -> None:
        """Zip allegato con didascalia /skill_add: scaricato in inbox, installato, cancellato sempre."""
        if not await self._skill_gate(update):
            return
        if Path(doc.file_name or "").suffix.lower() != ".zip":
            return await update.message.reply_text(_SKILL_ADD_USAGE)
        if (doc.file_size or 0) > self.s.max_upload_mb * 1024 * 1024:
            return await update.message.reply_text(f"File troppo grande (max {self.s.max_upload_mb} MB).")
        inbox = self.s.data_dir / "inbox"
        inbox.mkdir(parents=True, exist_ok=True)
        path = inbox / f"{uuid.uuid4().hex}.zip"
        try:
            try:
                await (await doc.get_file()).download_to_drive(custom_path=path)
            except Exception:
                logger.exception("Download dello zip della skill fallito")
                return await update.message.reply_text("Impossibile scaricare il file, riprova.")
            await self._skill_add(update, ctx, str(path), allow_local=True,   # lo zip e' quello scaricato dal bot
                                  label=doc.file_name)   # nel log il nome originale, non il percorso in inbox
        finally:
            path.unlink(missing_ok=True)

    async def on_schedules(self, update, ctx):
        if self.authorized(update):
            await update.message.reply_text(format_schedules(self.service.scheduler.list(str(update.effective_user.id))))

    async def on_trace(self, update, ctx):
        if self.authorized(update):
            for chunk in split_text(trace_text(self.s, str(update.effective_user.id))):
                await update.message.reply_text(chunk)

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

    def _run_ctx(self, ctx, chat_id: int, uid: int, **kw) -> RunCtx:
        return RunCtx(user_id=str(uid), channel="telegram", target=str(chat_id),
                      confirm=lambda code, language: self.confirm_code(ctx.bot, chat_id, uid, code, language), **kw)

    async def _ask(self, update, ctx, text: str, target: str = "auto", **ctx_kw):
        async with self._locks[update.effective_chat.id]:
            await self._ask_locked(update, ctx, text, target, **ctx_kw)

    async def _ask_locked(self, update, ctx, text: str, target: str = "auto", **ctx_kw):
        """Come _ask, per chi tiene gia' il lock della chat (trascrizione + richiesta in un solo turno)."""
        chat_id, uid = update.effective_chat.id, update.effective_user.id
        try:
            reply = await self._with_typing(ctx, chat_id, self.service.ask(
                text, user_id=str(uid), session_id=self.session_id(ctx, chat_id),
                ctx=self._run_ctx(ctx, chat_id, uid, **ctx_kw), target=target))
            await self.send_reply(update, reply)
        except DocumentError as e:
            await update.message.reply_text(str(e))
        except Exception:
            logger.exception("Errore nel run")
            await update.message.reply_text("Errore interno durante l'elaborazione. Riprova tra poco.")

    # -- messaggi vocali e audio ----------------------------------------------------------
    async def on_voice(self, update, ctx):
        if not self.authorized(update) or not update.message:
            return
        media = update.message.voice or update.message.audio
        if media is not None:
            await self._transcribe_and_ask(update, ctx, media, (update.message.caption or "").strip())

    @staticmethod
    def _audio_ext(media, is_voice: bool) -> str:
        suffix = Path(getattr(media, "file_name", None) or "").suffix.lower()
        mime = (getattr(media, "mime_type", None) or "").lower()
        return suffix or _AUDIO_EXT.get(mime) or mimetypes.guess_extension(mime) or (".ogg" if is_voice else ".bin")

    async def _transcribe_and_ask(self, update, ctx, media, caption: str) -> None:
        """Vocale/audio -> stt -> eco "🎤 ..." -> router, come un messaggio scritto. Il file non resta su disco."""
        s, chat_id, reply = self.s, update.effective_chat.id, update.message.reply_text
        async with self._locks[chat_id]:
            if not s.stt_url:
                return await reply("I messaggi vocali non sono abilitati.")
            too_long = f"Vocale troppo lungo (max {s.max_voice_s // 60} minuti)."
            if (getattr(media, "duration", None) or 0) > s.max_voice_s:
                return await reply(too_long)
            if (media.file_size or 0) > s.max_upload_mb * 1024 * 1024:
                return await reply(f"File troppo grande (max {s.max_upload_mb} MB).")
            is_voice = media is getattr(update.message, "voice", None)
            ext = self._audio_ext(media, is_voice)
            name = getattr(media, "file_name", None) or f"vocale{ext}"
            inbox = s.data_dir / "inbox"
            inbox.mkdir(parents=True, exist_ok=True)
            path = inbox / f"{uuid.uuid4().hex}{ext}"
            try:
                try:
                    tg_file = await media.get_file()
                    await tg_file.download_to_drive(custom_path=path)
                except Exception:
                    logger.exception("Download del vocale fallito")
                    return await reply("Impossibile scaricare il vocale, riprova.")
                try:
                    result = await self._with_typing(ctx, chat_id, transcribe(s, path, name))
                except SttError as e:
                    if e.kind == "unavailable":
                        logger.exception("Trascrizione non disponibile")
                    else:
                        logger.warning("Trascrizione rifiutata: %s", e)
                    return await reply(too_long if e.kind == "too_long" else _STT_MESSAGES[e.kind])
                text = result.text.strip()
                if not text:
                    return await reply("Non ho capito il vocale, puoi ripeterlo o scriverlo?")
                for chunk in split_text(f"🎤 {text}"):     # testo semplice: niente Markdown da rompere
                    await reply(chunk)
                prompt = f"{caption}\n\n[Trascrizione audio]: {text}" if caption else text
                await self._ask_locked(update, ctx, prompt)
            finally:
                path.unlink(missing_ok=True)   # l'audio non resta sul server

    async def on_message(self, update, ctx):
        if not self.authorized(update) or not update.message or not update.message.text:
            return
        logger.info("Messaggio user=%s chat=%s len=%d", update.effective_user.id, update.effective_chat.id,
                    len(update.message.text))
        await self._ask(update, ctx, update.message.text)

    async def _explicit(self, update, ctx, target: str):
        if not self.authorized(update):
            return
        text = ((update.message.text or "").split(maxsplit=1) + [""])[1].strip()
        if not text:
            return await update.message.reply_text(f"Uso: /{target} <richiesta>")
        await self._ask(update, ctx, text, target=target)

    async def on_simple(self, update, ctx):
        await self._explicit(update, ctx, "simple")

    async def on_complex(self, update, ctx):
        await self._explicit(update, ctx, "complex")

    async def _with_document(self, update, ctx, doc, handler) -> None:
        """Scarica il documento in inbox, esegue handler(path) e lo cancella sempre."""
        ext = Path(doc.file_name or "").suffix.lower()
        if ext not in SUPPORTED:
            return await update.message.reply_text("Formato non supportato. Ammessi: PDF, DOCX, TXT, MD, CSV, JSON, LOG.")
        if (doc.file_size or 0) > self.s.max_upload_mb * 1024 * 1024:
            return await update.message.reply_text(f"File troppo grande (max {self.s.max_upload_mb} MB).")
        inbox = self.s.data_dir / "inbox"
        inbox.mkdir(parents=True, exist_ok=True)
        path = inbox / f"{uuid.uuid4().hex}{ext}"
        try:
            tg_file = await doc.get_file()
            await tg_file.download_to_drive(custom_path=path)
            await handler(path)
        finally:
            path.unlink(missing_ok=True)   # il documento non resta sul server

    async def _send_summary(self, update, ctx, summarize, what: str) -> None:
        """summarize(session_id) -> coroutine del riassunto; i DocumentError arrivano all'utente come messaggio."""
        chat_id = update.effective_chat.id
        async with self._locks[chat_id]:
            try:
                text = await self._with_typing(ctx, chat_id, summarize(self.session_id(ctx, chat_id)))
                await send_safe(update, text, self.s.reply_format)
            except DocumentError as e:
                await update.message.reply_text(str(e))
            except Exception:
                logger.exception("Errore riassunto %s", what)
                await update.message.reply_text(f"Errore durante il riassunto {what}.")

    async def _summarize_direct(self, update, ctx, doc, instruction: str) -> None:
        uid = str(update.effective_user.id)

        async def run(path):
            await self._send_summary(update, ctx, lambda sid: self.service.summarize(
                path, instruction, user_id=uid, name=doc.file_name, session_id=sid), "del documento")
        await self._with_document(update, ctx, doc, run)

    async def on_document(self, update, ctx):
        if not self.authorized(update) or not update.message or not update.message.document:
            return
        doc, caption = update.message.document, (update.message.caption or "").strip()
        words = caption.lower().split(maxsplit=1)
        if words and words[0].partition("@")[0] == "/skill_add":   # anche /skill_add@NomeBot
            return await self._skill_from_attachment(update, ctx, doc)
        if (getattr(doc, "mime_type", None) or "").startswith("audio/"):   # file audio inviato come documento
            return await self._transcribe_and_ask(update, ctx, doc, caption)
        if caption.lower().startswith("/riassumi"):           # richiamo esplicito del workflow
            return await self._summarize_direct(update, ctx, doc, caption[len("/riassumi"):].strip())
        name = doc.file_name or "documento"

        async def run(path):                                     # decide il router
            await self._ask(update, ctx, f"[Documento caricato: {name}] {caption}".strip(),
                            document=path, document_name=name)
        await self._with_document(update, ctx, doc, run)

    async def on_riassumi(self, update, ctx):
        if not self.authorized(update):
            return
        args = ctx.args or []
        if args and is_url(args[0]):                              # /riassumi <link> [istruzioni]
            uid = str(update.effective_user.id)
            return await self._send_summary(update, ctx, lambda sid: self.service.summarize_url(
                args[0], " ".join(args[1:]), user_id=uid, session_id=sid), "della pagina")
        replied = getattr(update.message, "reply_to_message", None)
        doc = getattr(replied, "document", None) if replied else None
        if doc is None:
            return await update.message.reply_text(_RIASSUMI_USAGE)
        await self._summarize_direct(update, ctx, doc, " ".join(args))


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
    app.add_handler(CommandHandler("skill_add", gw.on_skill_add))
    app.add_handler(CommandHandler("skill_remove", gw.on_skill_remove))
    app.add_handler(CommandHandler("simple", gw.on_simple))
    app.add_handler(CommandHandler("complex", gw.on_complex))
    app.add_handler(CommandHandler("riassumi", gw.on_riassumi))
    app.add_handler(CommandHandler("unschedule", gw.on_unschedule))
    app.add_handler(CommandHandler("trace", gw.on_trace))
    app.add_handler(CallbackQueryHandler(gw.on_callback, pattern=r"^cf:"))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, gw.on_voice))
    app.add_handler(MessageHandler(filters.Document.ALL, gw.on_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, gw.on_message))
    return app, gw
