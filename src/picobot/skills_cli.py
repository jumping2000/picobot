"""CLI admin delle skill (da eseguire sull'host): `picobot skills list|add|remove|validate`.

Installare una skill = copiare la sua cartella nella cartella skill; il bot la vede senza riavvio.
L'installazione e' atomica (copia in .tmp-<id> e rename) e rifiuta zip ostili, symlink e nomi non validi.
"""
import argparse
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import uuid
import zipfile
from pathlib import Path, PurePosixPath

from .config import Settings
from .skills import NAME_RE, SkillInfo, read_frontmatter, skill_problem

MAX_SKILL_BYTES = 50 * 1024 * 1024
_GIT_PREFIXES = ("file://", "http://", "https://", "git@", "ssh://")


class SkillInstallError(ValueError):
    pass


def _info(folder: Path) -> SkillInfo:
    fm = read_frontmatter(folder / "SKILL.md") or {}
    files = sum(1 for p in folder.rglob("*") if p.is_file())
    return SkillInfo(str(fm.get("name", folder.name)), " ".join(str(fm.get("description", "")).split()),
                     files, (folder / "scripts").is_dir())


def _safe_extract(zip_path: Path, dest: Path) -> None:
    with zipfile.ZipFile(zip_path) as zf:
        for m in zf.infolist():
            parts = PurePosixPath(m.filename).parts
            if m.filename.startswith(("/", "\\")) or ".." in parts or (parts and ":" in parts[0]):
                raise SkillInstallError(f"zip non sicuro: percorso '{m.filename}'")
            if stat.S_ISLNK(m.external_attr >> 16):
                raise SkillInstallError(f"zip non sicuro: symlink '{m.filename}'")
        zf.extractall(dest)


def _fetch(source: str, work: Path) -> Path:
    if source.startswith(_GIT_PREFIXES) or source.endswith(".git"):
        if shutil.which("git") is None:
            raise SkillInstallError("git non installato: serve per installare da un repository")
        r = subprocess.run(["git", "clone", "--depth", "1", "--quiet", source, str(work / "repo")],
                           capture_output=True, text=True)
        if r.returncode != 0:
            raise SkillInstallError(f"git clone fallito: {r.stderr.strip()[:200]}")
        shutil.rmtree(work / "repo" / ".git", ignore_errors=True)
        return work / "repo"
    path = Path(source).expanduser()
    if path.is_file() and path.suffix.lower() == ".zip":
        try:
            _safe_extract(path, work / "zip")
        except zipfile.BadZipFile as e:
            raise SkillInstallError(f"zip non valido: {e}") from e
        return work / "zip"
    if path.is_dir():
        return path
    raise SkillInstallError(f"sorgente non trovata: {source}")


def _find_skill_dir(root: Path) -> Path:
    if (root / "SKILL.md").is_file():
        return root
    found = [p for p in root.iterdir()
             if p.is_dir() and not p.name.startswith((".", "__")) and (p / "SKILL.md").is_file()]
    if len(found) != 1:
        raise SkillInstallError("SKILL.md non trovato (attesa una cartella con SKILL.md, alla radice o unica sottocartella)")
    return found[0]


def _validate_tree(folder: Path) -> tuple[str, str]:
    fm = read_frontmatter(folder / "SKILL.md")
    if fm is None:
        raise SkillInstallError("SKILL.md senza frontmatter YAML valido")
    name = str(fm.get("name") or "")
    if not NAME_RE.fullmatch(name):
        raise SkillInstallError(f"name non valido {name!r}: ammessi a-z, 0-9, - (max 64)")
    desc = " ".join(str(fm.get("description") or "").split())
    if not desc:
        raise SkillInstallError("description mancante nel frontmatter")
    total = 0
    for dirpath, dirnames, filenames in os.walk(folder):
        for entry in dirnames + filenames:
            p = Path(dirpath) / entry
            if p.is_symlink():
                raise SkillInstallError(f"symlink non ammesso: {p.relative_to(folder)}")
        total += sum((Path(dirpath) / f).stat().st_size for f in filenames)
        if total > MAX_SKILL_BYTES:
            raise SkillInstallError(f"skill troppo grande (max {MAX_SKILL_BYTES // (1024 * 1024)} MB)")
    return name, desc


def install(source: str, dir: Path, force: bool = False) -> SkillInfo:
    """Installa una skill da cartella, .zip o repository git. Atomica: o tutto o niente."""
    dir = Path(dir)
    dir.mkdir(parents=True, exist_ok=True)
    tmp = dir / f".tmp-{uuid.uuid4().hex}"
    old = dir / f".old-{uuid.uuid4().hex}"
    try:
        with tempfile.TemporaryDirectory(prefix="picobot-skill-") as work:
            skill = _find_skill_dir(_fetch(source, Path(work)))
            name, _ = _validate_tree(skill)
            target = dir / name
            if target.exists() and not force:
                raise SkillInstallError(f"skill '{name}' gia' installata: usa --force per sostituirla")
            shutil.copytree(skill, tmp, symlinks=True, ignore=shutil.ignore_patterns(".git"))
            if target.exists():
                os.replace(target, old)
            os.replace(tmp, target)
            shutil.rmtree(old, ignore_errors=True)
            return _info(target)
    except SkillInstallError:
        raise
    except OSError as e:
        raise SkillInstallError(f"installazione fallita: {e}") from e
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        shutil.rmtree(old, ignore_errors=True)


def remove(name: str, dir: Path) -> None:
    if not NAME_RE.fullmatch(name or ""):
        raise SkillInstallError(f"nome skill non valido: {name!r}")
    target = Path(dir) / name
    if not target.is_dir():
        raise SkillInstallError(f"skill '{name}' non installata")
    shutil.rmtree(target)


def list_installed(dir: Path) -> list[SkillInfo]:
    dir = Path(dir)
    if not dir.is_dir():
        return []
    return [_info(p) for p in sorted(dir.iterdir()) if p.is_dir() and skill_problem(p) is None]


def validate_dir(dir: Path) -> list[tuple[str, str]]:
    """Cartelle presenti che il bot ignorerebbe, con il motivo."""
    dir = Path(dir)
    if not dir.is_dir():
        return []
    out = []
    for p in sorted(dir.iterdir()):
        if p.is_dir() and not p.name.startswith("."):
            problem = skill_problem(p)
            if problem:
                out.append((p.name, problem))
    return out


def _default_dir(s: Settings) -> Path:
    # sull'host la cartella del container (/app/skills) non esiste: si usa ./skills
    return Path(s.skills_dir) if Path(s.skills_dir).is_dir() else Path("skills")


def _print_info(info: SkillInfo) -> None:
    print(f"Installata: {info.name}\n  {info.description}\n  file: {info.files}")
    if info.has_scripts:
        print("  Attenzione: contiene scripts/. Il bot non li esegue direttamente: l'Analyst puo' usarli come "
              "riferimento e ogni esecuzione di codice richiede la tua conferma.")


def main_skills(argv: list[str], s: Settings) -> int:
    p = argparse.ArgumentParser(prog="picobot skills", description="Gestione delle skill (dall'host)")
    p.add_argument("--dir", type=Path, default=None, help="cartella skill (default: SKILLS_DIR o ./skills)")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="elenca le skill installate")
    a = sub.add_parser("add", help="installa da cartella, .zip o repository git")
    a.add_argument("source")
    a.add_argument("--force", action="store_true", help="sostituisce una skill gia' installata")
    r = sub.add_parser("remove", help="cancella una skill")
    r.add_argument("name")
    sub.add_parser("validate", help="segnala le cartelle che il bot ignorerebbe")
    args = p.parse_args(argv)
    dir = args.dir or _default_dir(s)
    try:
        if args.cmd == "list":
            infos = list_installed(dir)
            for i in infos:
                print(f"{i.name}: {i.description[:120]}  ({i.files} file{', scripts/' if i.has_scripts else ''})")
            if not infos:
                print(f"Nessuna skill installata in {dir}.")
        elif args.cmd == "add":
            _print_info(install(args.source, dir, force=args.force))
        elif args.cmd == "remove":
            remove(args.name, dir)
            print(f"Rimossa: {args.name}")
        elif args.cmd == "validate":
            problems = validate_dir(dir)
            for name, why in problems:
                print(f"{name}: {why}")
            if problems:
                return 1
            print("Tutte le skill sono valide.")
        return 0
    except SkillInstallError as e:
        print(f"Errore: {e}", file=sys.stderr)
        return 1
