"""Contesto del run corrente (chi chiede, su che canale, come confermare azioni rischiose).

Viaggia in un ContextVar: i tool (es. run_python) lo leggono senza dipendere da Agno.
"""
from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from dataclasses import dataclass, field
from pathlib import Path

# (codice completo, linguaggio "python" | "node") -> l'utente conferma?
ConfirmFn = Callable[[str, str], Awaitable[bool]]


@dataclass
class OutputFile:
    path: Path
    name: str
    size: int


@dataclass
class Reply:
    text: str
    files: list[OutputFile] = field(default_factory=list)


@dataclass
class RunCtx:
    user_id: str
    channel: str                       # telegram | cli | api | schedule
    confirm: ConfirmFn | None = None   # human-in-the-loop interattivo (telegram, cli)
    pre_approved: bool = False         # approvazione esplicita a monte (api: approve_code=true)
    outputs: list[OutputFile] = field(default_factory=list)   # file consegnati da deliver_file
    runs: int = 0                      # esecuzioni di codice approvate in questa richiesta
    document: Path | None = None       # documento caricato in questa richiesta (Telegram, CLI)
    document_name: str = ""

    @property
    def can_run_code(self) -> bool:
        return self.confirm is not None or self.pre_approved


_current: ContextVar[RunCtx | None] = ContextVar("picobot_run_ctx", default=None)


def set_ctx(ctx: RunCtx | None):
    return _current.set(ctx)


def reset_ctx(token) -> None:
    _current.reset(token)


def get_ctx() -> RunCtx | None:
    return _current.get()
