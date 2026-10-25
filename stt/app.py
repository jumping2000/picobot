"""API del servizio stt: sottoinsieme compatibile OpenAI di POST /v1/audio/transcriptions.

Il modello si carica una volta all'avvio (lifespan); una trascrizione alla volta (sul N100 due in parallelo
andrebbero entrambe piu' lente). Nessun file audio resta su disco dopo la richiesta.
"""
import asyncio
import os
import tempfile
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from settings import SttSettings
from transcriber import AudioError, Transcriber, choose_language

_CHUNK = 1024 * 1024


def create_app(settings: SttSettings, transcriber: Transcriber) -> FastAPI:
    state = {"ready": False}
    lock = asyncio.Lock()

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        await asyncio.to_thread(transcriber.load)
        state["ready"] = True
        yield

    app = FastAPI(title="PicoBot STT", lifespan=lifespan)

    @app.get("/health")
    async def health():
        if not state["ready"]:
            return JSONResponse({"status": "loading"}, status_code=503)
        return {"status": "ok", "model": settings.model}

    @app.post("/v1/audio/transcriptions")
    async def transcriptions(file: UploadFile | None = File(None), language: str | None = Form(None),
                             model: str | None = Form(None)):   # model: accettato per compatibilita', ignorato
        if not state["ready"]:
            raise HTTPException(503, "Modello non ancora caricato")
        if file is None:
            raise HTTPException(400, "File audio mancante")
        fd, path = tempfile.mkstemp(prefix="stt-")
        try:
            size, limit = 0, settings.max_mb * _CHUNK
            with os.fdopen(fd, "wb") as out:
                while chunk := await file.read(_CHUNK):
                    size += len(chunk)
                    if size > limit:
                        raise HTTPException(413, f"File troppo grande (max {settings.max_mb} MB)")
                    out.write(chunk)
            # durata dall'intestazione PRIMA di decodificare: un'ora di audio non va in memoria ne' blocca la coda
            probed = await asyncio.to_thread(transcriber.probe_duration, path)
            if probed is not None and probed > settings.max_seconds:
                raise HTTPException(413, f"Audio troppo lungo (max {settings.max_seconds} s)")
            async with lock:
                try:
                    clip = await asyncio.to_thread(transcriber.decode, path)
                except AudioError as e:
                    raise HTTPException(400, str(e)) from e
                if clip.duration > settings.max_seconds:
                    raise HTTPException(413, f"Audio troppo lungo (max {settings.max_seconds} s)")
                lang = language or choose_language(await asyncio.to_thread(transcriber.language_probs, clip),
                                                   settings.languages)
                text = await asyncio.to_thread(transcriber.transcribe, clip, lang)
            return {"text": text, "language": lang, "duration": round(clip.duration, 2)}
        finally:
            os.unlink(path)

    return app
