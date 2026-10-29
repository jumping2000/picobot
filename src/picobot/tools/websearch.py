"""Ricerca web e notizie a cascata: un motore alla volta, nell'ordine dato; il successivo solo se il precedente
non trova nulla.

Con backend="auto" ddgs interroga piu' motori in parallelo, Wikipedia e Grokipedia sempre per prime e gli altri in
ordine casuale: molte richieste a vuoto e, se DuckDuckGo non capita in tempo, nessun risultato.
"""
import json
import logging

from ddgs import DDGS
from ddgs.exceptions import DDGSException

from ..config import Settings

logger = logging.getLogger(__name__)

# Provati il 2026-10-29: DuckDuckGo e' l'unico che risponde con costanza. Brave da' 429, Google e' disattivato in ddgs.
TEXT_ENGINES = ("duckduckgo", "yahoo", "startpage", "mojeek")
NEWS_ENGINES = ("duckduckgo", "bing", "yahoo")
NO_RESULTS = "Nessun risultato da nessun motore di ricerca: riprova con una query piu' breve o con parole diverse."


def make_web_tools(s: Settings) -> list:
    def cascade(category: str, engines: tuple[str, ...], query: str, max_results: int) -> str:
        for engine in engines:
            try:
                results = getattr(DDGS(timeout=10), category)(
                    query, backend=engine, region=s.region, max_results=max_results)
            except DDGSException as e:
                logger.info("%s %s: %s, provo il motore successivo", category, engine, e)
                continue
            if results:
                return json.dumps(results, indent=2, ensure_ascii=False)
        return NO_RESULTS

    def web_search(query: str, max_results: int = 5) -> str:
        """Cerca sul web.

        Args:
            query: cosa cercare
            max_results: numero massimo di risultati (default 5)
        """
        return cascade("text", TEXT_ENGINES, query, max_results)

    def search_news(query: str, max_results: int = 5) -> str:
        """Cerca le notizie piu' recenti.

        Args:
            query: cosa cercare
            max_results: numero massimo di risultati (default 5)
        """
        return cascade("news", NEWS_ENGINES, query, max_results)

    return [web_search, search_news]
