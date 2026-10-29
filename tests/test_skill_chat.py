"""Installazione e rimozione delle skill da chat: servizio (fetched_skill, install_skill) e flussi condivisi."""
import asyncio
import errno
import io
import logging
import zipfile

import pytest

from picobot import skills_cli, web
from picobot.channels.common import SKILL_DIR_READONLY, add_skill_flow, remove_skill_flow
from picobot.config import Settings
from picobot.documents import DocumentError
from picobot.service import PicoBotService
from picobot.skills_cli import SkillInstallError


def skill_md(name, desc="Crea documenti Word"):
    return f"---\nname: {name}\ndescription: {desc}\n---\n# {name}\n"


def zipbytes(name, desc="Crea documenti Word"):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(f"{name}/SKILL.md", skill_md(name, desc))
        zf.writestr(f"{name}/requirements.txt", "openpyxl==3.1.5\n")
    return buf.getvalue()


@pytest.fixture
def svc(tmp_path):
    return PicoBotService(Settings(skills_dir=tmp_path / "skills"))


@pytest.fixture
def net(monkeypatch):
    """fetch_bytes / check_public_url finti: registrano le chiamate, nessuna rete."""
    state = {"zip": zipbytes("docx"), "events": [], "check_error": None}

    async def fake_fetch_bytes(url, *, max_bytes, transport=None):
        state["events"].append(("bytes", url, max_bytes))
        return state["zip"]

    async def fake_check(url):
        state["events"].append(("check", url))
        if state["check_error"]:
            raise DocumentError(state["check_error"])

    monkeypatch.setattr(web, "fetch_bytes", fake_fetch_bytes)
    monkeypatch.setattr(web, "check_public_url", fake_check)
    return state


@pytest.fixture
def git(monkeypatch, net):
    """_fetch finto per gli URL: crea una skill valida in work/repo; i percorsi locali vanno all'originale."""
    orig = skills_cli._fetch
    works = []

    def fake_fetch(source, work, *, strict_git=False):
        if "://" in source:
            net["events"].append(("git", source, strict_git))
            works.append(work)
            repo = work / "repo"
            repo.mkdir()
            (repo / "SKILL.md").write_text(skill_md("repo-skill", "Da git"), encoding="utf-8")
            return repo
        return orig(source, work, strict_git=strict_git)

    monkeypatch.setattr(skills_cli, "_fetch", fake_fetch)
    return works


def kinds(net, kind):
    return [e for e in net["events"] if e[0] == kind]


def run_add(svc, source, *, allow_local=False, answer=True, prompts=None, user="alice", channel="telegram"):
    async def ask(q):
        if prompts is not None:
            prompts.append(q)
        return answer
    return asyncio.run(add_skill_flow(svc, source, allow_local=allow_local, ask=ask, user=user, channel=channel))


def test_admin_ids(monkeypatch):
    monkeypatch.delenv("ADMIN_USER_IDS", raising=False)
    assert Settings(admin_user_ids="1, 2").admin_ids == {1, 2}
    assert Settings(_env_file=None).admin_ids == set()


def test_add_from_zip_url(svc, net):
    text = run_add(svc, "https://h/s.zip")
    assert "docx" in text and "Crea documenti Word" in text and "openpyxl==3.1.5" in text
    assert "picobot skills deps --write" in text
    assert (svc.s.skills_dir / "docx" / "SKILL.md").is_file()
    assert kinds(net, "bytes") == [("bytes", "https://h/s.zip", skills_cli.MAX_SKILL_BYTES)]


def test_zip_url_with_query_and_case(svc, net, git):  # Review Focus 1, 2
    text = run_add(svc, "HTTPS://h/S.ZIP?raw=1")
    assert "docx" in text
    assert [e[1] for e in kinds(net, "bytes")] == ["HTTPS://h/S.ZIP?raw=1"]
    assert kinds(net, "git") == [] and kinds(net, "check") == []


def test_git_url_uses_strict_clone(svc, net, git):
    text = run_add(svc, "https://h/r.git")
    assert "repo-skill" in text
    assert net["events"] == [("check", "https://h/r.git"), ("git", "https://h/r.git", True)]
    assert (svc.s.skills_dir / "repo-skill" / "SKILL.md").is_file()
    assert git and not git[0].exists()   # cartella temporanea cancellata


def test_git_url_scheme_lowercased(svc, net, git):  # R3: _fetch riconosce solo "https://" minuscolo
    run_add(svc, "HTTPS://h/r")
    assert kinds(net, "git") == [("git", "https://h/r", True)]


@pytest.mark.parametrize("source", ["http://h/s.zip", "file:///etc", "git@github.com:o/r.git", "ssh://h/r",
                                    "/tmp/x"])
def test_rejected_sources(svc, net, git, source):
    text = run_add(svc, source)
    assert text and "Installazione fallita" not in text
    assert net["events"] == []   # ne' download, ne' controllo host, ne' git
    assert not svc.s.skills_dir.exists() or not any(svc.s.skills_dir.iterdir())


@pytest.mark.parametrize("source", ["http://h/s.zip", "file:///etc", "git@github.com:o/r.git", "ssh://h/r"])
def test_rejected_sources_even_from_cli(svc, net, git, source):
    assert "Solo link https://" in run_add(svc, source, allow_local=True)
    assert net["events"] == []
    assert not svc.s.skills_dir.exists() or not any(svc.s.skills_dir.iterdir())


def test_local_path_messages(svc, net, git):
    assert "allega uno .zip" in run_add(svc, "/tmp/x", allow_local=False)
    assert "sorgente non trovata" in run_add(svc, "/tmp/x", allow_local=True)


def test_private_host_refused(svc, net, git):
    net["check_error"] = "Indirizzo non consentito (rete locale o privata)."
    text = run_add(svc, "https://192.168.1.10/r.git")
    assert "Indirizzo non consentito" in text
    assert kinds(net, "git") == []
    assert not svc.s.skills_dir.exists() or not any(svc.s.skills_dir.iterdir())


def install_old(svc, net):
    run_add(svc, "https://h/s.zip")
    net["events"].clear()
    net["zip"] = zipbytes("docx", "Versione nuova")


def test_replace_no_keeps_old(svc, net):
    install_old(svc, net)
    prompts = []
    text = run_add(svc, "https://h/s.zip", answer=False, prompts=prompts)
    assert text == "Skill 'docx' non sostituita."
    assert len(prompts) == 1 and "docx" in prompts[0]
    assert "Crea documenti Word" in (svc.s.skills_dir / "docx" / "SKILL.md").read_text(encoding="utf-8")
    assert len(kinds(net, "bytes")) == 1


def test_replace_yes_replaces(svc, net):
    install_old(svc, net)
    prompts = []
    text = run_add(svc, "https://h/s.zip", answer=True, prompts=prompts)
    assert "Versione nuova" in text
    assert len(prompts) == 1 and "docx" in prompts[0]
    assert "Versione nuova" in (svc.s.skills_dir / "docx" / "SKILL.md").read_text(encoding="utf-8")
    assert len(kinds(net, "bytes")) == 1   # lo zip non viene riscaricato


@pytest.mark.parametrize("exc", [
    PermissionError(errno.EACCES, "x"),
    SkillInstallError("installazione fallita: ro"),
])
def test_readonly_dir_message(svc, net, monkeypatch, exc):
    if isinstance(exc, SkillInstallError):
        exc.__cause__ = OSError(errno.EROFS, "ro")
    seen = []

    async def boom(path, *, force):
        seen.append(path)
        raise exc

    monkeypatch.setattr(svc, "install_skill", boom)
    assert run_add(svc, "https://h/s.zip") == SKILL_DIR_READONLY
    assert seen and not seen[0].exists()   # lo zip scaricato e' stato cancellato


def test_unexpected_error(svc, net, monkeypatch, caplog):
    async def boom(path, *, force):
        raise RuntimeError("guasto interno")

    monkeypatch.setattr(svc, "install_skill", boom)
    with caplog.at_level(logging.INFO):
        assert run_add(svc, "https://h/s.zip") == "Installazione fallita."
    assert "Traceback" in caplog.text and "guasto interno" in caplog.text


def test_install_logged(svc, net, caplog):
    with caplog.at_level(logging.INFO):
        run_add(svc, "https://h/s.zip", user="alice", channel="telegram")
        run_add(svc, "http://h/s.zip", user="bob", channel="cli", allow_local=True)
    lines = [r.getMessage() for r in caplog.records if r.getMessage().startswith("skill_add")]
    assert len(lines) == 2
    assert "utente=alice" in lines[0] and "canale=telegram" in lines[0] and "sorgente=https://h/s.zip" in lines[0]
    assert "esito=installata" in lines[0]
    assert "utente=bob" in lines[1] and "canale=cli" in lines[1] and "sorgente=http://h/s.zip" in lines[1]
    assert "esito=errore" in lines[1] and "Solo link https://" in lines[1]


def test_remove_flow(svc, net, tmp_path, caplog):  # Review Focus 5
    run_add(svc, "https://h/s.zip")
    outside = tmp_path / "data"
    outside.mkdir()
    (outside / "keep.txt").write_text("x")
    with caplog.at_level(logging.INFO):
        assert asyncio.run(remove_skill_flow(svc, "docx", user="alice", channel="telegram")) == "Rimossa: docx"
        assert not (svc.s.skills_dir / "docx").exists()
        bad = asyncio.run(remove_skill_flow(svc, "../data", user="alice", channel="telegram"))
        missing = asyncio.run(remove_skill_flow(svc, "nonce", user="alice", channel="telegram"))
    assert "non valido" in bad and "non installata" in missing
    assert (outside / "keep.txt").is_file()
    lines = [r.getMessage() for r in caplog.records if r.getMessage().startswith("skill_remove")]
    assert len(lines) == 3 and "utente=alice" in lines[0] and "canale=telegram" in lines[0]
    assert "esito=rimossa" in lines[0] and "esito=errore" in lines[1]
