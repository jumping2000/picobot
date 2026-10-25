"""ComplexTeam v0.5 con LLM finto: l'Analyst prepara il contenuto, il Writer produce e consegna."""

import asyncio
import shutil

import fake_llm
import pytest

from picobot.config import Settings
from picobot.context import RunCtx
from picobot.service import PicoBotService


def _svc(tmp_path):
    skills = tmp_path / "skills" / "docx"
    skills.mkdir(parents=True)
    (skills / "SKILL.md").write_text(
        "---\nname: docx\ndescription: Crea documenti Word\n---\n# docx\n"
    )
    return PicoBotService(
        Settings(
            skills_dir=tmp_path / "skills",
            data_dir=tmp_path / "data",
            workspace_dir=tmp_path / "ws",
        )
    )


def _tool_names(b):
    return {t["function"]["name"] for t in b.get("tools") or []}


@pytest.mark.skipif(shutil.which("node") is None, reason="node non installato")
def test_e2e_word_writer_delivers(tmp_path):
    confirmed = []

    async def yes(code, language):
        confirmed.append(language)
        return True

    async def go():
        svc = _svc(tmp_path)
        await svc.start()
        fake_llm.LOG.clear()
        return await svc.ask(
            "crea un documento word",
            user_id="u",
            session_id="e2e",
            ctx=RunCtx("u", "telegram", confirm=yes),
        )

    reply = asyncio.run(go())
    assert confirmed == ["node"]
    assert [f.name for f in reply.files] == ["e2e città.docx"] and reply.files[
        0
    ].path.read_bytes() == b"PK"
    writer = [b for b in fake_llm.LOG if {"run_node", "deliver_file"} <= _tool_names(b)]
    assert writer and "CONTENUTO-ANALYST" in str(
        [m for m in writer[0]["messages"] if m["role"] == "user"]
    )


def test_e2e_text_without_confirmation(tmp_path):
    async def never(code, language):
        raise AssertionError("per un file di testo non serve eseguire codice")

    async def go():
        svc = _svc(tmp_path)
        await svc.start()
        return await svc.ask(
            "scrivi una relazione",
            user_id="u",
            session_id="rel",
            ctx=RunCtx("u", "telegram", confirm=never),
        )

    reply = asyncio.run(go())
    assert [f.name for f in reply.files] == ["relazione.md"] and reply.files[
        0
    ].path.read_text() == "# Relazione"


def test_coder_delivers_script_as_file(
    tmp_path,
):  # revisione finale: caso d'uso del Coder
    async def never(code, language):
        raise AssertionError(
            "salvare e consegnare uno script non richiede di eseguirlo"
        )

    async def go():
        svc = _svc(tmp_path)
        await svc.start()
        return await svc.ask(
            "scrivi un programma per la rata e mandamelo",
            user_id="u",
            session_id="py",
            ctx=RunCtx("u", "telegram", confirm=never),
        )

    reply = asyncio.run(go())
    assert [f.name for f in reply.files] == ["rata.py"] and reply.files[
        0
    ].path.read_text() == "print('rata')"
