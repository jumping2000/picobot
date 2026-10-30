"""Configurazione centralizzata validata con pydantic-settings.

Precedenza, dal piu' forte: argomenti di Settings(...), ambiente, .env, config/config.yaml (a blocchi), default.
"""
import logging
import os
import re
from collections.abc import Hashable
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import yaml
from dotenv import dotenv_values
from pydantic import Field, TypeAdapter, ValidationError
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict

logger = logging.getLogger(__name__)

CONFIG_FILE = Path("config/config.yaml")   # relativo alla cartella di lavoro (/app nel container)

# solo in .env: nello YAML sono un errore
ENV_ONLY = frozenset({
    "openrouter_api_key", "openai_api_key", "openrouter_base_url", "llm_model_id", "llm_strong_model_id",
    "telegram_bot_token", "telegram_allowed_user_ids", "api_tokens", "cli_user_id", "admin_user_ids",
})

BLOCKS: dict[str, tuple[str, ...]] = {
    "telegram": ("allow_all_users", "reply_format"),
    "paths": ("data_dir", "workspace_dir", "mcp_config_path"),
    "memory": ("history_runs", "enable_memory", "enable_learning", "enable_session_summaries", "enable_critic",
               "team_max_iterations"),
    "web": ("region",),
    "code": ("code_timeout_s", "code_max_output", "confirm_timeout_s", "code_node_mem_mb", "code_max_runs",
             "node_path"),
    "outputs": ("max_output_mb", "max_output_files", "output_extensions", "outbox_ttl_h"),
    "trace": ("trace_enabled", "trace_max_mb"),
    "skills": ("enable_skills", "skills_dir", "skills_list_max", "skills_router_hint_max"),
    "documents": ("max_upload_mb", "doc_chunk_chars", "doc_max_chars"),
    "voice": ("stt_url", "stt_timeout_s", "max_voice_s"),
    "scheduler": ("timezone", "schedule_min_interval_min", "max_schedules_per_user"),
    "api": ("api_enabled", "api_host", "api_port", "api_ssl_certfile", "api_ssl_keyfile"),
}


class ConfigError(ValueError):
    """config.yaml sbagliato: il bot non parte."""


_VAR = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


def expand_vars(value, env: dict):
    """Sostituisce ${NOME} in tutte le stringhe (config dei server MCP e config.yaml)."""
    if isinstance(value, str):
        def sub(m: re.Match) -> str:
            if env.get(m.group(1)) is None:
                raise ValueError(f"variabile d'ambiente {m.group(1)} non definita")
            return env[m.group(1)]
        return _VAR.sub(sub, value)
    if isinstance(value, list):
        return [expand_vars(v, env) for v in value]
    if isinstance(value, dict):
        return {k: expand_vars(v, env) for k, v in value.items()}
    return value


class _UniqueKeyLoader(yaml.SafeLoader):
    """Come safe_load, ma un blocco o una chiave ripetuti sono un errore (PyYAML terrebbe l'ultimo in silenzio)."""

    def construct_mapping(self, node, deep=False):
        seen = set()
        for key_node, _ in node.value:
            key = self.construct_object(key_node, deep=deep)
            if not isinstance(key, Hashable):   # lo segnala gia' SafeLoader
                continue
            if key in seen:
                raise yaml.constructor.ConstructorError(None, None, f"chiave ripetuta: {key}", key_node.start_mark)
            seen.add(key)
        return super().construct_mapping(node, deep)


class YamlBlocksSource(PydanticBaseSettingsSource):
    """Appiattisce i blocchi di config.yaml nei campi di Settings, con errori che nominano blocco.chiave."""

    def get_field_value(self, field, field_name):
        return None, field_name, False

    def __call__(self) -> dict[str, Any]:
        path = CONFIG_FILE
        if not path.exists():
            return {}
        try:
            text = path.read_text(encoding="utf-8-sig")   # -sig: file salvati su Windows con BOM
        except (OSError, UnicodeDecodeError) as e:      # es. salvato in ANSI con un accento
            raise ConfigError(f"{path}: file illeggibile (serve UTF-8): {e}") from None
        try:
            data = yaml.load(text, Loader=_UniqueKeyLoader)
        except yaml.YAMLError as e:
            raise ConfigError(f"{path}: YAML non valido: {e}") from None
        if data is None:
            return {}
        if not isinstance(data, dict):
            raise ConfigError(f"{path}: la radice deve contenere blocchi (telegram:, memory:, ...)")
        env = {**{k: v for k, v in dotenv_values(".env").items() if v is not None}, **os.environ}
        defined = {k.lower() for k in env}   # pydantic-settings non distingue le maiuscole
        owner = {f: b for b, fields in BLOCKS.items() for f in fields}
        out: dict[str, Any] = {}
        for block, keys in data.items():
            if block not in BLOCKS:
                raise ConfigError(f"{path}: {block}: blocco sconosciuto")
            if keys is None:   # blocco con tutte le chiavi commentate
                continue
            if not isinstance(keys, dict):
                raise ConfigError(f"{path}: {block}: deve contenere chiavi")
            for key, value in keys.items():
                where = f"{path}: {block}.{key}"
                if key in ENV_ONLY:
                    raise ConfigError(f"{where}: va in .env come {key.upper()}")
                if key not in BLOCKS[block]:
                    raise ConfigError(f"{where}: chiave del blocco '{owner[key]}'" if key in owner
                                      else f"{where}: chiave sconosciuta")
                try:
                    value = expand_vars(value, env)
                except ValueError as e:
                    raise ConfigError(f"{where}: {e}") from None
                try:
                    TypeAdapter(self.settings_cls.model_fields[key].annotation).validate_python(value)
                except ValidationError as e:
                    raise ConfigError(f"{where}: {e.errors()[0]['msg']}") from None
                if key in defined:
                    logger.warning("%s (ambiente/.env) prevale su %s.%s (%s)", key.upper(), block, key, path)
                out[key] = value
        return out


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- Telegram ---
    telegram_bot_token: str = ""
    telegram_allowed_user_ids: str = ""   # CSV; vuoto = nessuno (fail-closed)
    allow_all_users: bool = False
    # markdown (semplice) | markdownv2 | html: come PicoBot formatta le risposte su Telegram
    reply_format: Literal["markdown", "markdownv2", "html"] = "markdown"
    admin_user_ids: str = ""              # CSV; vuoto = /skill_add e /skill_remove spenti (fail-closed)

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
    team_max_iterations: int = 3

    # --- Ricerca web ---
    region: str = "it-it"   # regione dei risultati DDGS (es. us-en, uk-en)

    # --- Codice generato ---
    code_timeout_s: int = 30
    code_max_output: int = 4000
    confirm_timeout_s: int = 120

    code_node_mem_mb: int = 1536   # pptxgenjs va in abort a 768 MB
    code_max_runs: int = 6         # esecuzioni approvate per richiesta
    node_path: str = ""            # NODE_PATH per gli script Node (pacchetti globali)

    # --- File in uscita ---
    max_output_mb: int = 20
    max_output_files: int = 5
    output_extensions: str = "docx,pptx,xlsx,csv,txt,md,pdf,html,json,py"
    outbox_ttl_h: int = 24

    # --- Traccia delle richieste ---
    trace_enabled: bool = False   # una riga JSON per richiesta in data/trace.jsonl; /trace mostra l'ultima
    trace_max_mb: int = 5         # oltre, trace.jsonl diventa trace.jsonl.1

    # --- Skill ---
    enable_skills: bool = True
    skills_dir: Path = Path("/app/skills")
    skills_list_max: int = 50
    skills_router_hint_max: int = 15

    # --- Documenti ---
    max_upload_mb: int = 15
    doc_chunk_chars: int = 100000   # sotto questa soglia il riassunto e' 1 sola chiamata
    doc_max_chars: int = 400000

    # --- Messaggi vocali (STT) ---
    stt_url: str = ""          # es. http://stt:8000 (servizio del profilo compose "stt"); vuoto = vocali spenti
    stt_timeout_s: int = 180
    max_voice_s: int = 300     # durata massima, controllata prima del download

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

    @classmethod
    def settings_customise_sources(cls, settings_cls, init_settings, env_settings, dotenv_settings,
                                   file_secret_settings):
        return init_settings, env_settings, dotenv_settings, YamlBlocksSource(settings_cls), file_secret_settings

    @property
    def api_key(self) -> str:
        return self.openrouter_api_key or self.openai_api_key

    @property
    def allowed_ids(self) -> set[int]:
        return {int(x) for x in self.telegram_allowed_user_ids.split(",") if x.strip()}

    @property
    def admin_ids(self) -> set[int]:
        return {int(x) for x in self.admin_user_ids.split(",") if x.strip()}

    @property
    def database_file(self) -> Path:
        return self.data_dir / "picobot.db"

    @property
    def trace_file(self) -> Path:
        return self.data_dir / "trace.jsonl"

    @property
    def output_ext_set(self) -> set[str]:
        return {e.strip().lower().lstrip(".") for e in self.output_extensions.split(",") if e.strip()}

    @property
    def outputs_dir(self) -> Path:
        return self.workspace_dir / "outputs"

    @property
    def outbox_dir(self) -> Path:
        return self.data_dir / "outbox"

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
