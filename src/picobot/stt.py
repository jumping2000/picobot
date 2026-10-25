"""Client del servizio di trascrizione (endpoint compatibile OpenAI POST /v1/audio/transcriptions).

Il servizio `stt` gira in un container separato (faster-whisper su CPU); qui solo HTTP, nessun modello.
"""
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import httpx

from .config import Settings

SttKind = Literal["unavailable", "unreadable", "too_long"]


@dataclass
class Transcript:
    text: str
    language: str


class SttError(Exception):
    def __init__(self, kind: SttKind, detail: str = ""):
        super().__init__(f"{kind}: {detail}" if detail else kind)
        self.kind = kind


_STATUS_KIND: dict[int, SttKind] = {400: "unreadable", 413: "too_long"}


async def transcribe(s: Settings, path: Path, filename: str,
                     transport: httpx.AsyncBaseTransport | None = None) -> Transcript:
    """Trascrive il file audio. Solleva SttError (kind: unavailable | unreadable | too_long)."""
    url = f"{s.stt_url.rstrip('/')}/v1/audio/transcriptions"
    try:
        async with httpx.AsyncClient(timeout=s.stt_timeout_s, transport=transport) as client:
            with path.open("rb") as f:
                r = await client.post(url, files={"file": (filename, f)})
    except httpx.HTTPError as e:   # server giu', timeout, connessione interrotta
        raise SttError("unavailable", type(e).__name__) from e
    if r.status_code != 200:
        raise SttError(_STATUS_KIND.get(r.status_code, "unavailable"), f"HTTP {r.status_code}")
    try:
        data = r.json()
        return Transcript(str(data["text"]).strip(), str(data.get("language", "")))
    except (ValueError, KeyError, TypeError) as e:
        raise SttError("unavailable", "risposta non valida") from e
