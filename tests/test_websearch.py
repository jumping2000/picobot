"""Ricerca web a cascata: un motore alla volta, il successivo solo se il precedente non trova nulla."""

import json

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


@pytest.fixture
def tools(monkeypatch):
    FakeDDGS.calls, FakeDDGS.answers = [], {}
    monkeypatch.setattr(websearch, "DDGS", FakeDDGS)
    return {f.__name__: f for f in websearch.make_web_tools(Settings())}


def test_stops_at_first_engine_with_results(tools):
    FakeDDGS.answers = {"duckduckgo": [{"title": "a"}], "yahoo": [{"title": "b"}]}
    assert json.loads(tools["web_search"]("borsa")) == [{"title": "a"}]
    assert FakeDDGS.calls == [("text", "duckduckgo")]


def test_falls_through_engines_in_order(tools):
    FakeDDGS.answers = {"duckduckgo": TimeoutException("timed out"), "startpage": [{"title": "c"}]}
    assert json.loads(tools["web_search"]("borsa")) == [{"title": "c"}]
    assert FakeDDGS.calls == [("text", e) for e in ("duckduckgo", "yahoo", "startpage")]


def test_news_has_its_own_engines(tools):
    FakeDDGS.answers = {"bing": [{"title": "n"}]}
    assert json.loads(tools["search_news"]("borsa")) == [{"title": "n"}]
    assert FakeDDGS.calls == [("news", "duckduckgo"), ("news", "bing")]


def test_no_results_anywhere_is_a_message_not_an_error(tools):
    out = tools["web_search"]("borsa")
    assert "Nessun risultato" in out
    assert [e for _, e in FakeDDGS.calls] == list(websearch.TEXT_ENGINES)
