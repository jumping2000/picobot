"""Configurazione centralizzata (env / .env) validata con pydantic-settings."""
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- Telegram ---
    telegram_bot_token: str = ""
    telegram_allowed_user_ids: str = ""   # CSV; vuoto = nessuno (fail-closed)
    allow_all_users: bool = False

    # --- LLM ---
    openrouter_api_key: str = Field(default="", validation_alias="OPENROUTER_API_KEY")
    openai_api_key: str = Field(default="", validation_alias="OPENAI_API_KEY")
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    llm_model_id: str = "openai/gpt-4o-mini"   # economico: router, specialisti, documenti
    llm_strong_model_id: str = ""              # solo ComplexTeam (vuoto = llm_model_id)

    # --- Percorsi ---
    data_dir: Path = Path("/app/data")           # DB, stato Telegram (NON visibile al codice generato)
    workspace_dir: Path = Path("/app/workspace")  # file di lavoro dell'agente
    mcp_config_path: Path = Path("/app/config/mcp_config.json")

    # --- Sessione / memoria / costi ---
    history_runs: int = 6
    enable_memory: bool = True
    enable_learning: bool = True
    enable_session_summaries: bool = False   # +1 chiamata LLM per run: off di default
    enable_critic: bool = True
    team_max_iterations: int = 8

    # --- Codice generato ---
    code_timeout_s: int = 30
    code_max_output: int = 4000
    confirm_timeout_s: int = 120

    # --- Documenti ---
    max_upload_mb: int = 15
    doc_chunk_chars: int = 20000
    doc_max_chars: int = 400000

    # --- Scheduler ---
    timezone: str = "Europe/Rome"
    schedule_min_interval_min: int = 30
    max_schedules_per_user: int = 10

    # --- CLI / API ---
    cli_user_id: str = "cli"
    api_enabled: bool = True
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    api_ssl_certfile: str = ""   # opzionale: HTTPS diretto (uvicorn), senza reverse proxy
    api_ssl_keyfile: str = ""
    api_tokens: str = ""   # CSV "token:user_id" (user_id = id Telegram per condividere la memoria)

    @property
    def api_key(self) -> str:
        return self.openrouter_api_key or self.openai_api_key

    @property
    def allowed_ids(self) -> set[int]:
        return {int(x) for x in self.telegram_allowed_user_ids.split(",") if x.strip()}

    @property
    def database_file(self) -> Path:
        return self.data_dir / "picobot.db"

    @property
    def strong_model_id(self) -> str:
        return self.llm_strong_model_id or self.llm_model_id

    @property
    def token_map(self) -> dict[str, str]:
        out = {}
        for item in self.api_tokens.split(","):
            if ":" in item:
                tok, uid = item.strip().split(":", 1)
                if tok and uid:
                    out[tok] = uid
        return out


@lru_cache
def get_settings() -> Settings:
    return Settings()
