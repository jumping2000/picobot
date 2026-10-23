"""Client STT (compatibile OpenAI) con transport finto: nessuna rete."""
import asyncio

import httpx
import pytest

from picobot.config import Settings
from picobot.stt import SttError, Transcript, transcribe


def _run(handler, tmp_path):   # handler: httpx.Request -> httpx.Response
    p = tmp_path / "v.ogg"
    p.write_bytes(b"audio")
    s = Settings(stt_url="http://stt:8000/")
    return asyncio.run(transcribe(s, p, "v.ogg", transport=httpx.MockTransport(handler)))


def test_transcribe_ok(tmp_path):
    seen = {}

    def h(req):
        seen["url"], seen["body"] = str(req.url), req.read()
        return httpx.Response(200, json={"text": " ciao ", "language": "it", "duration": 1.0})
    assert _run(h, tmp_path) == Transcript("ciao", "it")
    assert seen["url"] == "http://stt:8000/v1/audio/transcriptions"
    assert b'filename="v.ogg"' in seen["body"] and b"audio" in seen["body"]


@pytest.mark.parametrize("status,kind", [(400, "unreadable"), (413, "too_long"), (500, "unavailable"), (503, "unavailable")])
def test_http_errors(tmp_path, status, kind):
    with pytest.raises(SttError) as e:
        _run(lambda r: httpx.Response(status), tmp_path)
    assert e.value.kind == kind


def test_network_errors(tmp_path):
    for exc in (httpx.ConnectError("x"), httpx.ReadTimeout("x")):
        def h(req, exc=exc):
            raise exc
        with pytest.raises(SttError) as e:
            _run(h, tmp_path)
        assert e.value.kind == "unavailable"


def test_malformed_json_is_unavailable(tmp_path):
    with pytest.raises(SttError) as e:
        _run(lambda r: httpx.Response(200, text="non json"), tmp_path)
    assert e.value.kind == "unavailable"


def test_settings_defaults():
    s = Settings()
    assert (s.stt_url, s.stt_timeout_s, s.max_voice_s) == ("", 180, 300)
