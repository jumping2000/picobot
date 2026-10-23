"""Specialisti economici + ComplexTeam (costoso, solo per task complessi)."""
from agno.agent import Agent
from agno.team import Team
from agno.team.mode import TeamMode
from agno.tools.duckduckgo import DuckDuckGoTools
from agno.tools.yfinance import YFinanceTools

from . import prompts
from .config import Settings
from .models import make_model
from .tools.sandbox import make_code_tools


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


def build_complex_team(s: Settings, extra_tools: list | None = None) -> Team:
    strong = lambda: make_model(s, strong=True)  # noqa: E731
    members = [
        Agent(name="Researcher", role="Ricerca web approfondita con fonti.", model=strong(),
              tools=[DuckDuckGoTools()], instructions=[prompts.RESEARCHER]),
        Agent(name="Analyst", role="Calcoli, analisi dati, dati di mercato, codice.", model=strong(),
              tools=[_yf(), *make_code_tools(s), *(extra_tools or [])], instructions=[prompts.ANALYST]),
        Agent(name="Writer", role="Formatta il testo finale per Telegram.", model=make_model(s),
              instructions=[prompts.WRITER]),
    ]
    if s.enable_critic:
        members.append(Agent(name="Critic", role="Revisiona la bozza: allucinazioni e dati senza fonte.",
                             model=strong(), instructions=[prompts.CRITIC]))
    return Team(
        name="ComplexTeam",
        role="Task complessi multi-step: ricerca approfondita + analisi + report. Costoso: usalo solo se necessario.",
        mode=TeamMode.coordinate, model=strong(), members=members,
        instructions=[prompts.COMPLEX_LEADER],
    )
