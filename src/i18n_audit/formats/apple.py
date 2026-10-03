"""Apple ``*.lproj/*.strings`` files (``"key" = "value";``)."""
from __future__ import annotations

import re

from ..model import Catalog, Entry

_TOKEN = re.compile(
    r'\s+|/\*.*?\*/|//[^\n]*|"((?:[^"\\]|\\.)*)"|([A-Za-z0-9_.\-$:/]+)|(=)|(;)|(.)', re.S
)


def _unescape(s: str) -> str:
    def rep(m):
        e = m.group(1)
        if e[0] in "uU":
            return chr(int(e[1:], 16))
        return {"n": "\n", "t": "\t", "r": "\r", "0": "\0"}.get(e, e)

    return re.sub(r"\\([uU][0-9a-fA-F]{4}|.)", rep, s)


def _decode(data: bytes) -> str:
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16")
    if len(data) > 1 and data[1:2] == b"\x00":
        return data.decode("utf-16-le")
    return data.decode("utf-8-sig")


def load(path: str, rel: str, locale: str) -> Catalog:
    cat = Catalog(rel, locale, "apple")
    with open(path, "rb") as f:
        text = _decode(f.read())
    state = 0  # 0 expect key, 1 expect '=', 2 expect value, 3 expect ';'
    key = val = None
    key_line = 0
    for m in _TOKEN.finditer(text):
        quoted, bare, eq, semi, other = m.groups()
        line = text.count("\n", 0, m.start()) + 1 if (quoted is not None or bare or other) else 0
        if quoted is None and not bare and not eq and not semi:
            if other:
                cat.errors.append((line, f"unexpected character {other!r}"))
                return cat
            continue
        tok = _unescape(quoted) if quoted is not None else bare
        if state == 0:
            if semi:
                continue
            if eq:
                cat.errors.append((text.count("\n", 0, m.start()) + 1, "missing key before '='"))
                return cat
            key, key_line, state = tok, line, 1
        elif state == 1:
            if semi:  # "key"; shorthand means value == key
                cat.add(Entry(key, key, key_line))
                state = 0
            elif eq:
                state = 2
            else:
                cat.errors.append((key_line, f"missing '=' after key {key!r}"))
                return cat
        elif state == 2:
            if tok is None:
                cat.errors.append((key_line, f"missing value for key {key!r}"))
                return cat
            val, state = tok, 3
        elif state == 3:
            if not semi:
                cat.errors.append((key_line, f"missing ';' after value of {key!r}"))
                return cat
            cat.add(Entry(key, val, key_line))
            state = 0
    if state != 0:
        cat.errors.append((key_line, "unterminated entry at end of file"))
    return cat
