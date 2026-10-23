"""API del servizio stt con un trascrittore finto: nessun modello, nessuna rete."""
import asyncio
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest
from fastapi.testclient import TestClient

from app import create_app
from settings import SttSettings
from transcriber import AudioClip, AudioError

URL = "/v1/audio/transcriptions"
AUDIO = {"file": ("v.ogg", b"audio")}


class FakeTranscriber:
    def __init__(self, text="ciao", duration=3.0, probs=(("es", 0.6), ("it", 0.4))):
        self.text, self.duration, self.probs = text, duration, list(probs)
        self.loaded = False
        self.languages_used: list[str] = []
        self.max_concurrency = 0
        self._active = 0
        self._guard = threading.Lock()

    def load(self):
        self.loaded = True

    def decode(self, path):
        with open(path, "rb") as f:
            if f.read() == b"bad":
                raise AudioError("audio non decodificabile")
        return AudioClip(None, self.duration)

    def language_probs(self, clip):
        return self.probs

    def transcribe(self, clip, language):
        with self._guard:
            self._active += 1
            self.max_concurrency = max(self.max_concurrency, self._active)
        time.sleep(0.05)
        with self._guard:
            self._active -= 1
        self.languages_used.append(language)
        return self.text


@pytest.fixture
def fake():
    return FakeTranscriber()


@pytest.fixture
def client(fake):
    with TestClient(create_app(SttSettings(max_mb=1, max_seconds=300), fake)) as c:   # lifespan: load()
        yield c


def test_transcription_ok(client, fake):
    r = client.post(URL, files=AUDIO)
    assert fake.loaded
    assert r.status_code == 200 and r.json() == {"text": "ciao", "language": "it", "duration": 3.0}


def test_health_after_load(client):
    r = client.get("/health")
    assert r.status_code == 200 and r.json() == {"status": "ok", "model": "small"}


def test_language_chosen_among_allowed(client, fake):
    client.post(URL, files=AUDIO)
    assert fake.languages_used == ["it"]


def test_explicit_language_is_respected(client, fake):
    r = client.post(URL, files=AUDIO, data={"language": "en", "model": "whisper-1"})
    assert fake.languages_used == ["en"] and r.json()["language"] == "en"


def test_silence_returns_empty_text(client, fake):
    fake.text = ""
    r = client.post(URL, files=AUDIO)
    assert r.status_code == 200 and r.json()["text"] == ""


def test_not_ready_before_load(fake):
    async def t():
        app = create_app(SttSettings(), fake)              # ASGITransport non esegue il lifespan
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
            return (await c.get("/health")).status_code, (await c.post(URL, files=AUDIO)).status_code
    assert asyncio.run(t()) == (503, 503) and not fake.loaded


def test_requests_are_serialized(client, fake):
    with ThreadPoolExecutor(3) as pool:
        codes = list(pool.map(lambda _: client.post(URL, files=AUDIO).status_code, range(3)))
    assert codes == [200, 200, 200] and fake.max_concurrency == 1


def test_errors(client, fake):
    assert client.post(URL).status_code == 400                                          # senza file
    assert client.post(URL, files={"file": ("x.ogg", b"bad")}).status_code == 400          # AudioError
    assert client.post(URL, files={"file": ("x.ogg", b"a" * (1024 * 1024 + 1))}).status_code == 413
    fake.duration = 301.0
    assert client.post(URL, files=AUDIO).status_code == 413                                # oltre max_seconds
    assert fake.languages_used == []                                                       # mai trascritto
