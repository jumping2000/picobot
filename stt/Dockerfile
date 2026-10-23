FROM python:3.11-slim

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1

COPY --from=ghcr.io/astral-sh/uv:0.5 /uv /usr/local/bin/

# dipendenze (layer in cache): faster-whisper decodifica OGG/Opus, mp3, m4a e wav con PyAV, senza ffmpeg di sistema
# versioni esatte dal lock: una nuova release di una dipendenza non rompe la build (PyAV 19 l'ha gia' fatto)
COPY pyproject.toml uv.lock ./
RUN uv sync --no-dev --frozen

COPY *.py ./

# utente non root; i modelli si scaricano al primo avvio nel volume /models (HF_HOME)
RUN useradd -m -u 1000 stt && mkdir -p /models && chown stt /models
USER stt
ENV PATH="/app/.venv/bin:$PATH" HF_HOME=/models

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=300s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=3)" || exit 1
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
