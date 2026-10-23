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
from .tools.files import make_file_tools
from .tools.sandbox import make_code_tools, make_node_tools


def _yf() -> YFinanceTools:
    return YFinanceTools(
        enable_stock_price=True,
        enable_company_info=True,
        enable_historical_prices=True,
        enable_analyst_recommendations=True,
        enable_company_news=True,
    )


def build_finance(s: Settings) -> Agent:
    return Agent(
        name="Finance",
        role="Quotazioni, storico prezzi, fondamentali e news di titoli/ETF/crypto via yfinance.",
        model=make_model(s), tools=[_yf()], instructions=[prompts.FINANCE],
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
        role="Scrive piccoli programmi Python e, solo con conferma umana, li esegue nel workspace.",
        model=make_model(s), tools=make_code_tools(s), instructions=[prompts.CODER],
    )


def build_complex_team(s: Settings, registry: SkillRegistry | None = None, mcp_tools: list | None = None) -> Team:
    """Leader + Researcher, Analyst, Writer, (Critic). Skill e MCP condivisi da tutti; solo l'Analyst esegue e consegna."""
    strong = lambda: make_model(s, strong=True)  # noqa: E731
    # `is not None`, mai un test di verita': un catalogo vuoto va collegato comunque (skill aggiunte dopo l'avvio)
    skills = registry.skills if registry is not None and registry.skills is not None else None
    mcp = list(mcp_tools or [])
    members = [
        Agent(name="Researcher", role="Ricerca web approfondita con fonti.", model=strong(),
              tools=[DuckDuckGoTools(), *mcp], skills=skills, instructions=[prompts.RESEARCHER]),
        Agent(name="Analyst", role="Calcoli, analisi dati, dati di mercato, codice; crea e consegna file (Word, PowerPoint, Excel).",
              model=strong(),
              tools=[_yf(), *make_code_tools(s), *make_node_tools(s), *make_file_tools(s), *mcp],
              skills=skills, instructions=[prompts.ANALYST]),
        Agent(name="Writer", role="Redige e formatta i testi finali per Telegram.", model=make_model(s),
              tools=[*mcp], skills=skills, instructions=[prompts.WRITER]),
    ]
    if s.enable_critic:
        members.append(Agent(name="Critic", role="Revisiona la bozza: allucinazioni e dati senza fonte.",
                             model=strong(), tools=[*mcp], skills=skills, instructions=[prompts.CRITIC]))
    return Team(
        name="ComplexTeam",
        role=("Task complessi multi-step (ricerca approfondita + analisi + report) e creazione di documenti "
              "Word/PowerPoint/Excel con le skill installate. Costoso: usalo solo se necessario."),
        mode=TeamMode.coordinate, model=strong(), members=members, skills=skills,
        instructions=[prompts.COMPLEX_LEADER],
    )
