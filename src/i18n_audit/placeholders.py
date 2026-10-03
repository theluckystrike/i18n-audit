"""Placeholder and tag extraction for each interpolation syntax.

Syntax ids:

* ``i18next``  ``{{x}}``, ``{{x, format}}``, ``{{- x}}``, ``$t(key)``
* ``icu``      ICU MessageFormat (react-intl, formatjs, Lingui, Tolgee, next-intl)
* ``vue``      vue-i18n ``{x}``, ``{0}``, ``@:linked.key``, literal ``{'x'}``
* ``rails``    ``%{x}`` and ``%<x>s``
* ``printf``   ``%s``, ``%d``, ``%1$s``, ``%@``, ``%(name)s``, ``%lld``
* ``brace``    Python ``str.format`` / gettext python-brace-format ``{x}``, ``{0}``
* ``javamf``   java.text.MessageFormat ``{0}`` plus printf
"""
from __future__ import annotations

import re
from collections import Counter
from typing import Dict, List, Set, Tuple

from . import icu

I18NEXT = re.compile(r"\{\{\s*-?\s*([^{}\s,]+)[^{}]*\}\}")
I18NEXT_NEST = re.compile(r"\$t\(\s*([^),]+)")
SINGLE = re.compile(r"(?<![{%$])\{\s*([A-Za-z_][\w.]*)\s*\}(?!\})")
SINGLE_INDEX = re.compile(r"(?<![{%$])\{\s*(\d+)\s*\}(?!\})")
RAILS = re.compile(r"%\{\s*([A-Za-z_]\w*)\s*\}")
RAILS_FMT = re.compile(r"%<([A-Za-z_]\w*)>[-+ #0]*\d*(?:\.\d+)?[sdifxXeEgGbBo]")
# printf incl. positional (%1$s), Objective-C (%@), length modifiers (%lld), named python (%(x)s)
PRINTF = re.compile(
    r"%(?:(\d+)\$|\(([A-Za-z_]\w*)\))?[-+ #0']*(?:\d+|\*)?(?:\.(?:\d+|\*))?"
    r"(?:hh|h|ll|l|L|q|j|z|t)?([sdiufFeEgGxXoaAcpS@])"
)
TEMPLATE = re.compile(r"\$\{\s*([A-Za-z_][\w.]*)\s*\}")
VUE_LINK = re.compile(r"@(?:\.[a-z]+)?:(?:\(([\w.-]+)\)|([\w.-]+))")
VUE_ARG = re.compile(r"(?<!\{)\{\s*([A-Za-z_]\w*|\d+)\s*\}(?!\})")
DOUBLE_UNDERSCORE = re.compile(r"__([A-Za-z][A-Za-z0-9_]*)__")

TAG = re.compile(r"<(/?)([A-Za-z0-9][\w.:-]*)((?:\s+[^<>]*?)?)\s*(/?)>")
VOID_TAGS = {"br", "hr", "img", "input", "wbr", "meta", "link"}

SYNTAXES = ("i18next", "icu", "vue", "rails", "printf", "brace", "javamf")


def strip_printf_escapes(s: str) -> str:
    return s.replace("%%", "")


def _printf_matches(s: str):
    """Yield (normalized token, original text). Positional args are keyed by
    position, sequential ones by order, so ``%s %d`` equals ``%2$d %1$s``."""
    seq = 0
    for m in PRINTF.finditer(s.replace("%%", "\0\0")):
        pos, name, conv = m.groups()
        if name:
            yield f"%({name})", m.group(0)
            continue
        # treat %d/%i/%u, %s/%@, %f/%e/%g as the same family so %lld vs %d is not noise
        fam = {"d": "d", "i": "d", "u": "d", "x": "d", "X": "d", "o": "d", "c": "c",
               "s": "s", "@": "s", "S": "s", "p": "p"}.get(conv, "f")
        if pos:
            yield f"%{pos}${fam}", m.group(0)
        else:
            seq += 1
            yield f"%{seq}${fam}", m.group(0)


def printf_tokens(s: str) -> Counter:
    return Counter(tok for tok, _ in _printf_matches(s))


def display(token: str, *texts: str) -> str:
    """How a normalized printf token is actually written in ``texts`` (``%1$s`` -> ``%@``)."""
    if token.startswith("%"):
        for t in texts:
            for tok, orig in _printf_matches(t):
                if tok == token:
                    return orig
    return token


def _icu_names(s: str, mode: str = "icu") -> Tuple[Set[str], Set[str]]:
    try:
        return icu.arguments(s, mode)
    except icu.ICUSyntaxError:
        return set(), set()


def tokens(s: str, syntax: str) -> Tuple[Set[str], Set[str]]:
    """Return (all placeholder tokens, tokens a translation must keep).

    Tokens are normalized strings like ``{{name}}``, ``{name}``, ``%{name}``
    or ``%1$s`` so they can be compared across source and translation.
    """
    if syntax == "icu":
        names, req = _icu_names(s)
        allt = {"{%s}" % x for x in names}
        reqt = {"{%s}" % x for x in req}
        return allt, reqt
    t: Set[str] = set()
    if syntax == "i18next":
        t |= {"{{%s}}" % x for x in I18NEXT.findall(s)}
        t |= {"$t(%s)" % x.strip().strip("'\"") for x in I18NEXT_NEST.findall(s)}
    elif syntax == "vue":
        clean = re.sub(r"\{\s*'[^']*'\s*\}", "", s)
        t |= {"{%s}" % x for x in VUE_ARG.findall(clean)}
        t |= {"@:%s" % (a or b) for a, b in VUE_LINK.findall(clean)}
    elif syntax == "rails":
        t |= {"%%{%s}" % x for x in RAILS.findall(s)}
        t |= {"%%<%s>" % x for x in RAILS_FMT.findall(s)}
    elif syntax == "printf":
        t |= set(printf_tokens(s))
    elif syntax == "brace":
        t |= {"{%s}" % x for x in re.findall(r"(?<!\{)\{\s*([A-Za-z_]\w*|\d+)(?:[!:][^{}]*)?\}(?!\})", s)}
        t |= set(printf_tokens(s))
    elif syntax == "javamf":
        names, _ = _icu_names(s, "java") if re.search(r"\{\s*\d", s) else (set(), set())
        t |= {"{%s}" % x for x in names}
        t |= set(printf_tokens(s))
    return t, t


def names(token: str) -> str:
    """Bare placeholder name of a normalized token."""
    m = re.match(r"^(?:\{\{|\{|%\{|%<|%\(|\$t\(|@:)?(.*?)(?:\}\}|\}|>|\)|)$", token)
    return m.group(1) if m else token


# Every way a placeholder named NAME may be written, used to spot a placeholder that
# survived translation but in the syntax of another library.
def any_syntax_names(s: str) -> Dict[str, str]:
    found: Dict[str, str] = {}
    for rx, fmt in (
        (I18NEXT, "{{%s}}"),
        (SINGLE, "{%s}"),
        (SINGLE_INDEX, "{%s}"),
        (RAILS, "%%{%s}"),
        (TEMPLATE, "${%s}"),
        (DOUBLE_UNDERSCORE, "__%s__"),
        (re.compile(r"%\(([A-Za-z_]\w*)\)"), "%%(%s)s"),
        (re.compile(r"\[\[\s*([A-Za-z_]\w*)\s*\]\]"), "[[%s]]"),
    ):
        for m in rx.finditer(s):
            found.setdefault(m.group(1), fmt % m.group(1))
    return found


def tags(s: str) -> Counter:
    """Multiset of opening, closing and self-closing tags, by name (attributes ignored)."""
    out = Counter()
    for m in TAG.finditer(s):
        closing, name, _, selfclose = m.groups()
        out["<%s%s%s>" % (closing, name, "/" if selfclose else "")] += 1
    return out


def unbalanced_tags(s: str) -> List[str]:
    """Tags opened but never closed or closed but never opened."""
    stack: List[str] = []
    bad: List[str] = []
    for m in TAG.finditer(s):
        closing, name, _, selfclose = m.groups()
        if selfclose or name.lower() in VOID_TAGS:
            continue
        if closing:
            if stack and stack[-1] == name:
                stack.pop()
            elif name in stack:
                while stack and stack[-1] != name:
                    bad.append("<%s>" % stack.pop())
                stack.pop()
            else:
                bad.append("</%s>" % name)
        else:
            stack.append(name)
    bad.extend("<%s>" % x for x in stack)
    return bad


def looks_like_markup(s: str) -> bool:
    return bool(TAG.search(s))
