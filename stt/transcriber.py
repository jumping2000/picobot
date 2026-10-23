"""Trascrittore: interfaccia (sostituibile nei test) e implementazione faster-whisper su CPU.

faster_whisper si importa solo quando serve: i test e l'import di `main` non caricano il modello.
"""
from dataclasses import dataclass
from typing import Any, Protocol

from settings import SttSettings

SAMPLE_RATE = 16000


@dataclass
class AudioClip:
    samples: Any       # array numpy a 16 kHz (faster-whisper)
    duration: float    # secondi


class AudioError(ValueError):
    """Audio mancante, corrotto o in un formato non decodificabile."""


class Transcriber(Protocol):
    def load(self) -> None: ...
    def probe_duration(self, path: str) -> float | None: ...
    def decode(self, path: str) -> AudioClip: ...
    def language_probs(self, clip: AudioClip) -> list[tuple[str, float]]: ...
    def transcribe(self, clip: AudioClip, language: str) -> str: ...


def choose_language(probs: list[tuple[str, float]], allowed: list[str]) -> str:
    """La lingua piu' probabile tra quelle ammesse; se nessuna compare, la prima ammessa."""
    ranked = [(p, lang) for lang, p in probs if lang in allowed]
    return max(ranked)[1] if ranked else allowed[0]


class FasterWhisperTranscriber:
    def __init__(self, settings: SttSettings):
        self.s = settings
        self.model = None

    def load(self) -> None:
        from faster_whisper import WhisperModel

        self.model = WhisperModel(self.s.model, device="cpu", compute_type=self.s.compute_type,
                                  cpu_threads=self.s.threads)

    def probe_duration(self, path: str) -> float | None:
        """Durata dall'intestazione del file, senza decodificarlo (None se non disponibile)."""
        import av

        try:
            with av.open(path, mode="r") as container:
                if container.duration:
                    return container.duration / av.time_base
                stream = next((s for s in container.streams if s.type == "audio"), None)
                if stream is not None and stream.duration and stream.time_base:
                    return float(stream.duration * stream.time_base)
        except Exception:  # noqa: BLE001  file illeggibile: lo dira' decode()
            return None
        return None

    def decode(self, path: str) -> AudioClip:
        from faster_whisper import decode_audio

        try:
            samples = decode_audio(path, sampling_rate=SAMPLE_RATE)
        except Exception as e:  # noqa: BLE001  PyAV solleva tipi diversi per file corrotti o sconosciuti
            raise AudioError(f"audio non decodificabile: {type(e).__name__}") from e
        return AudioClip(samples, len(samples) / SAMPLE_RATE)

    def language_probs(self, clip: AudioClip) -> list[tuple[str, float]]:
        return list(self.model.detect_language(clip.samples, vad_filter=True)[2])

    def transcribe(self, clip: AudioClip, language: str) -> str:
        segments, _ = self.model.transcribe(clip.samples, language=language, beam_size=self.s.beam_size,
                                            vad_filter=True)
        return "".join(seg.text for seg in segments).strip()
