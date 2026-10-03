"""JSON catalogs (i18next nested/flat, formatjs/react-intl, vue-i18n, next-intl, ...).

The stdlib json module neither reports line numbers nor duplicate keys, so this
is a small strict JSON parser that does both.
"""
from __future__ import annotations

import bisect
import re
from typing import List, Tuple

from ..model import Catalog, Entry

_STRING = re.compile(r'"((?:[^"\\\x00-\x1f]|\\.)*)"', re.S)
_NUMBER = re.compile(r"-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?")
_WS = re.compile(r"[ \t\r\n]*")
_ESC = {'"': '"', "\\": "\\", "/": "/", "b": "\b", "f": "\f", "n": "\n", "r": "\r", "t": "\t"}


class JSONError(ValueError):
    def __init__(self, msg: str, line: int):
        super().__init__(f"{msg} (line {line})")
        self.line = line


def _unescape(raw: str, line: int) -> str:
    if "\\" not in raw:
        return raw
    out = []
    i = 0
    while i < len(raw):
        c = raw[i]
        if c != "\\":
            out.append(c)
            i += 1
            continue
        e = raw[i + 1]
        if e == "u":
            code = int(raw[i + 2:i + 6], 16)
            i += 6
            if 0xD800 <= code < 0xDC00 and raw[i:i + 2] == "\\u":
                low = int(raw[i + 2:i + 6], 16)
                if 0xDC00 <= low < 0xE000:
                    code = 0x10000 + ((code - 0xD800) << 10) + (low - 0xDC00)
                    i += 6
            out.append(chr(code))
            continue
        if e not in _ESC:
            raise JSONError(f"invalid escape \\{e}", line)
        out.append(_ESC[e])
        i += 2
    return "".join(out)


class _Parser:
    """Yields (path, value, line, depth) for every scalar, and duplicates."""

    def __init__(self, text: str):
        self.s = text
        self.leaves: List[Tuple[List[str], object, int]] = []
        self.dups: List[Tuple[List[str], int]] = []
        self.newlines = [m.start() for m in re.finditer("\n", text)]

    def line(self, i: int) -> int:
        return bisect.bisect_left(self.newlines, i) + 1

    def ws(self, i: int) -> int:
        return _WS.match(self.s, i).end()

    def value(self, i: int, path: List[str]) -> int:
        s = self.s
        i = self.ws(i)
        if i >= len(s):
            raise JSONError("unexpected end of file", self.line(i))
        c = s[i]
        if c == "{":
            return self.obj(i + 1, path)
        if c == "[":
            return self.arr(i + 1, path)
        if c == '"':
            m = _STRING.match(s, i)
            if not m:
                raise JSONError("unterminated string", self.line(i))
            ln = self.line(i)
            self.leaves.append((path, _unescape(m.group(1), ln), ln))
            return m.end()
        for lit, val in (("true", True), ("false", False), ("null", None)):
            if s.startswith(lit, i):
                self.leaves.append((path, val, self.line(i)))
                return i + len(lit)
        m = _NUMBER.match(s, i)
        if m and m.end() > i:
            self.leaves.append((path, m.group(0), self.line(i)))
            return m.end()
        raise JSONError(f"unexpected character {c!r}", self.line(i))

    def obj(self, i: int, path: List[str]) -> int:
        s = self.s
        seen = set()
        i = self.ws(i)
        if i < len(s) and s[i] == "}":
            return i + 1
        while True:
            i = self.ws(i)
            m = _STRING.match(s, i)
            if not m:
                raise JSONError("expected a string key", self.line(i))
            key = _unescape(m.group(1), self.line(i))
            if key in seen:
                self.dups.append((path + [key], self.line(i)))
            seen.add(key)
            i = self.ws(m.end())
            if i >= len(s) or s[i] != ":":
                raise JSONError("expected ':'", self.line(i))
            i = self.value(i + 1, path + [key])
            i = self.ws(i)
            if i < len(s) and s[i] == ",":
                i += 1
                continue
            if i < len(s) and s[i] == "}":
                return i + 1
            raise JSONError("expected ',' or '}'", self.line(i))

    def arr(self, i: int, path: List[str]) -> int:
        s = self.s
        i = self.ws(i)
        if i < len(s) and s[i] == "]":
            return i + 1
        idx = 0
        while True:
            i = self.value(i, path + [str(idx)])
            idx += 1
            i = self.ws(i)
            if i < len(s) and s[i] == ",":
                i += 1
                continue
            if i < len(s) and s[i] == "]":
                return i + 1
            raise JSONError("expected ',' or ']'", self.line(i))

    def parse(self):
        text = self.s
        start = 1 if text.startswith("﻿") else 0
        end = self.value(start, [])
        if self.ws(end) != len(text):
            raise JSONError("trailing data", self.line(end))
        return self


def parse_json(text: str):
    return _Parser(text).parse()


def load(path: str, rel: str, locale: str, text: str = None) -> Catalog:
    cat = Catalog(rel, locale, "json")
    if text is None:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    try:
        p = parse_json(text)
    except JSONError as e:
        cat.errors.append((e.line, str(e)))
        return cat
    for pth, ln in p.dups:
        cat.duplicates.append(Entry(".".join(pth), "", ln, {"top_level": len(pth) == 1}))
    # formatjs extracted format: {"key": {"defaultMessage": "..", "description": ".."}}
    # and Chrome extension format: {"key": {"message": "..", "description": ".."}}
    children = {}
    for pth, _, _ in p.leaves:
        if len(pth) >= 2:
            children.setdefault(tuple(pth[:-1]), set()).add(pth[-1])
    wrapped = {k for k, v in children.items()
               if "defaultMessage" in v or ("message" in v and "description" in v)}
    for pth, val, ln in p.leaves:
        if not isinstance(val, str) or not pth or pth[0] in ("$schema", "@metadata"):
            continue
        parent = tuple(pth[:-1])
        if parent in wrapped:
            if pth[-1] not in ("defaultMessage", "message"):
                continue
            key = ".".join(parent)
        else:
            key = ".".join(pth)
        cat.entries[key] = Entry(key, val, ln)
    return cat
