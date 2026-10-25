"""deliver_file: consegna controllata dei file prodotti dagli agenti."""

import asyncio
import os
import re
import time

import pytest

from picobot.config import Settings
from picobot.context import OutputFile, RunCtx, reset_ctx, set_ctx
from picobot.tools.files import (
    find_output,
    make_file_tools,
    make_text_tools,
    purge_outbox,
    store_outputs,
)


@pytest.fixture
def env(tmp_path):
    s = Settings(
        workspace_dir=tmp_path / "ws", data_dir=tmp_path / "data", max_output_mb=1
    )
    (s.workspace_dir / "outputs").mkdir(parents=True)
    (s.workspace_dir / "scripts").mkdir()
    ctx = RunCtx("u", "api", pre_approved=True)
    deliver = make_file_tools(s)[0]

    def run(path, c=ctx):
        async def go():
            tok = set_ctx(c)
            try:
                return await deliver(path)
            finally:
                reset_ctx(tok)

        return asyncio.run(go())

    return s, ctx, run


def test_deliver_ok_and_dedup(env):  # Review Focus 4: spazio e accento nel nome
    s, ctx, run = env
    (s.outputs_dir / "Relazione città.docx").write_bytes(b"hello")
    assert "Consegnato" in run("outputs/Relazione città.docx")
    run("outputs/Relazione città.docx")
    assert [f.name for f in ctx.outputs] == ["Relazione città.docx"] and ctx.outputs[
        0
    ].size == 5


@pytest.mark.parametrize(
    "p",
    [
        "../x.docx",
        "/etc/passwd",
        "outputs/../scripts/a.docx",
        "outputs/a.exe",
        "scripts/a.docx",
    ],
)
def test_deliver_refused(env, p):
    s, ctx, run = env
    (s.outputs_dir / "a.exe").write_bytes(b"x")
    (s.workspace_dir / "scripts" / "a.docx").write_bytes(b"x")
    assert "rifiutato" in run(p).lower() and ctx.outputs == []


def test_symlink_refused(env, tmp_path):
    s, ctx, run = env
    outside = tmp_path / "secret.docx"
    outside.write_bytes(b"s")
    try:
        os.symlink(outside, s.outputs_dir / "link.docx")
    except OSError:  # Windows senza Developer Mode
        pytest.skip("symlink non consentiti")
    assert "rifiutato" in run("outputs/link.docx").lower() and ctx.outputs == []


def test_size_and_count(env):
    s, ctx, run = env
    (s.outputs_dir / "big.docx").write_bytes(b"x" * 2 * 1024 * 1024)
    assert "rifiutato" in run("outputs/big.docx").lower()
    for i in range(6):
        (s.outputs_dir / f"f{i}.docx").write_bytes(b"x")
    res = [run(f"outputs/f{i}.docx") for i in range(6)]
    assert len(ctx.outputs) == 5 and "rifiutato" in res[5].lower()


def test_no_ctx(env):
    s, ctx, run = env
    (s.outputs_dir / "a.docx").write_bytes(b"x")
    assert "rifiutato" in run("outputs/a.docx", c=None).lower()


# ---------------- outbox API ----------------
def _outbox(tmp_path, name="Relazione città.docx", data=b"x"):
    s = Settings(workspace_dir=tmp_path / "ws", data_dir=tmp_path / "data")
    src = tmp_path / name
    src.write_bytes(data)
    return s, OutputFile(src, name, len(data))


def test_store_find_other_user(tmp_path):
    s, of = _outbox(tmp_path)
    meta = store_outputs(s, "alice", [of])[0]
    assert (
        re.fullmatch(r"[0-9a-f]{32}", meta["id"])
        and meta["name"] == "Relazione città.docx"
        and meta["size"] == 1
    )
    assert find_output(s, "alice", meta["id"]).read_bytes() == b"x"
    assert find_output(s, "bob", meta["id"]) is None
    for bad in ("../x", "..", "", "0" * 31, "G" * 32, "0" * 32):
        assert find_output(s, "alice", bad) is None


def test_hostile_user_id_stays_inside_outbox(tmp_path):
    s, of = _outbox(tmp_path)
    meta = store_outputs(s, "../../evil", [of])[0]
    stored = find_output(s, "../../evil", meta["id"])
    assert stored.resolve().is_relative_to(s.outbox_dir.resolve())
    assert (
        find_output(s, "a/b", meta["id"]) is None
        and find_output(s, "a_b", meta["id"]) is None
    )


def test_purge_ttl(tmp_path):
    s, of = _outbox(tmp_path)
    old = store_outputs(s, "alice", [of])[0]
    new = store_outputs(s, "alice", [of])[0]
    old_dir = find_output(s, "alice", old["id"]).parent
    past = time.time() - 25 * 3600
    os.utime(old_dir, (past, past))
    assert purge_outbox(s) == 1
    assert (
        find_output(s, "alice", old["id"]) is None
        and find_output(s, "alice", new["id"]) is not None
    )


# ---------------- save_text_file (v0.5) ----------------
def run_save(s, name, content):
    return asyncio.run(make_text_tools(s)[0](name, content))


def test_save_text_file_ok_and_deliverable(env):  # Review Focus 5
    s, ctx, run = env
    assert (
        run_save(s, "relazione città.md", "# Titolo")
        == "Salvato: outputs/relazione città.md"
    )
    assert (s.outputs_dir / "relazione città.md").read_text(
        encoding="utf-8"
    ) == "# Titolo"
    assert "Consegnato" in run("outputs/relazione città.md")


@pytest.mark.parametrize(
    "name",
    ["../x.md", "a/b.md", "a\\b.md", "x.exe", "x.sh", "x" * 121 + ".md", "", ".md"],
)
def test_save_text_file_refused(env, name):
    s, ctx, run = env
    assert run_save(s, name, "x").startswith("Rifiutato")
    assert not [
        p for p in s.workspace_dir.parent.rglob("*") if p.is_file()
    ]  # nulla scritto da nessuna parte


def test_save_text_file_size(env):  # max_output_mb=1
    s, ctx, run = env
    assert run_save(s, "big.txt", "x" * (2 * 1024 * 1024)).startswith("Rifiutato")
    assert not (s.outputs_dir / "big.txt").exists()


def test_save_text_file_respects_output_extensions(tmp_path):
    s = Settings(workspace_dir=tmp_path / "ws", output_extensions="docx,md")
    assert run_save(s, "a.md", "x").startswith("Salvato") and run_save(
        s, "a.txt", "x"
    ).startswith("Rifiutato")


@pytest.mark.parametrize("name", ["pagina.html", "dati.json", "script.py"])
def test_save_text_file_default_extensions(
    tmp_path, name
):  # revisione finale: promessi dallo spec al Writer/Coder
    s = Settings(workspace_dir=tmp_path / "ws")
    assert run_save(s, name, "x") == f"Salvato: outputs/{name}"
