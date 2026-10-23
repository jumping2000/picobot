"""Persistenza: DB unico (sessioni, runs, memorie, learning) + Memory + Learning."""
from agno.db.sqlite import SqliteDb
from agno.learn import LearningMachine, LearningMode, UserProfileConfig
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


def make_learning(s: Settings, db: SqliteDb) -> LearningMachine:
    """AGENTIC: il router aggiorna il profilo solo quando serve (0 chiamate extra).
    session_context supporta solo ALWAYS (1 chiamata/run): non usato."""
    return LearningMachine(db=db, model=make_model(s), user_profile=UserProfileConfig(mode=LearningMode.AGENTIC))


def make_summary_manager(s: Settings) -> SessionSummaryManager:
    return SessionSummaryManager(model=make_model(s))
