"""Titolo e note della release dall'ultima sezione di CHANGELOG.md.

Uso: changelog_release.py CHANGELOG.md <versione> <notes.md>
Stampa il titolo (la prima riga "## ", es. "[0.8.3] - 2026-11-09") e scrive in <notes.md>
i paragrafi "### ..." che la seguono. Exit 1 se la versione non coincide o mancano le note.
"""
import re
import sys
from pathlib import Path


def parse(text: str, version: str) -> tuple[str, str]:
    m = re.search(r"^## ([^\n]+)(.*?)(?=^## |\Z)", text, re.M | re.S)
    if not m:
        raise ValueError("nessuna sezione '## ' nel changelog")
    title, notes = m.group(1).strip(), m.group(2).strip()
    if not title.startswith(f"[{version}]"):
        raise ValueError(f"l'ultima sezione del changelog è '{title}', attesa la versione {version}")
    if not notes:
        raise ValueError(f"la sezione '{title}' del changelog non ha note")
    return title, notes


if __name__ == "__main__":
    changelog, version, out = sys.argv[1:4]
    try:
        title, notes = parse(Path(changelog).read_text(encoding="utf-8"), version)
    except ValueError as e:
        print(f"::error::{e}", file=sys.stderr)  # stdout è riservato al titolo
        sys.exit(1)
    Path(out).write_text(notes + "\n", encoding="utf-8")
    print(title)
