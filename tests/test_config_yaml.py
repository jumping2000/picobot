"""config/config.yaml a blocchi: .env e ambiente vincono, errori bloccanti con blocco.chiave."""

import logging
import re

import pytest

import picobot.config
from picobot.config import BLOCKS, ENV_ONLY, ConfigError, Settings

VARS = ("HISTORY_RUNS", "REGION", "API_PORT", "STT_URL", "STT_HOST", "PORT", "MANCA_XYZ", "history_runs")


@pytest.fixture
def yaml_cfg(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)   # niente .env dello sviluppatore
    for v in VARS:
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setattr(picobot.config, "CONFIG_FILE", tmp_path / "none.yaml")

    def write(text: str, encoding: str = "utf-8"):
        f = tmp_path / "config.yaml"
        f.write_text(text, encoding=encoding)
        monkeypatch.setattr(picobot.config, "CONFIG_FILE", f)
    return write


def test_missing_file_gives_defaults(yaml_cfg):
    s = Settings()
    assert s.history_runs == 6 and s.region == "it-it"


def test_yaml_value_used(yaml_cfg):
    yaml_cfg("memory:\n  history_runs: 10\nweb:\n  region: us-en\n")
    s = Settings()
    assert s.history_runs == 10 and s.region == "us-en"


def test_env_beats_yaml_and_warns(yaml_cfg, monkeypatch, caplog):
    yaml_cfg("memory:\n  history_runs: 10\n")
    monkeypatch.setenv("HISTORY_RUNS", "3")
    with caplog.at_level(logging.WARNING, logger="picobot.config"):
        assert Settings().history_runs == 3
    assert "HISTORY_RUNS" in caplog.text and "memory.history_runs" in caplog.text


def test_dotenv_beats_yaml(yaml_cfg, tmp_path):
    (tmp_path / ".env").write_text("HISTORY_RUNS=4\n", encoding="utf-8")
    yaml_cfg("memory:\n  history_runs: 10\n")
    assert Settings().history_runs == 4


def test_lowercase_env_beats_yaml_and_warns(yaml_cfg, monkeypatch, caplog):
    yaml_cfg("memory:\n  history_runs: 10\n")
    monkeypatch.setenv("history_runs", "3")
    with caplog.at_level(logging.WARNING, logger="picobot.config"):
        assert Settings().history_runs == 3
    assert "memory.history_runs" in caplog.text


def test_unknown_key(yaml_cfg):
    yaml_cfg("memory:\n  histroy_runs: 10\n")
    with pytest.raises(ConfigError, match=re.escape("memory.histroy_runs")) as e:
        Settings()
    assert "chiave sconosciuta" in str(e.value)


def test_unknown_block(yaml_cfg):
    yaml_cfg("memoria:\n  history_runs: 1\n")
    with pytest.raises(ConfigError, match="memoria") as e:
        Settings()
    assert "blocco sconosciuto" in str(e.value)


def test_key_in_wrong_block(yaml_cfg):
    yaml_cfg("web:\n  history_runs: 1\n")
    with pytest.raises(ConfigError, match=re.escape("web.history_runs")) as e:
        Settings()
    assert "memory" in str(e.value)


def test_env_only_key_rejected(yaml_cfg):
    yaml_cfg("telegram:\n  telegram_bot_token: x\n")
    with pytest.raises(ConfigError, match="TELEGRAM_BOT_TOKEN") as e:
        Settings()
    assert ".env" in str(e.value)


def test_wrong_type(yaml_cfg):
    yaml_cfg("memory:\n  history_runs: tante\n")
    with pytest.raises(ConfigError, match=re.escape("memory.history_runs")):
        Settings()


def test_root_not_mapping(yaml_cfg):
    yaml_cfg("- a\n- b\n")
    with pytest.raises(ConfigError):
        Settings()


def test_invalid_yaml(yaml_cfg):
    yaml_cfg("memory: [\n")
    with pytest.raises(ConfigError, match="YAML non valido"):
        Settings()


def test_var_expanded_from_env_and_dotenv(yaml_cfg, monkeypatch, tmp_path):
    yaml_cfg("voice:\n  stt_url: ${STT_HOST}\n")
    monkeypatch.setenv("STT_HOST", "http://stt:8000")
    assert Settings().stt_url == "http://stt:8000"
    monkeypatch.delenv("STT_HOST")
    (tmp_path / ".env").write_text("STT_HOST=http://stt:9000\n", encoding="utf-8")
    assert Settings().stt_url == "http://stt:9000"


def test_var_missing(yaml_cfg):
    yaml_cfg("voice:\n  stt_url: ${MANCA_XYZ}\n")
    with pytest.raises(ConfigError, match="MANCA_XYZ"):
        Settings()


def test_var_in_int_field(yaml_cfg, monkeypatch):
    yaml_cfg('api:\n  api_port: "${PORT}"\n')
    monkeypatch.setenv("PORT", "9000")
    assert Settings().api_port == 9000


def test_null_block_is_empty(yaml_cfg):
    yaml_cfg("memory:\n  # history_runs: 6\nweb:\n  region: us-en\n")
    assert Settings().region == "us-en"


def test_empty_file(yaml_cfg):
    yaml_cfg("# solo commenti\n")
    assert Settings().history_runs == 6


def test_bom(yaml_cfg):
    yaml_cfg("web:\n  region: us-en\n", encoding="utf-8-sig")
    assert Settings().region == "us-en"


def test_blocks_cover_all_fields():
    in_blocks = [f for fields in BLOCKS.values() for f in fields]
    assert len(in_blocks) == len(set(in_blocks))   # nessun campo in due blocchi
    assert not set(in_blocks) & ENV_ONLY
    assert set(in_blocks) | ENV_ONLY == set(Settings.model_fields)


def test_init_kwargs_beat_yaml(yaml_cfg):
    yaml_cfg("memory:\n  history_runs: 10\n")
    assert Settings(history_runs=2).history_runs == 2


def test_cli_exits_with_message(tmp_path):
    """Un config.yaml sbagliato blocca l'avvio con un messaggio, senza traceback."""
    import os
    import subprocess
    import sys

    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "config.yaml").write_text("memory:\n  histroy_runs: 1\n", encoding="utf-8")
    r = subprocess.run([sys.executable, "-m", "picobot", "skills", "list"], cwd=tmp_path,
                       capture_output=True, text=True, env={**os.environ})
    assert r.returncode != 0
    assert "memory.histroy_runs" in r.stderr and "Traceback" not in r.stderr


ROOT = __import__("pathlib").Path(__file__).resolve().parents[1]


def test_example_matches_defaults(monkeypatch, tmp_path):
    """Copiare config_example.yaml in config.yaml non cambia nulla: chiavi attive con i default del codice."""
    import yaml

    example = ROOT / "config" / "config_example.yaml"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(picobot.config, "CONFIG_FILE", example)
    fields = [f for fs in BLOCKS.values() for f in fs]
    for f in fields:
        monkeypatch.delenv(f.upper(), raising=False)
    s = Settings()
    assert {f: getattr(s, f) for f in fields} == {f: Settings.model_fields[f].default for f in fields}
    data = yaml.safe_load(example.read_text(encoding="utf-8"))
    assert {k for block in data.values() for k in block} == set(fields) - DOCKER_FIXED
    assert all(f"# {k}:" in example.read_text(encoding="utf-8") for k in DOCKER_FIXED)   # commentate, con la nota


DOCKER_FIXED = {"data_dir", "workspace_dir", "skills_dir", "api_host", "node_path"}   # ENV del Dockerfile


def test_env_example_only_env_keys():
    """In .env.example restano attive solo le chiavi riservate a .env; il resto va in config.yaml."""
    active = [l.split("=", 1)[0] for l in (ROOT / ".env.example").read_text(encoding="utf-8").splitlines()
              if re.match(r"^[A-Z_]+=", l)]
    assert active and [k for k in active if k.lower() not in ENV_ONLY] == []


def test_undecodable_file_is_config_error(yaml_cfg, tmp_path):
    """Un config.yaml salvato in ANSI (cp1252) con un accento: errore che nomina il file, non traceback."""
    yaml_cfg("web:\n  region: us-en\n")
    (tmp_path / "config.yaml").write_bytes("# perché\nweb:\n  region: us-en\n".encode("cp1252"))
    with pytest.raises(ConfigError, match="config.yaml"):
        Settings()


def test_duplicate_block_or_key_is_config_error(yaml_cfg):
    yaml_cfg("memory:\n  enable_critic: false\nmemory:\n  history_runs: 9\n")
    with pytest.raises(ConfigError, match="memory"):
        Settings()
    yaml_cfg("memory:\n  history_runs: 9\n  history_runs: 10\n")
    with pytest.raises(ConfigError, match="history_runs"):
        Settings()


def test_example_in_docker_gives_no_warnings(monkeypatch, tmp_path, caplog):
    """Nel container il Dockerfile fissa percorsi, API_HOST e NODE_PATH: copiare l'esempio non deve dare avvisi."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(picobot.config, "CONFIG_FILE", ROOT / "config" / "config_example.yaml")
    monkeypatch.setenv("DATA_DIR", "/app/data")
    monkeypatch.setenv("WORKSPACE_DIR", "/app/workspace")
    monkeypatch.setenv("SKILLS_DIR", "/app/skills")
    monkeypatch.setenv("API_HOST", "0.0.0.0")
    monkeypatch.setenv("NODE_PATH", "/usr/local/lib/node_modules")
    for f in [f for fs in BLOCKS.values() for f in fs]:
        if f.upper() not in ("DATA_DIR", "WORKSPACE_DIR", "SKILLS_DIR", "API_HOST", "NODE_PATH"):
            monkeypatch.delenv(f.upper(), raising=False)
    with caplog.at_level(logging.WARNING, logger="picobot.config"):
        Settings()
    assert "prevale" not in caplog.text


def test_python_tags_rejected(yaml_cfg):
    """Il loader resta sicuro: niente oggetti Python dal file."""
    yaml_cfg("web:\n  region: !!python/object/apply:os.getcwd []\n")
    with pytest.raises(ConfigError, match="YAML non valido"):
        Settings()
