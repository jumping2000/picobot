"""Ricerca web e notizie a cascata: un motore alla volta, nell'ordine dato; il successivo solo se il precedente
non trova nulla.

Con backend="auto" ddgs interroga piu' motori in parallelo, Wikipedia e Grokipedia sempre per prime e gli altri in
ordine casuale: molte richieste a vuoto e, se DuckDuckGo non capita in tempo, nessun risultato.

L'ordine scritto qui e' quello di partenza: prima di ogni ricerca i motori si riordinano per tasso di successo nelle
ultime 24 ore (tabella picobot_search_log nel DB). Chi non ha dati vale 1.0, quindi dopo 24 ore senza tentativi un
motore caduto viene riprovato. Statistiche: SELECT engine, COUNT(*), AVG(ok) FROM picobot_search_log GROUP BY engine.
"""
import json
import logging
import sqlite3
import time
from contextlib import closing

from agno.tools.keenable import KeenableTools
from ddgs import DDGS
from ddgs.exceptions import DDGSException

from ..config import Settings

logger = logging.getLogger(__name__)

# Provati il 2026-10-29: DuckDuckGo e' l'unico che risponde con costanza. Brave da' 429, Google e' disattivato in ddgs.
# keenable non e' un motore ddgs: Agno KeenableTools, senza chiave usa l'endpoint pubblico (nessuna ricerca news).
TEXT_ENGINES = ("duckduckgo", "keenable", "yahoo", "startpage", "mojeek")
NEWS_ENGINES = ("duckduckgo", "bing", "yahoo")
NO_RESULTS = "Nessun risultato da nessun motore di ricerca: riprova con una query piu' breve o con parole diverse."
WINDOW_S, KEEP_S = 24 * 3600, 7 * 24 * 3600


def make_web_tools(s: Settings) -> list:
    def db() -> sqlite3.Connection:
        s.data_dir.mkdir(parents=True, exist_ok=True)
        c = sqlite3.connect(s.database_file, timeout=10)
        c.execute("CREATE TABLE IF NOT EXISTS picobot_search_log(category TEXT, engine TEXT, ts REAL, ok INTEGER)")
        return c

    def ranked(category: str, engines: tuple[str, ...]) -> list[str]:
        # shortcut: un motore a intermittenza resta a meta' classifica; va bene finche' i motori sono pochi
        try:
            with closing(db()) as c:
                rate = dict(c.execute("SELECT engine, AVG(ok) FROM picobot_search_log WHERE category=? AND ts>? "
                                      "GROUP BY engine", (category, time.time() - WINDOW_S)))
        except sqlite3.Error as e:   # le statistiche non devono bloccare la ricerca
            logger.warning("statistiche ricerca non leggibili: %s", e)
            rate = {}
        return sorted(engines, key=lambda e: -rate.get(e, 1.0))   # sorted e' stabile: a parita' vale l'ordine scritto

    def record(category: str, engine: str, ok: bool) -> None:
        try:
            with closing(db()) as c, c:
                c.execute("DELETE FROM picobot_search_log WHERE ts<?", (time.time() - KEEP_S,))
                c.execute("INSERT INTO picobot_search_log VALUES(?,?,?,?)", (category, engine, time.time(), int(ok)))
        except sqlite3.Error as e:
            logger.warning("statistiche ricerca non scrivibili: %s", e)

    def ask(engine: str, category: str, query: str, max_results: int) -> list:
        if engine == "keenable":
            out = KeenableTools(format="json", max_results=max_results, timeout=10).web_search(query)
            try:
                return json.loads(out)["results"]
            except (ValueError, KeyError, TypeError):   # Keenable segnala gli errori con una stringa, non con un'eccezione
                logger.info("%s keenable: %s", category, out)
                return []
        return getattr(DDGS(timeout=10), category)(query, backend=engine, region=s.region, max_results=max_results)

    def cascade(category: str, engines: tuple[str, ...], query: str, max_results: int) -> str:
        for engine in ranked(category, engines):
            try:
                results = ask(engine, category, query, max_results)
            except DDGSException as e:
                logger.info("%s %s: %s, provo il motore successivo", category, engine, e)
                results = []
            record(category, engine, bool(results))
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
