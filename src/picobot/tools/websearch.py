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

import httpx
from agno.tools.keenable import KeenableTools
from ddgs import DDGS
from ddgs.exceptions import DDGSException

from ..config import Settings

logger = logging.getLogger(__name__)

# Provati il 2026-10-29: DuckDuckGo e' l'unico che risponde con costanza. Brave da' 429, Google e' disattivato in ddgs.
# keenable non e' un motore ddgs: Agno KeenableTools, senza chiave usa l'endpoint pubblico (nessuna ricerca news).
# brave non e' il backend ddgs (scraping, 429) ma l'API ufficiale con BRAVE_API_KEY: senza chiave si salta. Endpoint
# LLM Context (estratti di pagina per l'LLM, non solo titolo e riga). Via httpx e non con Agno BraveSearchTools: il
# pacchetto brave-search fissa httpx<0.26 e non si installa.
BRAVE_URL = "https://api.search.brave.com/res/v1/llm/context"
BRAVE_TOKENS = 2048   # token di estratti per ricerca (minimo 1024, default Brave 8192)
TEXT_ENGINES = ("brave", "duckduckgo", "keenable", "yahoo", "startpage", "mojeek")
NEWS_ENGINES = ("duckduckgo", "bing", "yahoo")
NO_RESULTS = "Nessun risultato da nessun motore di ricerca: riprova con una query piu' breve o con parole diverse."
WINDOW_S, KEEP_S = 24 * 3600, 7 * 24 * 3600
SQL_CREATE = "CREATE TABLE IF NOT EXISTS picobot_search_log(category TEXT, engine TEXT, ts REAL, ok INTEGER)"
SQL_RATES = "SELECT engine, AVG(ok) FROM picobot_search_log WHERE category=? AND ts>? GROUP BY engine"
SQL_PURGE = "DELETE FROM picobot_search_log WHERE ts<?"
SQL_INSERT = "INSERT INTO picobot_search_log VALUES(?,?,?,?)"


def make_web_tools(s: Settings) -> list:
    def db() -> sqlite3.Connection:
        s.data_dir.mkdir(parents=True, exist_ok=True)
        c = sqlite3.connect(s.database_file, timeout=10)
        c.execute(SQL_CREATE)
        return c

    def ranked(category: str, engines: tuple[str, ...]) -> list[str]:
        # shortcut: un motore a intermittenza resta a meta' classifica; va bene finche' i motori sono pochi
        try:
            with closing(db()) as c:
                rate = dict(c.execute(SQL_RATES, (category, time.time() - WINDOW_S)))
        except sqlite3.Error as e:   # le statistiche non devono bloccare la ricerca
            logger.warning("statistiche ricerca non leggibili: %s", e)
            rate = {}
        return sorted(engines, key=lambda e: -rate.get(e, 1.0))   # sorted e' stabile: a parita' vale l'ordine scritto

    def record(category: str, engine: str, ok: bool) -> None:
        try:
            with closing(db()) as c, c:
                c.execute(SQL_PURGE, (time.time() - KEEP_S,))
                c.execute(SQL_INSERT, (category, engine, time.time(), int(ok)))
        except sqlite3.Error as e:
            logger.warning("statistiche ricerca non scrivibili: %s", e)

    def ask(engine: str, category: str, query: str, max_results: int) -> list:
        if engine == "brave":
            country, lang = s.region.split("-")   # shortcut: "uk-en" non e' un paese per Brave (GB), da mappare se serve
            try:
                r = httpx.get(BRAVE_URL, headers={"X-Subscription-Token": s.brave_api_key}, timeout=10,
                              params={"q": query, "maximum_number_of_urls": max_results, "maximum_number_of_tokens": BRAVE_TOKENS,
                                      "country": country.upper(), "search_lang": lang})
                r.raise_for_status()
                found = r.json().get("grounding", {}).get("generic", [])
            except (httpx.HTTPError, ValueError) as e:   # 429, chiave errata, rete, query > 600 caratteri: si passa al motore dopo
                logger.info("%s brave: %s", category, e)
                return []
            return [{"title": x.get("title"), "url": x.get("url"), "description": " ".join(x.get("snippets", []))} for x in found]
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
        engines = tuple(e for e in TEXT_ENGINES if e != "brave" or s.brave_api_key)
        return cascade("text", engines, query, max_results)

    def search_news(query: str, max_results: int = 5) -> str:
        """Cerca le notizie piu' recenti.

        Args:
            query: cosa cercare
            max_results: numero massimo di risultati (default 5)
        """
        return cascade("news", NEWS_ENGINES, query, max_results)

    return [web_search, search_news]
