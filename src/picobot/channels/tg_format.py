"""Markdown del modello nei formati di Telegram: Markdown legacy, MarkdownV2, HTML (più il testo semplice)."""
import re
from bisect import bisect_right
from dataclasses import dataclass
from itertools import accumulate, groupby
from types import SimpleNamespace

from markdown_it import MarkdownIt
from markdown_it.tree import SyntaxTreeNode
from telegram.error import BadRequest

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
            return self.pre("\n".join(_table(n)), "")
        return ""

    def lst(self, n, depth):
        return "\n".join(self.item(it, m, depth) for it, m in zip(n.children, _marks(n)))

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


def _marks(n) -> list[str]:
    """Segni delle voci di un elenco: "• " oppure il numero, che parte da start."""
    start = int(n.attrs.get("start", 1))
    return ["• " if n.type == "bullet_list" else f"{start + i}. " for i in range(len(n.children))]


def _table(n) -> list[str]:
    """Righe della tabella allineate a sinistra: celle senza marcatori, trattini sotto l'intestazione."""
    rows = [[PLAIN.inline(cell.children[0].children) for cell in tr.children] for sec in n.children for tr in sec.children]
    widths = [max(len(r[i]) for r in rows) for i in range(len(rows[0]))]
    rows.insert(1, ["-" * w for w in widths])
    return ["  ".join(c.ljust(w) for c, w in zip(r, widths)).rstrip() for r in rows]


def _render(f: _Plain, n) -> tuple[str, str]:
    """Coppia (testo formattato, testo semplice) di un blocco."""
    return f.block(n), PLAIN.block(n)


# Divisione. Una parte è (testo, semplice, separatore dalla parte prima); fits dice se un testo convertito sta nel
# limite, e i contenitori (citazione, voce) lo avvolgono con quello che aggiungono intorno.

def _join(g) -> tuple[str, str]:
    return tuple(g[0][i] + "".join(u[2] + u[i] for u in g[1:]) for i in (0, 1))


def _longest(lo, hi, ok) -> int:
    """Il k più grande in [lo, hi] con ok(k), dato ok monotono; lo vale comunque, così si va sempre avanti.
    Passi che raddoppiano finché ok regge: si provano gruppi poco più grandi del risultato."""
    step = 1
    while lo < hi:
        k = min(lo + step, hi)
        if ok(k):
            lo, step = k, step * 2
        else:
            hi, step = k - 1, max(step // 2, 1)
    return lo


def _pack(units, make, fits) -> list[tuple[str, str, str]]:
    """Unità raccolte avidamente: ogni parte è make(gruppo) e sta nel limite (ogni unità da sola ci sta già)."""
    parts, i = [], 0
    while i < len(units):
        j = _longest(i + 1, len(units), lambda j: fits(make(units[i:j])[0]))
        parts.append((*make(units[i:j]), "\n\n"))
        i = j
    return parts


def _cut(a, b, render, fits) -> list[tuple[int, int]]:
    """Ultima risorsa: il tratto [a, b) del testo grezzo in tratti il più lunghi possibile il cui convertito
    render(i, j) sta nel limite. Si taglia prima dell'escape, quindi mai dentro \\. o &amp;; almeno un carattere
    per tratto, così finisce sempre."""
    out = []
    while b - a > 1 and not fits(render(a, b)):
        k = _longest(a + 1, b - 1, lambda k: fits(render(a, k)))
        out.append((a, k))
        a = k
    return out + [(a, b)]


def _pre_parts(f, head, lines, lang, fits):
    """Blocco fisso diviso per righe: ogni parte è un blocco chiuso, con la stessa lingua e la stessa intestazione."""
    if not fits(f.pre("\n".join(head), lang)):   # intestazione più larga del limite: non si ripete
        head, lines = [], head + lines
    make = lambda g: (f.pre("\n".join(head + g), lang), "\n".join(head + g))
    units = [s[i:j] for s in lines for i, j in _cut(0, len(s), lambda i, j: make([s[i:j]])[0], fits)]
    return _pack(units, make, fits)


def _leaves(nodes, wraps=()) -> list:
    """Il contenuto in linea come foglie (involucri, tipo, testo grezzo), da tagliare in un punto qualsiasi."""
    out = []
    for n in nodes:
        if n.type in ("text", "code_inline"):
            out.append((wraps, n.type, n.content))
        elif n.type in ("softbreak", "hardbreak"):
            out.append((wraps, "text", "\n"))
        elif n.type == "image":
            out.append((wraps, "text", PLAIN.inline(n.children)))
        else:   # strong, em, s, link
            out += _leaves(n.children, wraps + ((n.type, n.attrs.get("href")),))
    return out


def _tree(leaves) -> list:
    """Foglie di nuovo in nodi: le consecutive con lo stesso involucro esterno stanno nello stesso nodo."""
    out = []
    for w, g in groupby(leaves, lambda l: l[0][:1]):
        g = list(g)
        if w:
            kids = _tree([(ws[1:], t, s) for ws, t, s in g])
            out.append(SimpleNamespace(type=w[0][0], attrs={"href": w[0][1]}, children=kids))
        else:
            out += [SimpleNamespace(type=t, content=s) for _, t, s in g]
    return out


def _inline_parts(f, nodes, wraps, fits):
    """Paragrafo o titolo diviso tra parole: ogni parte ricostruisce le sue entità, quindi un'entità tagliata si
    chiude prima del taglio e si riapre dopo."""
    leaves = _leaves(nodes, wraps)
    starts = list(accumulate((len(s) for _, _, s in leaves), initial=0))
    raw = "".join(s for _, _, s in leaves)

    def make(g):   # g: tratti (inizio, fine) consecutivi; la parte va dall'inizio del primo alla fine dell'ultimo
        a, b, part = g[0][0], g[-1][1], []
        for k in range(bisect_right(starts, a) - 1, len(leaves)):
            w, t, s = leaves[k]
            if (i := starts[k]) >= b:
                break
            if max(i, a) < min(i + len(s), b):
                part.append((w, t, s[max(a - i, 0):b - i]))
        kids = _tree(part)
        return f.inline(kids), PLAIN.inline(kids)

    words = [m.span() for m in re.finditer(r"\S+", raw)]
    return _pack([r for a, b in words for r in _cut(a, b, lambda i, j: make([(i, j)])[0], fits)], make, fits)


def _item_parts(f, it, mark, depth, fits):
    """Una voce intera se ci sta; se no i suoi blocchi divisi, con il segno solo sulla prima parte."""
    whole = f.item(it, mark, depth), PLAIN.item(it, mark, depth)
    if fits(whole[0]):
        return [(*whole, "\n")]
    pad, units = "  " * depth, []
    head = pad + f.esc(mark)
    ind = lambda s: s.replace("\n", "\n" + pad)
    for c in it.children:
        if c.type in _LISTS:
            units += [(t, p, "\n") for t, p, _ in _list_parts(f, c, depth + 1, lambda s: fits(head + s))]
        else:
            units += [(pad + ind(t), pad + ind(p), "\n") for t, p, _ in _parts(f, c, lambda s: fits(head + ind(s))) if t]
    (t, p, _), *rest = units
    return [(head + t.removeprefix(pad), pad + mark + p.removeprefix(pad), "\n"), *rest]


def _list_parts(f, n, depth, fits):
    """Elenco diviso tra le voci, con le parti unite da "\\n": la numerazione continua."""
    units = [u for it, m in zip(n.children, _marks(n)) for u in _item_parts(f, it, m, depth, fits)]
    return [(t, p, "\n" if k else "\n\n") for k, (t, p, _) in enumerate(units)]


def _parts(f, n, fits) -> list[tuple[str, str, str]]:
    """Parti di un blocco, ognuna con fits(testo): il blocco intero se ci sta, se no diviso secondo il suo tipo."""
    whole = _render(f, n)
    if fits(whole[0]):
        return [(*whole, "\n\n")]
    if n.type in _LISTS:
        return _list_parts(f, n, 0, fits)
    if n.type == "blockquote":   # ogni parte è una citazione completa
        units = [u for c in n.children for u in _parts(f, c, lambda s: fits(f.quote(s))) if u[0]]
        return _pack(units, lambda g: (f.quote((j := _join(g))[0]), j[1]), fits)
    if n.type in ("fence", "code_block"):
        return _pre_parts(f, [], n.content.removesuffix("\n").split("\n"), (n.info.split() or [""])[0], fits)
    if n.type == "table":   # intestazione e trattini ripetuti in ogni parte
        rows = _table(n)
        return _pre_parts(f, rows[:2], rows[2:], "", fits)
    # paragrafo o titolo (il titolo è tutto in grassetto)
    return _inline_parts(f, n.children[0].children, (("strong", None),) if n.type == "heading" else (), fits)


def render_chunks(md: str, fmt: str, limit: int = 4000) -> list[Chunk]:
    """Il Markdown del modello in pezzi convertiti: i blocchi di primo livello riempiono ogni pezzo fino al limite;
    un blocco più lungo del limite si divide prima in parti valide da sole."""
    f, fits = _FORMATS[fmt], lambda t: len(t) <= limit
    # fuori i blocchi senza testo (riga ---, titolo vuoto): il ripiego manderebbe un messaggio vuoto
    units = [u for n in SyntaxTreeNode(_MD.parse(md)).children if PLAIN.block(n).strip() for u in _parts(f, n, fits)]
    if not units:
        return [Chunk(f.esc(EMPTY), EMPTY)]
    return [Chunk(t, p) for t, p, _ in _pack(units, _join, fits)]


async def send_formatted(send, text: str, fmt: str) -> None:
    """send(testo, **kw) è una coroutine; se Telegram rifiuta la formattazione ripiega sul testo semplice."""
    for c in render_chunks(text, fmt):
        try:
            await send(c.text, parse_mode=PARSE_MODE[fmt])
        except BadRequest:
            await send(c.plain)
