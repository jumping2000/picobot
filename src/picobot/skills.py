"""Skill estensibili (formato Agent Skills) per il ComplexTeam.

- Installare = copiare una cartella in SKILLS_DIR; cancellare = eliminarla. Nessun riavvio: `refresh()` le ricarica.
- `CatalogSkills`: istruzioni e riferimenti si'; esecuzione degli script delle skill (`get_skill_script`) NO.
  Il codice si esegue solo con run_python/run_node, dopo conferma umana.
- Lo snippet nel prompt ha lunghezza fissa: gli agenti scoprono le skill con `list_skills(query)`.
"""
import logging
import re
from dataclasses import dataclass
from pathlib import Path

import yaml
from agno.skills import LocalSkills, Skills
from agno.tools import Function

from .config import Settings

logger = logging.getLogger(__name__)

NAME_RE = re.compile(r"^[a-z0-9-]{1,64}$")
DESC_MAX = 120
SNIPPET = ("Hai skill installate (pacchetti di istruzioni per compiti specifici). Prima di iniziare chiama "
           "list_skills() e valuta se una facilita il compito; se si', leggila con get_skill_instructions(nome).")


@dataclass
class SkillInfo:
    name: str
    description: str
    files: int
    has_scripts: bool


def read_frontmatter(skill_md: Path) -> dict | None:
    """Frontmatter YAML di SKILL.md, o None se assente/illeggibile."""
    try:
        text = skill_md.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    m = re.match(r"^---\s*\n(.*?)\n---\s*(\n|$)", text, re.S)
    if not m:
        return None
    try:
        data = yaml.safe_load(m.group(1))
    except yaml.YAMLError:
        return None
    return data if isinstance(data, dict) else None


def skill_problem(folder: Path) -> str | None:
    """None se la cartella e' una skill valida, altrimenti il motivo."""
    if folder.name.startswith((".", "_")):
        return "cartella temporanea o nascosta"
    if not NAME_RE.fullmatch(folder.name):
        return "nome cartella non valido (ammessi a-z, 0-9, -)"
    fm = read_frontmatter(folder / "SKILL.md")
    if fm is None:
        return "SKILL.md mancante o senza frontmatter"
    if fm.get("name") != folder.name:
        return f"name nel frontmatter ({fm.get('name')!r}) diverso dal nome cartella"
    if not str(fm.get("description") or "").strip():
        return "description mancante"
    return None


class CatalogSkills(Skills):
    """Skills senza esecuzione di script, con catalogo ricercabile e snippet di lunghezza fissa."""

    def __init__(self, loaders, list_max: int = 50):
        self.list_max = list_max
        super().__init__(loaders=loaders)

    def list_skills(self, query: str = "") -> str:
        """Elenca le skill installate (nome: descrizione), le piu' pertinenti alla query per prime.

        Args:
            query: parole che descrivono il compito (vuota = tutte)
        """
        words = {w for w in re.findall(r"\w+", query.lower()) if len(w) > 2}
        def score(sk):
            text = f"{sk.name} {sk.description}".lower()
            return sum(1 for w in words if w in text)
        skills = sorted(self.get_all_skills(), key=lambda sk: (-score(sk), sk.name))[: self.list_max]
        if not skills:
            return "Nessuna skill installata."
        return "\n".join(f"- {sk.name}: {' '.join(sk.description.split())[:DESC_MAX]}" for sk in skills)

    def get_tools(self) -> list[Function]:
        tools = [t for t in super().get_tools() if t.name != "get_skill_script"]
        tools.append(Function(
            name="list_skills",
            description="Elenca le skill installate (nome e descrizione), le piu' pertinenti alla query per prime.",
            entrypoint=self.list_skills,
        ))
        return tools

    def get_system_prompt_snippet(self) -> str:
        return SNIPPET if self._skills else ""


class SkillRegistry:
    """Cartella delle skill + ricarica a caldo quando cambia."""

    def __init__(self, s: Settings):
        self.s = s
        self.dir = Path(s.skills_dir)
        self.skills: CatalogSkills | None = CatalogSkills([], list_max=s.skills_list_max) if s.enable_skills else None
        self._fingerprint: tuple = ()
        self.refresh(force=True)

    def _scan(self) -> tuple:
        if not self.dir.is_dir():
            return ()
        out = []
        try:
            for f in sorted(self.dir.iterdir()):
                md = f / "SKILL.md"
                if f.is_dir() and md.is_file():
                    out.append((f.name, f.stat().st_mtime_ns, md.stat().st_mtime_ns))
        except OSError as e:
            logger.warning("Skill: cartella %s illeggibile: %s", self.dir, e)
        return tuple(out)

    def refresh(self, force: bool = False) -> bool:
        """Ricarica se la cartella e' cambiata. True se l'elenco caricato e' cambiato."""
        if self.skills is None:
            return False
        fp = self._scan()
        if fp == self._fingerprint and not force:
            return False
        valid = []
        for name, *_ in fp:
            problem = skill_problem(self.dir / name)
            if problem:
                logger.warning("Skill '%s' ignorata: %s", name, problem)
            else:
                valid.append(self.dir / name)
        before = sorted(self.skills.get_skill_names())
        old_loaders, old_skills = self.skills.loaders, dict(self.skills._skills)
        self.skills.loaders = [LocalSkills(str(p), validate=False) for p in valid]
        try:
            self.skills.reload()
        except Exception as e:  # noqa: BLE001  si tiene l'elenco precedente
            logger.warning("Skill: ricarica fallita, mantengo l'elenco precedente: %s", e)
            self.skills.loaders, self.skills._skills = old_loaders, old_skills
            return False
        self._fingerprint = fp
        changed = sorted(self.skills.get_skill_names()) != before or not force
        if changed:
            logger.info("Skill caricate: %s", ", ".join(self.names()) or "nessuna")
        return changed

    def names(self) -> list[str]:
        return sorted(self.skills.get_skill_names()) if self.skills else []

    def info(self) -> list[SkillInfo]:
        if not self.skills:
            return []
        out = []
        for sk in sorted(self.skills.get_all_skills(), key=lambda x: x.name):
            folder = Path(sk.source_path) if sk.source_path else self.dir / sk.name
            files = sum(1 for p in folder.rglob("*") if p.is_file()) if folder.is_dir() else 0
            out.append(SkillInfo(sk.name, " ".join(sk.description.split()), files, (folder / "scripts").is_dir()))
        return out
