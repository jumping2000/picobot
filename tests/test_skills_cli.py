"""CLI admin `picobot skills`: installazione atomica e sicura da cartella, zip o git."""
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from picobot import skills_cli
from picobot.config import Settings
from picobot.skills_cli import SkillInstallError, install, main_skills, remove, validate_dir

GOOD = "---\nname: docx\ndescription: Crea documenti Word\n---\n# docx\n"


@pytest.fixture
def d(tmp_path):
    p = tmp_path / "installed"
    p.mkdir()
    return p


def good_src(tmp_path, folder="docx-main", md=GOOD, scripts=True):
    src = tmp_path / "src" / folder
    src.mkdir(parents=True)
    (src / "SKILL.md").write_text(md, encoding="utf-8")
    if scripts:
        (src / "scripts").mkdir()
        (src / "scripts" / "a.py").write_text("print(1)")
    return src


def test_install_dir_renames_to_frontmatter_name(tmp_path, d):
    info = install(str(good_src(tmp_path)), d)
    assert info.name == "docx" and (d / "docx" / "SKILL.md").exists() and info.has_scripts and info.files == 2
    assert [p.name for p in d.iterdir()] == ["docx"]


def test_duplicate_needs_force(tmp_path, d):
    src = good_src(tmp_path)
    install(str(src), d)
    with pytest.raises(SkillInstallError):
        install(str(src), d)
    (src / "extra.md").write_text("x")
    assert install(str(src), d, force=True).files == 3
    assert sorted(p.name for p in d.iterdir()) == ["docx"]          # nessun .old-* o .tmp-* residuo


def _no_md(tmp):
    p = tmp / "s"; p.mkdir(); (p / "README.md").write_text("x"); return p
def _no_desc(tmp): return good_src(tmp, md="---\nname: docx\n---\n")
def _traversal(tmp): return good_src(tmp, md="---\nname: ../x\ndescription: d\n---\n")
def _upper(tmp): return good_src(tmp, md="---\nname: Docx\ndescription: d\n---\n")
def _symlink(tmp):
    p = good_src(tmp); os.symlink("/etc/passwd", p / "passwd"); return p
FIXTURES = {"no_skill_md": _no_md, "no_description": _no_desc, "name_traversal": _traversal,
            "name_upper": _upper, "symlink_inside": _symlink}


@pytest.mark.parametrize("bad", sorted(FIXTURES))
def test_invalid_rejected_no_residue(bad, tmp_path, d):     # Review Focus 1/2
    with pytest.raises(SkillInstallError):
        install(str(FIXTURES[bad](tmp_path)), d)
    assert list(d.iterdir()) == []


def test_size_limit(monkeypatch, tmp_path, d):
    monkeypatch.setattr(skills_cli, "MAX_SKILL_BYTES", 10)
    with pytest.raises(SkillInstallError):
        install(str(good_src(tmp_path)), d)
    assert list(d.iterdir()) == []


def make_zip(tmp_path, root_folder=True, extra=None):
    z = tmp_path / "skill.zip"
    prefix = "docx-main/" if root_folder else ""
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr(prefix + "SKILL.md", GOOD)
        zf.writestr(prefix + "scripts/a.py", "print(1)")
        if extra:
            zf.writestr(zipfile.ZipInfo(extra), "evil")
    return z


@pytest.mark.parametrize("root_folder", [True, False])
def test_zip_layouts(tmp_path, d, root_folder):
    info = install(str(make_zip(tmp_path, root_folder=root_folder)), d)
    assert info.name == "docx" and (d / "docx" / "scripts" / "a.py").exists()


@pytest.mark.parametrize("member", ["../evil.txt", "/abs/evil.txt", "docx-main/../../evil.txt"])
def test_zip_hostile_rejected(member, tmp_path, d):          # Review Focus 1
    with pytest.raises(SkillInstallError):
        install(str(make_zip(tmp_path, extra=member)), d)
    assert list(d.iterdir()) == [] and not (tmp_path / "evil.txt").exists()


def test_git_source(tmp_path, d):
    if shutil.which("git") is None:
        pytest.skip("git non installato")
    repo = good_src(tmp_path, folder="repo")
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@t"}
    for cmd in (["git", "init", "-q"], ["git", "add", "-A"], ["git", "commit", "-qm", "x"]):
        subprocess.run(cmd, cwd=repo, check=True, env=env)
    info = install(f"file://{repo}", d)
    assert info.name == "docx" and not (d / "docx" / ".git").exists()


def test_remove(tmp_path, d):
    install(str(good_src(tmp_path)), d)
    remove("docx", d)
    assert not (d / "docx").exists()
    with pytest.raises(SkillInstallError):
        remove("docx", d)
    with pytest.raises(SkillInstallError):
        remove("../installed", d)


def test_validate_dir(tmp_path, d):
    install(str(good_src(tmp_path)), d)
    (d / "rotta").mkdir()
    (d / "rotta" / "SKILL.md").write_text("niente")
    problems = validate_dir(d)
    assert [p[0] for p in problems] == ["rotta"]


def test_cli_dispatch(capsys, tmp_path, d):
    s = Settings(skills_dir=d)
    assert main_skills(["add", str(good_src(tmp_path))], s) == 0
    out = capsys.readouterr().out
    assert "docx" in out and "Crea documenti Word" in out and "conferma" in out      # avviso scripts/
    assert main_skills(["list"], s) == 0 and "docx" in capsys.readouterr().out
    assert main_skills(["validate"], s) == 0
    assert main_skills(["add", "/nonexistent"], s) == 1
    assert main_skills(["remove", "docx"], s) == 0 and not (d / "docx").exists()


def test_main_skills_needs_no_api_key(tmp_path, d):
    env = {"SKILLS_DIR": str(d), "PATH": os.environ["PATH"], "HOME": str(tmp_path)}
    r = subprocess.run([sys.executable, "-m", "picobot", "skills", "list"], env=env, cwd=tmp_path,
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


# ---------------- skills deps (Task 11) ----------------
import json                                                        # noqa: E402

from picobot.skills_cli import declared_deps, missing_deps, write_missing   # noqa: E402


def skill_with_deps(root, name="s1"):
    p = root / name
    p.mkdir(parents=True)
    (p / "SKILL.md").write_text(f"---\nname: {name}\ndescription: con dipendenze\n---\n")
    (p / "requirements.txt").write_text("# commento\n\nopenpyxl==3.1.5\n")
    (p / "package.json").write_text(json.dumps({"dependencies": {"docx": "^9.0.0", "pptxgenjs": "~4.0.1"}}))
    (p / "apt.txt").write_text("fonts-liberation\n")
    return p


def test_declared(d):
    skill_with_deps(d)
    (d / "senza").mkdir()
    (d / "senza" / "SKILL.md").write_text("---\nname: senza\ndescription: x\n---\n")
    decl = declared_deps(d)
    assert decl == {"s1": {"pip": ["openpyxl==3.1.5"], "npm": ["docx@9.0.0", "pptxgenjs@4.0.1"], "apt": ["fonts-liberation"]}}


def test_missing_compares_by_name(d, tmp_path):
    skill_with_deps(d)
    deps = tmp_path / "deps"
    deps.mkdir()
    (deps / "npm.txt").write_text("# skill: altro\ndocx@9.5.0\n")
    (deps / "pip.txt").write_text("OpenPyXL==3.0.0\n")
    miss = missing_deps(declared_deps(d), deps)
    assert miss == {"pip": [], "npm": ["pptxgenjs@4.0.1"], "apt": ["fonts-liberation"]}


def test_write_missing_idempotent(d, tmp_path):
    skill_with_deps(d)
    deps = tmp_path / "deps"
    decl = declared_deps(d)
    assert write_missing(decl, deps) == 4 and write_missing(decl, deps) == 0
    npm = (deps / "npm.txt").read_text()
    assert "# skill: s1" in npm and "docx@9.0.0" in npm and missing_deps(decl, deps) == {"pip": [], "npm": [], "apt": []}


def test_cli_deps_exit_codes(d, tmp_path, capsys):
    s = Settings(skills_dir=d)
    deps = tmp_path / "deps"
    assert main_skills(["deps", "--deps-dir", str(deps)], s) == 0              # nessuna dipendenza dichiarata
    skill_with_deps(d)
    assert main_skills(["deps", "--deps-dir", str(deps)], s) == 1              # mancanti, senza --write
    assert "pptxgenjs@4.0.1" in capsys.readouterr().out and not deps.exists()  # non scrive e non installa
    assert main_skills(["deps", "--write", "--deps-dir", str(deps)], s) == 0
    assert main_skills(["deps", "--deps-dir", str(deps)], s) == 0


def test_add_summary_lists_declared_deps(capsys, tmp_path, d):
    src = skill_with_deps(tmp_path / "src")
    assert main_skills(["add", str(src)], Settings(skills_dir=d)) == 0
    assert "pip: openpyxl==3.1.5" in capsys.readouterr().out
