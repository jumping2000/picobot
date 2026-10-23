"""Specialisti economici + ComplexTeam (costoso, solo per task complessi)."""
from agno.agent import Agent
from agno.team import Team
from agno.team.mode import TeamMode
from agno.tools.duckduckgo import DuckDuckGoTools
from agno.tools.yfinance import YFinanceTools

from . import prompts
from .config import Settings
from .models import make_model
from .skills import SkillRegistry
from .storage import make_learning_view
from .tools.documents import make_read_tools
from .tools.files import make_file_tools, make_text_tools
from .tools.sandbox import make_code_tools, make_node_tools


def _yf() -> YFinanceTools:
    return YFinanceTools(
        enable_stock_price=True,
        enable_company_info=True,
        enable_historical_prices=True,
        enable_analyst_recommendations=True,
        enable_company_news=True,
    )


def _view(s: Settings, db) -> dict:
    """Profilo ed entita' in sola lettura: Agno inizializza il learning solo se l'agente ha anche `db`."""
    return {"db": db, "learning": make_learning_view(s, db), "add_learnings_to_context": True} if db is not None else {}


def build_finance(s: Settings, db=None) -> Agent:
    return Agent(
        name="Finance",
        role="Quotazioni, storico prezzi, fondamentali e news di titoli/ETF/crypto via yfinance.",
        model=make_model(s), tools=[_yf()], instructions=[prompts.FINANCE], **_view(s, db),
    )


def build_web(s: Settings) -> Agent:
    return Agent(
        name="Web",
        role="Cerca informazioni e notizie aggiornate sul web.",
        model=make_model(s), tools=[DuckDuckGoTools()], instructions=[prompts.WEB],
    )


def build_coder(s: Settings) -> Agent:
    return Agent(
        name="Coder",
        role="Scrive piccoli programmi Python (eseguiti solo con conferma umana) e file di testo; consegna i file.",
        model=make_model(s), tools=[*make_code_tools(s), *make_text_tools(s), *make_file_tools(s)],
        instructions=[prompts.CODER],
    )


def build_simple_team(s: Settings, db=None) -> Team:
    """Compiti rapidi sul modello economico: ricerche, quotazioni, piccoli programmi e file di testo."""
    return Team(
        name="SimpleTeam",
        role="Compiti rapidi ed economici: quotazioni e dati di mercato, ricerche web, piccoli programmi Python, file di testo.",
        mode=TeamMode.coordinate, model=make_model(s),
        members=[build_web(s), build_finance(s, db), build_coder(s)],
        instructions=[prompts.SIMPLE_LEADER], **_view(s, db),
    )


def build_complex_team(s: Settings, registry: SkillRegistry | None = None, mcp_tools: list | None = None,
                       db=None) -> Team:
    """Leader + Researcher, Analyst, Writer, (Critic), tutti sul modello forte, con skill e MCP.
    L'Analyst ragiona e calcola (anche con codice) ma non consegna; il Writer produce e consegna il risultato."""
    strong = lambda: make_model(s, strong=True)  # noqa: E731
    # `is not None`, mai un test di verita': un catalogo vuoto va collegato comunque (skill aggiunte dopo l'avvio)
    skills = registry.skills if registry is not None and registry.skills is not None else None
    mcp = list(mcp_tools or [])
    read = make_read_tools(s)
    members = [
        Agent(name="Researcher", role="Ricerca web approfondita con fonti.", model=strong(),
              tools=[DuckDuckGoTools(), *mcp], skills=skills, instructions=[prompts.RESEARCHER]),
        Agent(name="Analyst", role="Ragiona, analizza e calcola (dati di mercato, codice, grafici); passa il materiale al Writer.",
              model=strong(), tools=[_yf(), *make_code_tools(s), *make_node_tools(s), *read, *mcp],
              skills=skills, instructions=[prompts.ANALYST]),
        Agent(name="Writer", role="Scrive, formatta e produce il risultato finale (testo, Word, PowerPoint, Excel) e lo consegna.",
              model=strong(),
              tools=[*make_text_tools(s), *make_code_tools(s), *make_node_tools(s), *make_file_tools(s), *read, *mcp],
              skills=skills, instructions=[prompts.WRITER]),
    ]
    if s.enable_critic:
        members.append(Agent(name="Critic", role="Revisiona la bozza: allucinazioni e dati senza fonte.",
                             model=strong(), tools=[*mcp], skills=skills, instructions=[prompts.CRITIC]))
    return Team(
        name="ComplexTeam",
        role=("Task complessi multi-step (ricerca approfondita + analisi + report) e creazione di documenti "
              "Word/PowerPoint/Excel con le skill installate. Costoso: usalo solo se necessario."),
        mode=TeamMode.coordinate, model=strong(), members=members, skills=skills,
        instructions=[prompts.COMPLEX_LEADER], **_view(s, db),
    )
