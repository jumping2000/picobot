"""Conversione del Markdown del modello nei tre formati di Telegram (markdown, markdownv2, html)."""
import asyncio
import re

import pytest
from telegram.error import BadRequest

from picobot.channels.tg_format import Chunk, render_chunks, send_formatted


def one(md: str, fmt: str) -> Chunk:
    chunks = render_chunks(md, fmt)
    assert len(chunks) == 1, chunks
    return chunks[0]


T = "Nome   Età  Città\n-----  ---  -----\nMarco  30   Roma"
USER_TABLE = "| Nome | Età | Città |\n| --- | --- | --- |\n| Marco | 30 | Roma |"

CASES = [  # (markdown del modello, markdown legacy, markdownv2, html, plain)
    ("**ciao** mondo", "*ciao* mondo", "*ciao* mondo", "<b>ciao</b> mondo", "ciao mondo"),
    ("*x*", "_x_", "_x_", "<i>x</i>", "x"),
    ("~~x~~", "x", "~x~", "<s>x</s>", "x"),
    ("`a_b`", "`a_b`", "`a_b`", "<code>a_b</code>", "a_b"),
    ("```python\nprint(1)\n```", "```\nprint(1)\n```", "```python\nprint(1)\n```",
     '<pre><code class="language-python">print(1)</code></pre>', "print(1)"),
    ("[sito](https://example.com)", "[sito](https://example.com)", "[sito](https://example.com)",
     '<a href="https://example.com">sito</a>', "sito (https://example.com)"),
    ("# Titolo", "*Titolo*", "*Titolo*", "<b>Titolo</b>", "Titolo"),
    ("## **Titolo**", "*Titolo*", "*Titolo*", "<b>Titolo</b>", "Titolo"),
    ("**a **b** c**", "*a b c*", "*a b c*", "<b>a b c</b>", "a b c"),
    ("- a\n- b", "• a\n• b", "• a\n• b", "• a\n• b", "• a\n• b"),
    ("1. a\n2. b", "1. a\n2. b", "1\\. a\n2\\. b", "1. a\n2. b", "1. a\n2. b"),
    ("- a\n  - b", "• a\n  • b", "• a\n  • b", "• a\n  • b", "• a\n  • b"),
    ("> cit", "cit", ">cit", "<blockquote>cit</blockquote>", "cit"),
    ("a\n\n---\n\nb", "a\n\nb", "a\n\nb", "a\n\nb", "a\n\nb"),
    ("riga1\nriga2", "riga1\nriga2", "riga1\nriga2", "riga1\nriga2", "riga1\nriga2"),
    (USER_TABLE, f"```\n{T}\n```", f"```\n{T}\n```", f"<pre>{T}</pre>", T),
]


@pytest.mark.parametrize("md,legacy,v2,html,plain", CASES)
def test_conversion(md, legacy, v2, html, plain):
    for fmt, want in (("markdown", legacy), ("markdownv2", v2), ("html", html)):
        c = one(md, fmt)
        assert (c.text, c.plain) == (want, plain), fmt


def test_v2_escapes_prose():                      # Review Focus 1
    assert one("Costa 3.5€ (circa) - ok!", "markdownv2").text == "Costa 3\\.5€ \\(circa\\) \\- ok\\!"


def test_html_escapes():
    assert one("a < b & c", "html").text == "a &lt; b &amp; c"


def test_legacy_escapes_lonely_specials():
    assert one("nome_utente e 2*3", "markdown").text == "nome\\_utente e 2\\*3"


def test_legacy_special_inside_entity():          # Review Focus 2
    assert one("**snake_case**", "markdown").text == "*snake*\\_*case*"


def test_legacy_no_nested_entities():
    assert one("**a *b* c**", "markdown").text == "*a b c*"


def test_raw_html_is_text():                      # Review Focus 5
    assert one("<b>x</b>", "html").text == "&lt;b&gt;x&lt;/b&gt;"
    assert one("<b>x</b>", "markdownv2").text == "<b\\>x</b\\>"


def test_table_cells_lose_markup():
    c = one("| **A** | b |\n|---|---|\n| `1` | 2 |", "html")
    assert c.text == "<pre>A  b\n-  -\n1  2</pre>"


def test_empty_text():
    [c] = render_chunks("", "markdownv2")
    assert (c.text, c.plain) == ("\\(risposta vuota\\)", "(risposta vuota)")


def test_blocks_without_text_are_skipped():
    assert render_chunks("#", "html") == render_chunks("", "html")
    assert render_chunks("a\n\n#\n\nb", "html")[0].text == "a\n\nb"


def test_small_blocks_share_one_message():
    md = "\n\n".join(f"paragrafo {i} " + "x" * 80 for i in range(10))
    assert len(render_chunks(md, "html")) == 1


def balanced(text: str, fmt: str) -> bool:
    """Nessun blocco ``` aperto (markdown, markdownv2); in html tanti tag aperti quanti chiusi."""
    if fmt == "html":
        return all(len(re.findall(rf"<{t}[ >]", text)) == text.count(f"</{t}>")
                   for t in ("pre", "b", "i", "s", "code", "a", "blockquote"))
    return text.count("```") % 2 == 0


FMTS = ("markdown", "markdownv2", "html")
LONG = {
    "paragrafo": "parola " * 1500,
    "elenco": "\n".join(f"{i}. voce numero {i}" for i in range(1, 400)),
    "tabella": "| a | b |\n|---|---|\n" + "\n".join(f"| riga {i} | {i * 7} |" for i in range(600)),
    "codice": "```python\n" + "\n".join(f"print({i})  # (riga)" for i in range(600)) + "\n```",
    "citazione": "\n>\n".join(f"> paragrafo {i} " + "y" * 60 for i in range(120)),
    "grassetto": "**" + ("lungo " * 1000).strip() + "**",   # niente spazio prima di ** o non è grassetto
}


@pytest.mark.parametrize("fmt", FMTS)
@pytest.mark.parametrize("kind", LONG)
def test_long_blocks_split_within_limit(kind, fmt):
    chunks = render_chunks(LONG[kind], fmt)
    assert len(chunks) > 1
    assert all(len(c.text) <= 4000 and balanced(c.text, fmt) for c in chunks)


def test_long_table_repeats_header():
    for c in render_chunks(LONG["tabella"], "html"):
        assert c.text.startswith("<pre>a" + " " * 9 + "b\n")


def test_long_numbered_list_keeps_counting():
    second = render_chunks(LONG["elenco"], "markdown")[1].plain
    assert not second.startswith("1. ") and second.split(". ")[0].isdigit()


@pytest.mark.parametrize("fmt", FMTS)
def test_overlong_word_is_hard_cut(fmt):           # Review Focus 3
    chunks = render_chunks("https://example.com/" + "a.b-" * 2000, fmt)
    assert all(len(c.text) <= 4000 for c in chunks)
    assert "".join(c.plain for c in chunks).count("a.b-") == 2000


def test_send_formatted_uses_parse_mode_then_plain():
    calls = []
    async def send(text, **kw):
        calls.append((text, kw.get("parse_mode")))
        if kw.get("parse_mode"): raise BadRequest("can't parse entities")
    asyncio.run(send_formatted(send, "**ciao**", "html"))
    assert calls == [("<b>ciao</b>", "HTML"), ("ciao", None)]


def test_legacy_link_url_parentheses_are_percent_encoded():
    assert one("[Euro](https://it.wikipedia.org/wiki/Euro_(valuta))", "markdown").text == \
        "[Euro](https://it.wikipedia.org/wiki/Euro_%28valuta%29)"


def test_markdownv2_link_url_escapes_closing_parenthesis():
    assert one("[a](https://x.org/a_(b))", "markdownv2").text == r"[a](https://x.org/a_(b\))"


def test_html_attribute_escapes_quotes():   # markdown-it codifica già " negli URL: si prova con la lingua del blocco
    assert one('```a"b\nx\n```', "html").text == '<pre><code class="language-a&quot;b">x</code></pre>'


def utf16(t: str) -> int:
    return len(t.encode("utf-16-le")) // 2


@pytest.mark.parametrize("fmt", FMTS)
def test_chunks_fit_limit_in_utf16_units(fmt):
    md = "\n".join(f"- 📈 ENI 14,52€ (+1,3%) 🟢 riga {i}" for i in range(400))
    chunks = render_chunks(md, fmt)
    assert len(chunks) > 1
    assert all(utf16(c.text) <= 4000 for c in chunks)


def test_send_formatted_falls_back_to_plain_pieces_if_converter_raises(monkeypatch):
    from picobot.channels import tg_format
    def boom(*a, **kw): raise RuntimeError("bug")
    monkeypatch.setattr(tg_format, "render_chunks", boom)
    calls = []
    async def send(text, **kw): calls.append((text, kw))
    asyncio.run(send_formatted(send, "**ciao**", "html"))
    assert calls == [("**ciao**", {})]
