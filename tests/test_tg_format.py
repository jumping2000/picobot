"""Conversione del Markdown del modello nei tre formati di Telegram (markdown, markdownv2, html)."""
import pytest

from picobot.channels.tg_format import Chunk, render_chunks


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
