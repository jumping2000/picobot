"""Consegna dei file prodotti dagli agenti: solo da workspace/outputs/, con controlli."""
import os
from pathlib import Path

from ..config import Settings
from ..context import OutputFile, get_ctx

_MIB = 1024 * 1024


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
