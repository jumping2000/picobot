"""Markdown del modello nei formati di Telegram: Markdown legacy, MarkdownV2, HTML (più il testo semplice)."""
import re
from dataclasses import dataclass

from markdown_it import MarkdownIt
from markdown_it.tree import SyntaxTreeNode

PARSE_MODE = {"markdown": "Markdown", "markdownv2": "MarkdownV2", "html": "HTML"}
EMPTY = "(risposta vuota)"
_MD = MarkdownIt("commonmark", {"html": False}).enable(["table", "strikethrough"])
_LISTS = ("bullet_list", "ordered_list")
_LEGACY_SPECIAL = re.compile(r"([_*`\[])")
_V2_SPECIAL = re.compile(r"([_*\[\]()~`>#+\-=|{}.!\\])")
_V2_CODE = re.compile(r"([`\\])")
_V2_URL = re.compile(r"([)\\])")


@dataclass(frozen=True)
class Chunk:
    text: str   # testo formattato, da mandare con parse_mode
    plain: str  # lo stesso testo senza marcatori, per il ripiego


class _Plain:
    """Scrittore senza marcatori. Le modalità ridefiniscono escape e marcatori; i blocchi si rendono uno per uno."""
    TAGS = {"strong": ("", ""), "em": ("", ""), "s": ("", "")}

    def esc(self, s):
        return s

    def code(self, s):
        return s

    def link(self, kids, url, bold=False):
        return f"{self.inline(kids, bold)} ({url})"

    def pre(self, s, lang):
        return s

    def quote(self, s):
        return s

    def wrap(self, kind, kids, bold=False):
        if kind == "strong" and bold:   # già in grassetto (titolo o grassetto esterno): niente grassetto annidato
            return self.inline(kids, True)
        o, c = self.TAGS[kind]
        return o + self.inline(kids, bold or kind == "strong") + c

    def inline(self, nodes, bold=False):
        return "".join(self.span(n, bold) for n in nodes)

    def span(self, n, bold=False):
        if n.type == "text":
            return self.esc(n.content)
        if n.type in ("softbreak", "hardbreak"):
            return "\n"
        if n.type == "code_inline":
            return self.code(n.content)
        if n.type == "image":      # solo il testo alternativo
            return self.esc(PLAIN.inline(n.children))
        if n.type == "link":
            return self.link(n.children, n.attrs["href"], bold)
        return self.wrap(n.type, n.children, bold)   # strong, em, s

    def block(self, n):
        """Testo di un blocco; "" per quelli che non producono niente (riga ---)."""
        t = n.type
        if t == "paragraph":
            return self.inline(n.children[0].children)
        if t == "heading":
            return self.wrap("strong", n.children[0].children)
        if t in _LISTS:
            return self.lst(n, 0)
        if t == "blockquote":
            return self.quote("\n\n".join(b for b in map(self.block, n.children) if b))
        if t in ("fence", "code_block"):
            return self.pre(n.content.removesuffix("\n"), (n.info.split() or [""])[0])
        if t == "table":
            return self.pre(_table(n), "")
        return ""

    def lst(self, n, depth):
        start = int(n.attrs.get("start", 1))
        return "\n".join(self.item(it, "• " if n.type == "bullet_list" else f"{start + i}. ", depth)
                         for i, it in enumerate(n.children))

    def item(self, n, mark, depth):
        """Una voce: i blocchi interni a capo con il rientro della voce, gli elenchi annidati 2 spazi più in là."""
        pad, parts = "  " * depth, []
        for c in n.children:
            if c.type in _LISTS:
                parts.append(self.lst(c, depth + 1))
            elif text := self.block(c):
                parts.append(pad + text.replace("\n", "\n" + pad))
        return pad + self.esc(mark) + "\n".join(parts).removeprefix(pad)


class _Legacy(_Plain):
    """Markdown legacy: escape solo fuori dalle entità, entità non annidate."""
    TAGS = {"strong": ("*", "*"), "em": ("_", "_"), "s": ("", "")}

    def esc(self, s):
        return _LEGACY_SPECIAL.sub(r"\\\1", s)

    def ent(self, o, c, s):
        # dentro un'entità niente escape: un carattere speciale la chiude, si scrive con escape e l'entità riapre
        return "".join(self.esc(p) if i % 2 else p and o + p + c for i, p in enumerate(_LEGACY_SPECIAL.split(s)))

    def wrap(self, kind, kids, bold=False):
        return self.ent(*self.TAGS[kind], PLAIN.inline(kids))

    def code(self, s):
        return self.esc(s) if "`" in s else f"`{s}`"

    def link(self, kids, url, bold=False):
        return self.ent("[", f"]({url})", PLAIN.inline(kids))

    def pre(self, s, lang):
        return f"```\n{s}\n```"


class _V2(_Plain):
    TAGS = {"strong": ("*", "*"), "em": ("_", "_"), "s": ("~", "~")}

    def esc(self, s):
        return _V2_SPECIAL.sub(r"\\\1", s)

    def code(self, s):
        return f"`{_V2_CODE.sub(r'\\\1', s)}`"

    def link(self, kids, url, bold=False):
        return f"[{self.inline(kids, bold)}]({_V2_URL.sub(r'\\\1', url)})"

    def pre(self, s, lang):
        return f"```{lang}\n{_V2_CODE.sub(r'\\\1', s)}\n```"

    def quote(self, s):
        return "\n".join(">" + line for line in s.split("\n"))


class _Html(_Plain):
    TAGS = {"strong": ("<b>", "</b>"), "em": ("<i>", "</i>"), "s": ("<s>", "</s>")}

    def esc(self, s):
        return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    def attr(self, s):
        return self.esc(s).replace('"', "&quot;")

    def code(self, s):
        return f"<code>{self.esc(s)}</code>"

    def link(self, kids, url, bold=False):
        return f'<a href="{self.attr(url)}">{self.inline(kids, bold)}</a>'

    def pre(self, s, lang):
        s = self.esc(s)
        return f'<pre><code class="language-{self.attr(lang)}">{s}</code></pre>' if lang else f"<pre>{s}</pre>"

    def quote(self, s):
        return f"<blockquote>{s}</blockquote>"


PLAIN = _Plain()
_FORMATS = {"markdown": _Legacy(), "markdownv2": _V2(), "html": _Html()}


def _table(n) -> str:
    """Tabella come testo allineato a sinistra: celle senza marcatori, trattini sotto l'intestazione."""
    rows = [[PLAIN.inline(cell.children[0].children) for cell in tr.children] for sec in n.children for tr in sec.children]
    widths = [max(len(r[i]) for r in rows) for i in range(len(rows[0]))]
    rows.insert(1, ["-" * w for w in widths])
    return "\n".join("  ".join(c.ljust(w) for c, w in zip(r, widths)).rstrip() for r in rows)


def _render(f: _Plain, n) -> tuple[str, str]:
    """Coppia (testo formattato, testo semplice) di un blocco."""
    return f.block(n), PLAIN.block(n)


def render_chunks(md: str, fmt: str, limit: int = 4000) -> list[Chunk]:
    """Il Markdown del modello in pezzi convertiti: i blocchi di primo livello riempiono ogni pezzo fino al limite."""
    f = _FORMATS[fmt]
    # fuori i blocchi senza testo (riga ---, titolo vuoto): il ripiego manderebbe un messaggio vuoto
    blocks = [p for n in SyntaxTreeNode(_MD.parse(md)).children if (p := _render(f, n))[1].strip()]
    if not blocks:
        return [Chunk(f.esc(EMPTY), EMPTY)]
    chunks = [Chunk(*blocks[0])]
    for text, plain in blocks[1:]:
        last = chunks[-1]
        if len(last.text) + 2 + len(text) <= limit:
            chunks[-1] = Chunk(f"{last.text}\n\n{text}", f"{last.plain}\n\n{plain}")
        else:
            chunks.append(Chunk(text, plain))
    return chunks
