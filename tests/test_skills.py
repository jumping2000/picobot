"""Skill estensibili: registry con reload a caldo, catalogo senza esecuzione di script."""
import shutil

import pytest

from picobot.config import Settings
from picobot.skills import CatalogSkills, SkillRegistry


@pytest.fixture
def d(tmp_path):
    p = tmp_path / "skills"
    p.mkdir()
    return p


def mk(root, name, desc, extra=""):
    (root / name).mkdir()
    (root / name / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {desc}\n{extra}---\n# {name}\nIstruzioni di {name}.\n", encoding="utf-8")


def reg_of(d, **kw):
    return SkillRegistry(Settings(skills_dir=d, **kw))


def tool(reg, name):
    return next(t for t in reg.skills.get_tools() if t.name == name)


def test_loads_valid_and_extra_frontmatter(d):
    mk(d, "docx", "Word", extra="argument-hint: x\neffort: low\n")
    assert reg_of(d).names() == ["docx"]


def test_invalid_skipped_not_fatal(d):
    (d / "bad").mkdir()
    (d / "bad" / "SKILL.md").write_text("niente frontmatter")
    (d / "nodesc").mkdir()
    (d / "nodesc" / "SKILL.md").write_text("---\nname: nodesc\n---\n")
    mk(d, "ok", "x")
    assert reg_of(d).names() == ["ok"]


def test_partial_and_bad_names_ignored(d):          # Review Focus 2
    mk(d, ".tmp-x", "x")
    mk(d, "_x", "x")
    mk(d, "Maiuscola", "x")
    (d / "altro").mkdir()                            # nome cartella != name nel frontmatter
    (d / "altro" / "SKILL.md").write_text("---\nname: diverso\ndescription: x\n---\n")
    assert reg_of(d).names() == []


def test_missing_or_empty_dir_degrades(tmp_path):   # Review Focus 5
    assert SkillRegistry(Settings(skills_dir=tmp_path / "nope")).names() == []
    assert SkillRegistry(Settings(skills_dir=tmp_path / "nope")).skills is not None
    assert SkillRegistry(Settings(enable_skills=False)).skills is None
    assert SkillRegistry(Settings(enable_skills=False)).names() == []


def test_refresh_detects_add_remove(d):
    reg = reg_of(d)
    assert reg.refresh() is False
    mk(d, "pptx", "P")
    assert reg.refresh() is True and reg.names() == ["pptx"]
    shutil.rmtree(d / "pptx")
    assert reg.refresh() is True and reg.names() == []


def test_refresh_detects_edit(d):
    mk(d, "docx", "vecchia")
    reg = reg_of(d)
    import os, time
    f = d / "docx" / "SKILL.md"
    f.write_text("---\nname: docx\ndescription: nuova\n---\n", encoding="utf-8")
    later = time.time() + 5
    os.utime(f, (later, later))
    assert reg.refresh() is True and reg.info()[0].description == "nuova"


def test_tools_no_script(d):
    mk(d, "docx", "Word")
    assert {t.name for t in reg_of(d).skills.get_tools()} == {"get_skill_instructions", "get_skill_reference", "list_skills"}


def test_list_skills_rank_and_cap(d):
    for i in range(60):
        mk(d, f"s{i:02d}", "descrizione lunga " * 20)
    mk(d, "docx", "Crea documenti Word")
    reg = reg_of(d, skills_list_max=50)
    ls = tool(reg, "list_skills").entrypoint
    lines = ls("").splitlines()
    assert len(lines) == 50 and all(len(l.split(": ", 1)[1]) <= 120 for l in lines)
    assert ls("documento word").splitlines()[0].startswith("- docx:")


def test_reload_failure_keeps_previous(d, monkeypatch):
    mk(d, "a", "x")
    reg = reg_of(d)
    def boom():
        raise RuntimeError("rotto")
    monkeypatch.setattr(reg.skills, "reload", boom)
    mk(d, "b", "y")
    assert reg.refresh() is False and reg.names() == ["a"]


def test_snippet_fixed_length(tmp_path):
    def with_n(n):
        root = tmp_path / f"r{n}"
        root.mkdir()
        for i in range(n):
            mk(root, f"s{i}", f"descrizione {i}")
        return reg_of(root).skills.get_system_prompt_snippet()
    one, thirty, zero = with_n(1), with_n(30), with_n(0)
    assert one == thirty != "" and "list_skills" in one and zero == ""


def test_info(d):
    mk(d, "docx", "Word")
    (d / "docx" / "scripts").mkdir()
    (d / "docx" / "scripts" / "a.py").write_text("print(1)")
    info = reg_of(d).info()[0]
    assert (info.name, info.description, info.files, info.has_scripts) == ("docx", "Word", 2, True)
    assert isinstance(reg_of(d).skills, CatalogSkills)
