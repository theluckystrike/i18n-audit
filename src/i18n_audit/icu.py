"""A small ICU MessageFormat parser.

Covers what translation catalogs use in practice: simple arguments ``{x}``,
formatted arguments ``{x, number, ::currency/EUR}``, ``plural``,
``selectordinal`` and ``select`` with nested messages, ``offset:``, ``#`` and
apostrophe quoting.

Two apostrophe modes are supported:

* ``icu`` (ICU4J / formatjs default, DOUBLE_OPTIONAL): an apostrophe only starts
  quoted text when it is followed by ``{``, ``}`` (or ``#`` / ``|`` inside a
  plural). ``''`` is a literal apostrophe. Any other apostrophe is literal.
* ``java`` (java.text.MessageFormat, DOUBLE_REQUIRED): every single apostrophe
  starts or ends quoted text, so ``l'utente {0}`` renders ``{0}`` literally.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Union

PLURAL_CATEGORIES = ("zero", "one", "two", "few", "many", "other")
SIMPLE_TYPES = ("number", "date", "time", "spellout", "ordinal", "duration", "list")
COMPLEX_TYPES = ("plural", "selectordinal", "select")
JAVA_TYPES = ("choice",)

_WS = re.compile(r"\s*")
# ICU Pattern_White_Space / Pattern_Syntax are excluded from names; this is close enough.
_NAME = re.compile(r"[^\s{}#,'\"=<>|:;!?~`^&*()\[\]\\/+@%$]+")
_KEYWORD = re.compile(r"[A-Za-z][A-Za-z0-9_-]*")
_EXPLICIT = re.compile(r"=\s*-?\d+(?:\.\d+)?")
_OFFSET = re.compile(r"offset\s*:\s*(-?\d+)")


class ICUSyntaxError(ValueError):
    def __init__(self, message: str, offset: int):
        super().__init__(f"{message} (at offset {offset})")
        self.reason = message
        self.offset = offset


@dataclass
class Text:
    value: str


@dataclass
class Pound:
    pass


@dataclass
class Argument:
    name: str
    type: Optional[str] = None
    style: Optional[str] = None
    offset: int = 0
    options: Dict[str, List["Node"]] = field(default_factory=dict)


Node = Union[Text, Pound, Argument]


class _Parser:
    def __init__(self, s: str, mode: str):
        self.s = s
        self.n = len(s)
        self.mode = mode

    def ws(self, i: int) -> int:
        return _WS.match(self.s, i).end()

    def error(self, msg: str, i: int):
        raise ICUSyntaxError(msg, i)

    # message := (text | '#' | argument)*   ends at '}' when nested
    def message(self, i: int, depth: int, in_plural: bool) -> tuple:
        s, n = self.s, self.n
        nodes: List[Node] = []
        buf: List[str] = []

        def flush():
            if buf:
                nodes.append(Text("".join(buf)))
                buf.clear()

        while i < n:
            c = s[i]
            if c == "'":
                i = self.apostrophe(i, buf, in_plural)
                continue
            if c == "{":
                flush()
                node, i = self.argument(i + 1)
                nodes.append(node)
                continue
            if c == "}":
                if depth == 0:
                    self.error("unmatched closing brace", i)
                flush()
                return nodes, i
            if c == "#" and in_plural:
                flush()
                nodes.append(Pound())
                i += 1
                continue
            buf.append(c)
            i += 1
        if depth > 0:
            self.error("unclosed plural/select option", n)
        flush()
        return nodes, i

    def apostrophe(self, i: int, buf: List[str], in_plural: bool) -> int:
        s, n = self.s, self.n
        nxt = s[i + 1] if i + 1 < n else ""
        if nxt == "'":
            buf.append("'")
            return i + 2
        if self.mode == "icu":
            special = "{}" + ("#|" if in_plural else "")
            if not nxt or nxt not in special:
                buf.append("'")
                return i + 1
        # quoted literal until the next lone apostrophe (or end of string)
        i += 1
        while i < n:
            if s[i] == "'":
                if i + 1 < n and s[i + 1] == "'":
                    buf.append("'")
                    i += 2
                    continue
                return i + 1
            buf.append(s[i])
            i += 1
        return n

    def argument(self, i: int) -> tuple:
        s = self.s
        start = i - 1
        i = self.ws(i)
        if i >= self.n:
            self.error("unclosed argument", start)
        if s[i] == "}":
            self.error("empty argument", start)
        m = _NAME.match(s, i)
        if not m:
            self.error("malformed argument name", i)
        name = m.group(0)
        i = self.ws(m.end())
        if i >= self.n:
            self.error("unclosed argument", start)
        if s[i] == "}":
            return Argument(name), i + 1
        if s[i] != ",":
            self.error(f"unexpected character {s[i]!r} in argument {name!r}", i)
        i = self.ws(i + 1)
        m = _KEYWORD.match(s, i)
        if not m:
            self.error(f"missing argument type for {name!r}", i)
        typ = m.group(0)
        i = self.ws(m.end())
        if typ in COMPLEX_TYPES:
            return self.complex(name, typ, i, start)
        if typ in SIMPLE_TYPES or (self.mode == "java" and typ in JAVA_TYPES):
            if i < self.n and s[i] == "}":
                return Argument(name, typ), i + 1
            if i >= self.n or s[i] != ",":
                self.error(f"expected ',' or '}}' after type {typ!r}", i)
            style, i = self.style(i + 1, start)
            return Argument(name, typ, style.strip()), i
        self.error(f"invalid argument type {typ!r}", m.start())

    def style(self, i: int, start: int) -> tuple:
        """Raw style text up to the matching closing brace."""
        s, n = self.s, self.n
        depth = 0
        out = []
        while i < n:
            c = s[i]
            if c == "'":
                j = s.find("'", i + 1)
                if j < 0:
                    self.error("unterminated quote in argument style", i)
                out.append(s[i:j + 1])
                i = j + 1
                continue
            if c == "{":
                depth += 1
            elif c == "}":
                if depth == 0:
                    return "".join(out), i + 1
                depth -= 1
            out.append(c)
            i += 1
        self.error("unclosed argument", start)

    def complex(self, name: str, typ: str, i: int, start: int) -> tuple:
        s, n = self.s, self.n
        if i >= n or s[i] != ",":
            self.error(f"expected ',' after {typ!r}", i)
        i = self.ws(i + 1)
        arg = Argument(name, typ)
        if typ != "select":
            m = _OFFSET.match(s, i)
            if m:
                arg.offset = int(m.group(1))
                i = self.ws(m.end())
        while True:
            if i >= n:
                self.error(f"unclosed {typ} argument {name!r}", start)
            if s[i] == "}":
                i += 1
                break
            if typ != "select":
                m = _EXPLICIT.match(s, i) or _KEYWORD.match(s, i)
            else:
                m = _NAME.match(s, i)
            if not m:
                self.error(f"invalid {typ} selector", i)
            sel = re.sub(r"\s+", "", m.group(0))
            if sel in arg.options:
                self.error(f"duplicate selector {sel!r} in {name!r}", m.start())
            i = self.ws(m.end())
            if i >= n or s[i] != "{":
                self.error(f"expected '{{' after selector {sel!r}", i)
            nodes, i = self.message(i + 1, 1, typ != "select")
            arg.options[sel] = nodes
            i = self.ws(i + 1)
        if not arg.options:
            self.error(f"{typ} argument {name!r} has no options", start)
        if "other" not in arg.options:
            self.error(f"{typ} argument {name!r} is missing the required 'other' option", start)
        return arg, i


def parse(message: str, mode: str = "icu") -> List[Node]:
    """Parse an ICU message. Raises ICUSyntaxError."""
    nodes, _ = _Parser(message, mode).message(0, 0, False)
    return nodes


def is_valid(message: str, mode: str = "icu") -> bool:
    try:
        parse(message, mode)
        return True
    except ICUSyntaxError:
        return False


def walk(nodes: List[Node], required: bool = True, branch: str = ""):
    """Yield (Argument, required) for every argument.

    An argument is "required" when it appears outside any plural branch other
    than ``other`` (so a translation must keep it); ``one {# item}`` style
    branches may legitimately drop arguments in other languages.
    """
    for node in nodes:
        if isinstance(node, Argument):
            yield node, required
            for sel, sub in node.options.items():
                sub_required = required
                if node.type in ("plural", "selectordinal") and sel != "other":
                    sub_required = False
                yield from walk(sub, sub_required, sel)


def arguments(message: str, mode: str = "icu"):
    """Return (all argument names, required argument names). Raises ICUSyntaxError."""
    names, req = set(), set()
    for arg, required in walk(parse(message, mode)):
        names.add(arg.name)
        if required:
            req.add(arg.name)
    return names, req


def unknown_plural_selectors(message: str, mode: str = "icu") -> List[str]:
    """Plural selectors that are neither CLDR categories nor =N (often translated by mistake)."""
    out = []
    for arg, _ in walk(parse(message, mode)):
        if arg.type in ("plural", "selectordinal"):
            out.extend(s for s in arg.options if not s.startswith("=") and s not in PLURAL_CATEGORIES)
    return out


def literal_braces(message: str, mode: str = "icu") -> List[str]:
    """Names that appear as ``{name}`` inside quoted (literal) text.

    ``'{count}'`` is valid ICU but renders the text "{count}" verbatim, which is
    almost always a translator escaping by accident.
    """
    out = []

    def visit(nodes):
        for node in nodes:
            if isinstance(node, Text):
                out.extend(re.findall(r"\{\s*([\w.]+)\s*[,}]", node.value))
            elif isinstance(node, Argument):
                for sub in node.options.values():
                    visit(sub)

    visit(parse(message, mode))
    return out
