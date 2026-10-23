"""Punto d'ingresso per uvicorn: `uvicorn main:app`. Il modello si carica all'avvio, non all'import."""
from app import create_app
from settings import SttSettings
from transcriber import FasterWhisperTranscriber

settings = SttSettings.from_env()
app = create_app(settings, FasterWhisperTranscriber(settings))
