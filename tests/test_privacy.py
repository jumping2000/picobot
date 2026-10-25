"""Revisione finale: nessuna telemetria verso Agno, salvo scelta esplicita dell'utente."""

import os
import subprocess
import sys


def _probe(env_extra):
    code = ("import picobot, os; from agno.agent._init import set_telemetry; from picobot.agents import build_web;"
            "from picobot.config import Settings; a = build_web(Settings(openrouter_api_key='k'));"
            "set_telemetry(a); print(os.environ.get('AGNO_TELEMETRY'), a.telemetry)")
    env = {k: v for k, v in os.environ.items() if k != "AGNO_TELEMETRY"} | env_extra
    return subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env).stdout.strip()


def test_telemetry_off_by_default():
    assert _probe({}) == "false False"


def test_telemetry_explicit_choice_respected():
    assert _probe({"AGNO_TELEMETRY": "true"}) == "true True"
