FROM python:3.11-slim

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1 \
    NODE_PATH=/usr/local/lib/node_modules

# base: node/npm (server MCP via npx, script delle skill), curl (healthcheck), git (skill da chat)
RUN apt-get update && apt-get install -y --no-install-recommends nodejs npm curl git \
    && rm -rf /var/lib/apt/lists/*

# uv per le dipendenze Python, uvx per i server MCP scritti in Python
COPY --from=ghcr.io/astral-sh/uv:0.5 /uv /uvx /usr/local/bin/

# layer dipendenze del bot (cache): solo metadati
COPY pyproject.toml README.md ./
RUN mkdir -p src/picobot && touch src/picobot/__init__.py && uv sync --no-dev

# ---- PUNTI DI ESTENSIONE: librerie richieste dalle skill (vedi deps/*.txt) ----
COPY deps/ /tmp/deps/
# 1) pacchetti di sistema
RUN pkgs="$(grep -v '^[[:space:]]*#' /tmp/deps/apt.txt | grep -v '^[[:space:]]*$' || true)"; \
    if [ -n "$pkgs" ]; then apt-get update && apt-get install -y --no-install-recommends $pkgs \
    && rm -rf /var/lib/apt/lists/*; fi
# 2) librerie Python nel venv del bot
RUN if grep -qv '^[[:space:]]*\(#\|$\)' /tmp/deps/pip.txt; then \
    uv pip install --python /app/.venv/bin/python -r /tmp/deps/pip.txt; fi
# 3) pacchetti Node globali (gli script li trovano tramite NODE_PATH)
RUN [ "$(npm root -g)" = "$NODE_PATH" ] || { echo "NODE_PATH ($NODE_PATH) diverso da 'npm root -g'"; exit 1; }; \
    pkgs="$(grep -v '^[[:space:]]*#' /tmp/deps/npm.txt | grep -v '^[[:space:]]*$' || true)"; \
    if [ -n "$pkgs" ]; then npm install -g $pkgs && npm cache clean --force; fi
# 4) hook libero
RUN bash /tmp/deps/setup.sh && rm -rf /tmp/deps

COPY src/ ./src/
# --inexact: non rimuovere le librerie delle skill installate da deps/pip.txt (non sono nel lock)
RUN uv sync --no-dev --inexact

# utente non-root. src/ e .venv restano di root (il codice generato non puo' modificarli);
# scrivibili solo data/ (DB, stato), workspace/ (file dell'agente) e skills/ (installazione da chat)
RUN useradd -m -u 1000 picobot && mkdir -p /app/data /app/workspace /app/skills \
    && chown picobot /app/data /app/workspace /app/skills
USER picobot
ENV PATH="/app/.venv/bin:$PATH" DATA_DIR=/app/data WORKSPACE_DIR=/app/workspace SKILLS_DIR=/app/skills API_HOST=0.0.0.0

EXPOSE 8000
HEALTHCHECK --interval=60s --timeout=5s CMD curl -fs http://localhost:8000/health || exit 0
CMD ["python", "-m", "picobot", "serve"]
