import importlib.util
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("changelog_release", ROOT / ".github/scripts/changelog_release.py")
cr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cr)

SAMPLE = "# Changelog\n\n## [1.2.0] - 2026-01-02\n\n### Added\n\n- a\n\n### Fixed\n\n- b\n\n## [1.1.0] - 2025-12-01\n\n### Added\n\n- old\n"


def test_parse_title_and_notes():
    title, notes = cr.parse(SAMPLE, "1.2.0")
    assert title == "[1.2.0] - 2026-01-02"
    assert notes.startswith("### Added") and "### Fixed" in notes and "old" not in notes


def test_parse_errors():
    with pytest.raises(ValueError):
        cr.parse(SAMPLE, "1.1.0")  # l'ultima sezione è 1.2.0
    with pytest.raises(ValueError):
        cr.parse("## [1.2.0] - 2026-01-02\n\n## [1.1.0] - x\n", "1.2.0")  # nessuna nota


def test_real_changelog_matches_pyproject():
    version = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    title, notes = cr.parse((ROOT / "CHANGELOG.md").read_text(encoding="utf-8"), version)
    assert title.startswith(f"[{version}]") and "### " in notes
