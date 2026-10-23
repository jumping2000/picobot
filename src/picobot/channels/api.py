"""Canale API REST (FastAPI) con bearer token. Token -> user_id (memoria separata per utente)."""
import asyncio
import hmac
import logging
import re
import uuid
from collections import defaultdict
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from pydantic import BaseModel, Field

from .. import __version__
from ..config import Settings
from ..context import RunCtx
from ..documents import SUPPORTED, DocumentError
from ..scheduler import ScheduleError
from ..service import PicoBotService

logger = logging.getLogger(__name__)


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    session_id: str | None = Field(default=None, max_length=80, pattern=r"^[A-Za-z0-9_\-]+$")
    approve_code: bool = Field(default=False, description="Pre-approva l'esecuzione di codice Python in questa richiesta")


class ChatOut(BaseModel):
    answer: str
    session_id: str


class ScheduleIn(BaseModel):
    cron: str = Field(max_length=100)
    prompt: str = Field(min_length=1, max_length=1000)


def create_app(s: Settings, service: PicoBotService) -> FastAPI:
    app = FastAPI(title="PicoBot API", version=__version__)
    tokens = s.token_map
    locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    async def auth(authorization: Annotated[str | None, Header()] = None) -> str:
        if not authorization or not authorization.lower().startswith("bearer "):
            raise HTTPException(401, "Token mancante", headers={"WWW-Authenticate": "Bearer"})
        given, user = authorization[7:].strip(), None
        for known, uid in tokens.items():      # confronto a tempo costante, senza uscita anticipata
            if hmac.compare_digest(given.encode(), known.encode()):
                user = uid
        if user is None:
            raise HTTPException(401, "Token non valido", headers={"WWW-Authenticate": "Bearer"})
        return user

    User = Annotated[str, Depends(auth)]

    @app.get("/health")
    async def health():
        return {"status": "ok", "version": __version__}

    @app.post("/v1/chat", response_model=ChatOut)
    async def chat(body: ChatIn, user: User):
        sid = f"api-{user}-{body.session_id or uuid.uuid4().hex[:8]}"
        ctx = RunCtx(user_id=user, channel="api", pre_approved=body.approve_code)
        async with locks[sid]:
            try:
                answer = await service.ask(body.message, user_id=user, session_id=sid, ctx=ctx)
            except Exception:
                logger.exception("Errore /v1/chat")
                raise HTTPException(500, "Errore interno")
        return ChatOut(answer=answer, session_id=sid.removeprefix(f"api-{user}-"))

    @app.post("/v1/summarize")
    async def summarize(user: User, file: UploadFile = File(...), instruction: str = Form(""),
                        session_id: str | None = Form(None)):
        ext = Path(file.filename or "").suffix.lower()
        if session_id is not None and not re.fullmatch(r"[A-Za-z0-9_\-]{1,80}", session_id):
            raise HTTPException(422, "session_id non valido")
        short = session_id or uuid.uuid4().hex[:8]
        if ext not in SUPPORTED:
            raise HTTPException(415, "Formato non supportato (PDF, DOCX, TXT, MD, CSV, JSON, LOG)")
        inbox = s.data_dir / "inbox"
        inbox.mkdir(parents=True, exist_ok=True)
        path, limit, size = inbox / f"{uuid.uuid4().hex}{ext}", s.max_upload_mb * 1024 * 1024, 0
        try:
            with path.open("wb") as f:
                while chunk := await file.read(1024 * 1024):
                    size += len(chunk)
                    if size > limit:
                        raise HTTPException(413, f"File troppo grande (max {s.max_upload_mb} MB)")
                    f.write(chunk)
            summary = await service.summarize(path, instruction[:1000], user_id=user, name=file.filename or "",
                                              session_id=f"api-{user}-{short}")
            return {"summary": summary, "session_id": short}   # usa session_id in /v1/chat per le domande di follow-up
        except DocumentError as e:
            raise HTTPException(422, str(e))
        finally:
            path.unlink(missing_ok=True)

    @app.get("/v1/memory")
    async def get_memory(user: User):
        return {"memories": await service.memories(user)}

    @app.delete("/v1/memory", status_code=204)
    async def delete_memory(user: User, confirm: bool = False):
        if not confirm:
            raise HTTPException(400, "Passa ?confirm=true per cancellare tutta la memoria")
        await service.forget(user)

    @app.get("/v1/schedules")
    async def list_schedules(user: User):
        return {"schedules": service.scheduler.list(user)}

    @app.post("/v1/schedules", status_code=201)
    async def add_schedule(body: ScheduleIn, user: User):
        try:
            return {"id": service.scheduler.add(user, "api", user, body.cron, body.prompt)}
        except ScheduleError as e:
            raise HTTPException(422, str(e))

    @app.delete("/v1/schedules/{sid}", status_code=204)
    async def delete_schedule(sid: int, user: User):
        if not service.scheduler.remove(user, sid):
            raise HTTPException(404, "Task non trovato")

    return app
