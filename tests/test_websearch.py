"""Ricerca web a cascata: un motore alla volta, il successivo solo se il precedente non trova nulla."""

import json
import sqlite3
import time
from contextlib import closing

import pytest
from ddgs.exceptions import DDGSException, TimeoutException

from picobot.config import Settings
from picobot.tools import websearch


class FakeDDGS:
    calls: list = []
    answers: dict = {}   # motore -> lista di risultati o eccezione

    def __init__(self, **kw):
        pass

    def text(self, query, *, backend, **kw):
        return self._go("text", backend)

    def news(self, query, *, backend, **kw):
        return self._go("news", backend)

    @classmethod
    def _go(cls, category, backend):
        cls.calls.append((category, backend))
        answer = cls.answers.get(backend, [])
        if isinstance(answer, Exception):
            raise answer
        if not answer:
            raise DDGSException("No results found.")   # come ddgs quando un motore non trova nulla
        return answer


class FakeKeenable:
    """KeenableTools: gli errori sono stringhe, non eccezioni."""

    def __init__(self, **kw):
        pass

    def web_search(self, query):
        FakeDDGS.calls.append(("text", "keenable"))
        answer = FakeDDGS.answers.get("keenable", "No results found.")
        return answer if isinstance(answer, str) else json.dumps({"query": query, "results": answer})


@pytest.fixture
def settings(tmp_path):
    return Settings(data_dir=tmp_path)


@pytest.fixture
def tools(monkeypatch, settings):
    FakeDDGS.calls, FakeDDGS.answers = [], {}
    monkeypatch.setattr(websearch, "DDGS", FakeDDGS)
    monkeypatch.setattr(websearch, "KeenableTools", FakeKeenable)
    return {f.__name__: f for f in websearch.make_web_tools(settings)}


def test_stops_at_first_engine_with_results(tools):
    FakeDDGS.answers = {"duckduckgo": [{"title": "a"}], "yahoo": [{"title": "b"}]}
    assert json.loads(tools["web_search"]("borsa")) == [{"title": "a"}]
    assert FakeDDGS.calls == [("text", "duckduckgo")]


def test_falls_through_engines_in_order(tools):
    FakeDDGS.answers = {"duckduckgo": TimeoutException("timed out"), "startpage": [{"title": "c"}]}
    assert json.loads(tools["web_search"]("borsa")) == [{"title": "c"}]
    assert FakeDDGS.calls == [("text", e) for e in ("duckduckgo", "keenable", "yahoo", "startpage")]


@pytest.mark.parametrize("answer", ["No results found.", "Keenable rate limit exceeded (429)",
                                    "Error performing search: timed out"])
def test_keenable_error_string_moves_to_next_engine(tools, answer):
    FakeDDGS.answers = {"duckduckgo": TimeoutException("x"), "keenable": answer, "yahoo": [{"title": "y"}]}
    assert json.loads(tools["web_search"]("borsa")) == [{"title": "y"}]
    assert [e for _, e in FakeDDGS.calls] == ["duckduckgo", "keenable", "yahoo"]


def test_keenable_results_stop_the_cascade(tools):
    FakeDDGS.answers = {"duckduckgo": TimeoutException("x"), "keenable": [{"title": "k"}], "yahoo": [{"title": "y"}]}
    assert json.loads(tools["web_search"]("borsa")) == [{"title": "k"}]
    assert [e for _, e in FakeDDGS.calls] == ["duckduckgo", "keenable"]


def _log(settings, engine, ok, age_s=0, n=1):
    with closing(sqlite3.connect(settings.database_file)) as c, c:
        c.execute("CREATE TABLE IF NOT EXISTS picobot_search_log(category TEXT, engine TEXT, ts REAL, ok INTEGER)")
        c.executemany("INSERT INTO picobot_search_log VALUES('text',?,?,?)", [(engine, time.time() - age_s, ok)] * n)


def test_engine_failing_recently_is_tried_last(tools, settings):
    _log(settings, "duckduckgo", 0, n=3)
    FakeDDGS.answers = {"duckduckgo": [{"title": "a"}], "keenable": [{"title": "k"}]}
    assert json.loads(tools["web_search"]("borsa")) == [{"title": "k"}]
    assert [e for _, e in FakeDDGS.calls] == ["keenable"]


def test_old_failures_do_not_count(tools, settings):
    _log(settings, "duckduckgo", 0, age_s=25 * 3600, n=3)
    FakeDDGS.answers = {"duckduckgo": [{"title": "a"}]}
    assert json.loads(tools["web_search"]("borsa")) == [{"title": "a"}]
    assert [e for _, e in FakeDDGS.calls] == ["duckduckgo"]


def test_attempts_are_logged(tools, settings):
    FakeDDGS.answers = {"duckduckgo": TimeoutException("x"), "keenable": [{"title": "k"}]}
    tools["web_search"]("borsa")
    with closing(sqlite3.connect(settings.database_file)) as c:
        assert dict(c.execute("SELECT engine, ok FROM picobot_search_log")) == {"duckduckgo": 0, "keenable": 1}


def test_news_has_its_own_engines(tools):
    FakeDDGS.answers = {"bing": [{"title": "n"}]}
    assert json.loads(tools["search_news"]("borsa")) == [{"title": "n"}]
    assert FakeDDGS.calls == [("news", "duckduckgo"), ("news", "bing")]


def test_no_results_anywhere_is_a_message_not_an_error(tools):
    out = tools["web_search"]("borsa")
    assert "Nessun risultato" in out
    assert [e for _, e in FakeDDGS.calls] == list(websearch.TEXT_ENGINES)
