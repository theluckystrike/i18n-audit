"""Java ``.properties`` resource bundles (``messages_de.properties``)."""
from __future__ import annotations

import re

from ..model import Catalog, Entry


def _unescape(s: str) -> str:
    def rep(m):
        e = m.group(1)
        if e[0] == "u":
            return chr(int(e[1:], 16))
        return {"n": "\n", "t": "\t", "r": "\r", "f": "\f"}.get(e, e)

    return re.sub(r"\\(u[0-9a-fA-F]{4}|.)", rep, s)


def load(path: str, rel: str, locale: str) -> Catalog:
    cat = Catalog(rel, locale, "properties")
    with open(path, "rb") as f:
        data = f.read()
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        text = data.decode("latin-1")  # pre Java 9 default encoding
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        start = i
        line = lines[i].lstrip()
        i += 1
        if not line or line[0] in "#!":
            continue
        # logical line: odd number of trailing backslashes continues it
        while re.search(r"(?<!\\)(\\\\)*\\$", line) and i < len(lines):
            line = line[:-1] + lines[i].lstrip()
            i += 1
        m = re.match(r"((?:[^\\:=\s]|\\.)*)\s*[:=]?\s*(.*)$", line, re.S)
        key, val = _unescape(m.group(1)), _unescape(m.group(2))
        if not key:
            continue
        cat.add(Entry(key, val, start + 1, {"raw": m.group(2)}))
    return cat
