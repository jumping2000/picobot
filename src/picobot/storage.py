"""Persistenza: DB unico (sessioni, runs, memorie, learning) + Memory + Learning."""
from agno.db.sqlite import SqliteDb
import dataclasses
from typing import Optional

from agno.learn import EntityMemoryConfig, LearningMachine, LearningMode, UserProfile, UserProfileConfig
from agno.memory import MemoryManager
from agno.session import SessionSummaryManager

from .config import Settings
from .models import make_model
from .prompts import MEMORY_CAPTURE


def make_db(s: Settings) -> SqliteDb:
    s.data_dir.mkdir(parents=True, exist_ok=True)
    return SqliteDb(db_file=str(s.database_file))


def make_memory_manager(s: Settings, db: SqliteDb) -> MemoryManager:
    return MemoryManager(db=db, model=make_model(s), memory_capture_instructions=MEMORY_CAPTURE)


def _f(desc: str):
    return dataclasses.field(default=None, metadata={"description": desc})


@dataclasses.dataclass
class PicoProfile(UserProfile):
    """Profilo strutturato dell'utente (oltre a name e preferred_name)."""
    lingua: Optional[str] = _f("Lingua preferita per le risposte, es. italiano")
    fuso_orario: Optional[str] = _f("Fuso orario IANA dell'utente, es. Europe/Rome")
    formato_risposta: Optional[str] = _f("Formato preferito delle risposte, es. 'breve a punti'")
    titoli_seguiti: Optional[str] = _f("Ticker che l'utente segue, separati da virgola, es. 'AAPL, ENI.MI'")


def _learning(s: Settings, db: SqliteDb, write: bool) -> LearningMachine:
    ro = {} if write else {"enable_agent_tools": False}
    return LearningMachine(
        db=db, model=make_model(s),
        user_profile=UserProfileConfig(mode=LearningMode.AGENTIC, schema=PicoProfile,
                                       **(ro | ({} if write else {"agent_can_update_profile": False}))),
        entity_memory=EntityMemoryConfig(mode=LearningMode.AGENTIC, namespace="user", **ro),   # privata per utente
    )


def make_learning(s: Settings, db: SqliteDb) -> LearningMachine:
    """Profilo + entita' IN SCRITTURA (solo router). AGENTIC: nessuna chiamata LLM in piu'."""
    return _learning(s, db, write=True)


def make_learning_view(s: Settings, db: SqliteDb) -> LearningMachine:
    """Stessi dati in SOLA LETTURA (leader dei team, Finance). Chi la usa deve avere anche `db`."""
    return _learning(s, db, write=False)


def make_summary_manager(s: Settings) -> SessionSummaryManager:
    return SessionSummaryManager(model=make_model(s))
