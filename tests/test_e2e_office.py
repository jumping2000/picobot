"""Criterio di successo (a), con LLM finto: router -> ComplexTeam -> Analyst -> run_node (conferma) -> deliver_file -> file nella risposta."""
import asyncio
import shutil

import pytest

import fake_llm
from picobot.config import Settings
from picobot.context import RunCtx
from picobot.service import PicoBotService


@pytest.mark.skipif(shutil.which("node") is None, reason="node non installato")
def test_document_request_returns_file(tmp_path):
    skills = tmp_path / "skills" / "docx"
    skills.mkdir(parents=True)
    (skills / "SKILL.md").write_text("---\nname: docx\ndescription: Crea documenti Word\n---\n# docx\n")
    s = Settings(skills_dir=tmp_path / "skills", data_dir=tmp_path / "data", workspace_dir=tmp_path / "ws")
    confirmed = []

    async def yes(code, language):
        confirmed.append(language)
        return True

    async def go():
        svc = PicoBotService(s)
        await svc.start()
        fake_llm.LOG.clear()
        return await svc.ask("crea un documento word", user_id="u", session_id="e2e",
                             ctx=RunCtx("u", "telegram", confirm=yes))
    reply = asyncio.run(go())
    assert confirmed == ["node"]
    assert [f.name for f in reply.files] == ["e2e città.docx"] and reply.files[0].path.read_bytes() == b"PK"
    calls = [t["function"]["name"] for b in fake_llm.LOG for m in b["messages"] if m["role"] == "assistant"
             for t in (m.get("tool_calls") or [])]
    assert "run_node" in calls and "deliver_file" in calls
