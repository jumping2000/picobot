"""Router: Team coordinate su modello economico. Risponde da solo alle domande semplici
(1 sola chiamata LLM) e delega agli specialisti solo quando serve."""
from agno.team import Team
from agno.team.mode import TeamMode

from . import prompts
from .agents import build_coder, build_complex_team, build_finance, build_web
from .config import Settings
from .skills import SkillRegistry
from .models import make_model
from .storage import make_db, make_learning, make_memory_manager, make_summary_manager


def build_router(s: Settings, registry: SkillRegistry | None = None, mcp_tools: list | None = None) -> Team:
    db = make_db(s)
    kw: dict = {}
    if s.enable_memory:
        # agentic: e' il router a chiamare add_memory quando l'utente dichiara un fatto (nessuna chiamata extra)
        kw.update(memory_manager=make_memory_manager(s, db), enable_agentic_memory=True, add_memories_to_context=True)
    if s.enable_learning:
        kw.update(learning=make_learning(s, db), add_learnings_to_context=True)
    if s.enable_session_summaries:
        kw.update(enable_session_summaries=True, session_summary_manager=make_summary_manager(s),
                  add_session_summary_to_context=True)
    return Team(
        name="PicoBot",
        mode=TeamMode.coordinate,
        model=make_model(s),
        members=[build_finance(s), build_web(s), build_coder(s), build_complex_team(s, registry, mcp_tools)],
        instructions=prompts.router_instructions(registry.names() if registry else [], s.skills_router_hint_max),
        db=db,
        add_history_to_context=True,
        num_history_runs=s.history_runs,
        markdown=True,
        **kw,
    )
