"""Consegna dei file prodotti dagli agenti: solo da workspace/outputs/, con controlli."""
import hashlib
import os
import re
import shutil
import time
import uuid
from pathlib import Path

from ..config import Settings
from ..context import OutputFile, get_ctx

_MIB = 1024 * 1024
_ID = re.compile(r"^[0-9a-f]{32}$")


class _Refused(Exception):
    pass


def _validate(s: Settings, path: str) -> Path:
    outputs = Path(os.path.abspath(s.outputs_dir))
    raw = Path(path)
    candidate = Path(os.path.abspath(raw if raw.is_absolute() else s.workspace_dir / raw))
    try:
        rel = candidate.relative_to(outputs)
    except ValueError:
        raise _Refused("il file deve stare dentro outputs/") from None
    cur = outputs
    for part in rel.parts:                      # nessun componente symlink dentro outputs
        cur = cur / part
        if cur.is_symlink():
            raise _Refused("i symlink non sono ammessi")
    if not candidate.resolve().is_relative_to(s.outputs_dir.resolve()):
        raise _Refused("il file deve stare dentro outputs/")
    if not candidate.is_file():
        raise _Refused("file non trovato")
    if candidate.suffix.lower().lstrip(".") not in s.output_ext_set:
        raise _Refused(f"estensione non ammessa (ammesse: {', '.join(sorted(s.output_ext_set))})")
    if candidate.stat().st_size > s.max_output_mb * _MIB:
        raise _Refused(f"file troppo grande (max {s.max_output_mb} MB)")
    return candidate


def make_file_tools(s: Settings) -> list:
    async def deliver_file(path: str) -> str:
        """Consegna all'utente un file che hai creato (Word, PowerPoint, Excel, CSV, testo, PDF).
        Il file deve stare in outputs/ (es. "outputs/relazione.docx").

        Args:
            path: percorso del file relativo al workspace, es. "outputs/relazione.docx"
        """
        ctx = get_ctx()
        if ctx is None:
            return "Rifiutato: nessuna richiesta attiva a cui consegnare il file."
        try:
            target = _validate(s, path)
        except _Refused as e:
            return f"Rifiutato: {e}."
        if any(f.path == target for f in ctx.outputs):
            return f"Consegnato: {target.name} (gia' in elenco)."
        if len(ctx.outputs) >= s.max_output_files:
            return f"Rifiutato: massimo {s.max_output_files} file per richiesta."
        ctx.outputs.append(OutputFile(path=target, name=target.name, size=target.stat().st_size))
        return f"Consegnato: {target.name} ({target.stat().st_size} byte)."

    return [deliver_file]


# ---------------- file di testo scritti direttamente (senza eseguire codice) ----------------
TEXT_EXTENSIONS = {"md", "txt", "csv", "html", "json"}


def make_text_tools(s: Settings) -> list:
    async def save_text_file(filename: str, content: str) -> str:
        """Salva un file di testo (Markdown, testo, CSV, HTML, JSON) in outputs/ senza eseguire codice.
        Per consegnarlo all'utente chiama poi deliver_file con il percorso restituito.

        Args:
            filename: solo il nome del file, senza cartelle, es. "relazione.md"
            content: contenuto completo del file
        """
        allowed = TEXT_EXTENSIONS & s.output_ext_set
        name = (filename or "").strip()
        if not name or len(name) > 120 or any(c in name for c in "/\\\0") or ".." in name or name.startswith("."):
            return "Rifiutato: nome file non valido (solo il nome, senza cartelle, max 120 caratteri)."
        if Path(name).suffix.lower().lstrip(".") not in allowed:
            return f"Rifiutato: estensione non ammessa (ammesse: {', '.join(sorted(allowed))})."
        data = content.encode("utf-8")
        if len(data) > s.max_output_mb * _MIB:
            return f"Rifiutato: file troppo grande (max {s.max_output_mb} MB)."
        s.outputs_dir.mkdir(parents=True, exist_ok=True)
        target = s.outputs_dir / name
        if target.is_symlink():
            return "Rifiutato: i symlink non sono ammessi."
        target.write_bytes(data)
        return f"Salvato: outputs/{name}"

    return [save_text_file]


# ---------------- outbox per l'API ----------------
def _user_dir(s: Settings, user_id: str) -> Path:
    # hash: nessun carattere dell'id utente finisce nel percorso, e due id diversi non collidono
    return s.outbox_dir / hashlib.sha256(user_id.encode("utf-8")).hexdigest()[:24]


def store_outputs(s: Settings, user_id: str, files: list[OutputFile]) -> list[dict]:
    """Copia i file in data/outbox/<utente>/<id>/<nome> e ritorna i metadati per l'API."""
    out = []
    for f in files:
        fid = uuid.uuid4().hex
        dest = _user_dir(s, user_id) / fid
        dest.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f.path, dest / f.name)
        out.append({"id": fid, "name": f.name, "size": f.size})
    return out


def find_output(s: Settings, user_id: str, file_id: str) -> Path | None:
    """Percorso del file dell'utente, o None (altrui, inesistente e id non valido sono indistinguibili)."""
    if not _ID.fullmatch(file_id or ""):
        return None
    folder = _user_dir(s, user_id) / file_id
    if not folder.is_dir():
        return None
    for p in folder.iterdir():
        if p.is_file() and not p.is_symlink() and p.resolve().is_relative_to(s.outbox_dir.resolve()):
            return p
    return None


def purge_outbox(s: Settings) -> int:
    """Rimuove le consegne piu' vecchie di OUTBOX_TTL_H. Ritorna il numero di consegne rimosse."""
    if not s.outbox_dir.is_dir():
        return 0
    limit, removed = time.time() - s.outbox_ttl_h * 3600, 0
    for user in s.outbox_dir.iterdir():
        for entry in user.iterdir() if user.is_dir() else []:
            if entry.is_dir() and entry.stat().st_mtime < limit:
                shutil.rmtree(entry, ignore_errors=True)
                removed += 1
    return removed
