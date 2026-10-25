"""Sandbox: run_node, tetto esecuzioni, nomi script unici, gate umano, generazione reale di file Office."""

import asyncio
import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest

from picobot.config import Settings
from picobot.context import RunCtx, reset_ctx, set_ctx
from picobot.tools.sandbox import make_code_tools, make_node_tools

needs_node = pytest.mark.skipif(
    shutil.which("node") is None, reason="node non installato"
)


def pre() -> RunCtx:
    return RunCtx("u", "api", pre_approved=True)


def run_in_ctx(ctx, fn, *args):
    async def go():
        tok = set_ctx(ctx)
        try:
            return await fn(*args)
        finally:
            reset_ctx(tok)

    return asyncio.run(go())


async def gather_in_ctxs(fn, codes):
    async def one(code):
        tok = set_ctx(pre())  # un contesto per richiesta, come in produzione
        try:
            return await fn(code)
        finally:
            reset_ctx(tok)

    return await asyncio.gather(*(one(c) for c in codes))


def tool_of(s, kind):
    return make_node_tools(s)[0] if kind == "node" else make_code_tools(s)[1]


def npm_root_g():
    if not (shutil.which("node") and shutil.which("npm")):
        pytest.skip("node/npm non installati")
    root = subprocess.run(
        [shutil.which("npm"), "root", "-g"], capture_output=True, text=True  # su Windows e' npm.cmd
    ).stdout.strip()
    if not (Path(root, "docx").is_dir() and Path(root, "pptxgenjs").is_dir()):
        pytest.skip("docx/pptxgenjs non installati globalmente")
    return root


@needs_node
def test_run_node_after_confirm():
    seen = []

    async def yes(code, lang):
        seen.append((code, lang))
        return True

    out = run_in_ctx(
        RunCtx("u", "telegram", confirm=yes),
        make_node_tools(Settings())[0],
        "console.log(6*7)",
    )
    assert "exit=0" in out and "42" in out and seen == [("console.log(6*7)", "node")]


@needs_node
def test_node_env_clean_and_node_path():
    s = Settings(node_path="/x/modules")
    out = run_in_ctx(
        pre(),
        make_node_tools(s)[0],
        "console.log(process.env.OPENROUTER_API_KEY, process.env.NODE_PATH)",
    )
    assert "undefined /x/modules" in out


def test_sandbox_python_can_import_asyncio():  # su Windows serve SYSTEMROOT nell'env ripulito
    out = run_in_ctx(pre(), make_code_tools(Settings())[1], "import asyncio; print('ok')")
    assert out.splitlines()[:2] == ["exit=0", "ok"], out


def test_run_cap_counts_only_approved():
    s = Settings(code_max_runs=2)
    ctx, rp = pre(), make_code_tools(s)[1]
    outs = [run_in_ctx(ctx, rp, "print(1)") for _ in range(3)]
    assert (
        "exit=0" in outs[0]
        and "exit=0" in outs[1]
        and "limite raggiunto" in outs[2]
        and ctx.runs == 2
    )

    async def no(code, lang):
        return False

    no_ctx = RunCtx("u", "telegram", confirm=no)
    run_in_ctx(no_ctx, rp, "print(1)")
    assert no_ctx.runs == 0


def test_parallel_runs_isolated(tmp_path):  # Review Focus 3
    s = Settings(workspace_dir=tmp_path / "ws")
    rp = make_code_tools(s)[1]
    outs = asyncio.run(gather_in_ctxs(rp, ["print('A')", "print('B')", "print('C')"]))
    assert [o.splitlines()[1] for o in outs] == ["A", "B", "C"]
    assert not list((s.workspace_dir / "scripts").glob("_run*"))


def test_node_missing_path(monkeypatch):  # Review Focus 5
    monkeypatch.setenv("PATH", "/nonexistent")
    out = run_in_ctx(pre(), make_node_tools(Settings())[0], "1")
    assert "node" in out.lower() and "non" in out.lower()


@pytest.mark.parametrize("ctx", [None, RunCtx("u", "schedule"), RunCtx("u", "api")])
def test_run_node_blocked_without_human(ctx):
    assert "NON consentita" in run_in_ctx(ctx, make_node_tools(Settings())[0], "1")


def test_dirs_created_at_tool_build(tmp_path):
    s = Settings(workspace_dir=tmp_path / "w")
    make_node_tools(s)
    make_code_tools(s)
    assert (s.workspace_dir / "outputs").is_dir() and (
        s.workspace_dir / "scripts"
    ).is_dir()


def test_real_office_generation(
    tmp_path,
):  # salta se mancano node, docx/pptxgenjs o openpyxl
    pytest.importorskip("openpyxl")
    s = Settings(workspace_dir=tmp_path / "w", node_path=npm_root_g())
    docx = (
        "const {Document,Packer,Paragraph}=require('docx');const fs=require('fs');"
        "Packer.toBuffer(new Document({sections:[{children:[new Paragraph('x')]}]}))"
        ".then(b=>fs.writeFileSync('outputs/a.docx',b))"
    )
    pptx = (
        "const P=require('pptxgenjs');const p=new P();p.addSlide().addText('x',{x:1,y:1});"
        "p.writeFile({fileName:'outputs/a.pptx'})"
    )
    xlsx = "import openpyxl; wb=openpyxl.Workbook(); wb.active['A1']='=1+1'; wb.save('outputs/a.xlsx')"
    for code, name, kind in [
        (docx, "a.docx", "node"),
        (pptx, "a.pptx", "node"),
        (xlsx, "a.xlsx", "python"),
    ]:
        assert "exit=0" in run_in_ctx(pre(), tool_of(s, kind), code), name
        z = zipfile.ZipFile(s.workspace_dir / "outputs" / name)
        assert z.testzip() is None and "[Content_Types].xml" in z.namelist()
