"""Decodifica reale con faster-whisper/PyAV (nessun modello): protegge dalle incompatibilita' tra le due librerie.

Un vocale Telegram e' OGG/Opus: lo si genera al volo con PyAV.
"""
import av
import numpy as np
import pytest

from settings import SttSettings
from transcriber import AudioError, FasterWhisperTranscriber


def _ogg_opus(path, seconds=2.0, rate=48000):
    with av.open(str(path), "w", format="ogg") as c:
        s = c.add_stream("libopus", rate=rate)
        s.layout = "mono"
        t = np.arange(int(rate * seconds)) / rate
        data = (0.3 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
        for i in range(0, len(data), 960):
            frame = av.AudioFrame.from_ndarray(data[i:i + 960].reshape(1, -1), format="flt", layout="mono")
            frame.sample_rate = rate
            for packet in s.encode(frame):
                c.mux(packet)
        for packet in s.encode(None):
            c.mux(packet)


def test_decode_telegram_ogg_opus(tmp_path):
    path = tmp_path / "voce.ogg"
    _ogg_opus(path)
    clip = FasterWhisperTranscriber(SttSettings()).decode(str(path))
    assert clip.duration == pytest.approx(2.0, abs=0.1) and len(clip.samples) == pytest.approx(32000, abs=1600)


def test_decode_garbage_raises_audio_error(tmp_path):
    path = tmp_path / "rotto.ogg"
    path.write_bytes(b"non e' audio")
    with pytest.raises(AudioError):
        FasterWhisperTranscriber(SttSettings()).decode(str(path))
