FROM python:3.11-slim

WORKDIR /app

# nodejs/npm: server MCP lanciati con npx
RUN apt-get update && apt-get install -y --no-install-recommends nodejs npm curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.5 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1

COPY pyproject.toml README.md ./
RUN mkdir -p src/picobot && touch src/picobot/__init__.py && uv sync --no-dev
COPY src/ ./src/
RUN uv sync --no-dev

# utente non-root; data (DB, stato) e workspace (file dell'agente) separati
RUN useradd -m -u 1000 picobot && mkdir -p /app/data /app/workspace && chown -R picobot /app
USER picobot
ENV PATH="/app/.venv/bin:$PATH" DATA_DIR=/app/data WORKSPACE_DIR=/app/workspace API_HOST=0.0.0.0

EXPOSE 8000
HEALTHCHECK --interval=60s --timeout=5s CMD curl -fs http://localhost:8000/health || exit 0
CMD ["python", "-m", "picobot", "serve"]
