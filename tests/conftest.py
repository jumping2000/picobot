import os, sys, tempfile
import pytest
sys.path.insert(0, os.path.dirname(__file__))
import fake_llm

_tmp = tempfile.mkdtemp()
os.environ.update(OPENROUTER_API_KEY="fake", OPENROUTER_BASE_URL="http://127.0.0.1:8765/v1",
                  DATA_DIR=f"{_tmp}/data", WORKSPACE_DIR=f"{_tmp}/ws", MCP_CONFIG_PATH=f"{_tmp}/none.json",
                  API_TOKENS="tok-a:alice,tok-b:bob", TELEGRAM_ALLOWED_USER_IDS="1,2")
fake_llm.start()


@pytest.fixture(autouse=True)
def clear_log():
    fake_llm.LOG.clear()
    yield
