"""Controlli statici su deps/, Dockerfile, compose ed esempi di configurazione (nessun Docker richiesto)."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def read(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


def lines(rel):
    return [l.strip() for l in read(rel).splitlines() if l.strip() and not l.strip().startswith("#")]


def test_deps_seed():
    npm = lines("deps/npm.txt")
    assert len(npm) == 2 and all(re.fullmatch(r"(docx|pptxgenjs)@\d+\.\d+\.\d+", l) for l in npm)
    pip = lines("deps/pip.txt")
    assert pip and all(re.fullmatch(r"openpyxl==\d+\.\d+\.\d+", l) for l in pip)
    assert lines("deps/apt.txt") == []
    assert read("deps/setup.sh").startswith("#!")
    assert "# skill: docx" in read("deps/npm.txt") and "# skill: xlsx" in read("deps/pip.txt")


def test_dockerfile_order_and_hardening():
    d = read("Dockerfile")
    order = ["COPY deps/", "/tmp/deps/apt.txt", "-r /tmp/deps/pip.txt", "/tmp/deps/npm.txt", "/tmp/deps/setup.sh", "COPY src/"]
    idx = [d.index(m) for m in order]
    assert idx == sorted(idx), dict(zip(order, idx))
    assert "/uvx" in d and "NODE_PATH" in d and "libreoffice" not in d.lower()
    assert "chown -R picobot /app" not in d and "chown picobot /app/data /app/workspace" in d
    assert d.index("chown picobot /app/data /app/workspace") < d.index("USER picobot")


def test_compose_env_ignores():
    compose = read("docker-compose.yaml")
    assert "./skills:/app/skills:ro" in compose and "./config:/app/config:ro" in compose
    assert "skills/" in read(".gitignore") and "skills" in read(".dockerignore").split()
    env = read(".env.example")
    for k in ("ENABLE_SKILLS", "SKILLS_DIR", "CODE_NODE_MEM_MB", "CODE_MAX_RUNS", "MAX_OUTPUT_MB",
              "MAX_OUTPUT_FILES", "OUTPUT_EXTENSIONS", "OUTBOX_TTL_H"):
        assert k in env, k


def _run_step(marker):
    """Testo del RUN del Dockerfile che contiene marker, con le continuazioni di riga unite."""
    text = read("Dockerfile").replace("\\\n", " ")
    line = next(l for l in text.splitlines() if l.startswith("RUN ") and marker in l)
    return line[4:]


def test_npm_step_fails_if_node_path_differs(tmp_path):
    import os
    import subprocess
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    npm = bin_ / "npm"
    deps = tmp_path / "deps"
    deps.mkdir()
    (deps / "npm.txt").write_text("docx@9.9.0\n")
    script = _run_step("/tmp/deps/npm.txt").replace("/tmp/deps", str(deps))
    env = {"PATH": f"{bin_}:{os.environ['PATH']}", "NODE_PATH": "/usr/local/lib/node_modules"}
    for root, expected_ok in (("/somewhere/else", False), ("/usr/local/lib/node_modules", True)):
        npm.write_text(f'#!/bin/sh\nif [ "$1" = root ]; then echo {root}; fi\nexit 0\n')
        npm.chmod(0o755)
        r = subprocess.run(["sh", "-c", script], env=env, capture_output=True, text=True)
        assert (r.returncode == 0) is expected_ok, (root, r.returncode, r.stderr)
