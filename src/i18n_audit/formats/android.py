"""Android ``res/values*/strings.xml`` resources."""
from __future__ import annotations

import re
import xml.parsers.expat
from typing import List

from ..model import Catalog, Entry


def _unescape_android(s: str) -> str:
    """Resolve Android string escapes (\\', \\", \\n, \\@, \\?, \\uXXXX) and quoting."""
    out = []
    i = 0
    quoted = False
    while i < len(s):
        c = s[i]
        if c == "\\" and i + 1 < len(s):
            e = s[i + 1]
            if e == "u" and re.match(r"[0-9a-fA-F]{4}", s[i + 2:i + 6]):
                out.append(chr(int(s[i + 2:i + 6], 16)))
                i += 6
                continue
            out.append({"n": "\n", "t": "\t"}.get(e, e))
            i += 2
            continue
        if c == '"':
            quoted = not quoted
            i += 1
            continue
        out.append(c)
        i += 1
    return "".join(out)


def unescaped_apostrophe(raw: str) -> bool:
    """True when an apostrophe is neither backslash-escaped nor inside double quotes.

    aapt2 rejects (or silently drops) such strings.
    """
    quoted = False
    i = 0
    while i < len(raw):
        c = raw[i]
        if c == "\\":
            i += 2
            continue
        if c == '"':
            quoted = not quoted
        elif c == "'" and not quoted:
            return True
        i += 1
    return False


def load(path: str, rel: str, locale: str) -> Catalog:
    cat = Catalog(rel, locale, "android")
    with open(path, "rb") as f:
        data = f.read()
    p = xml.parsers.expat.ParserCreate()
    stack: List[dict] = []  # open resource element state
    seen = set()

    def start(name, attrs):
        if stack:
            cur = stack[-1]
            if name == "item" and cur["kind"] in ("plurals", "string-array") and cur["depth"] == 0:
                key = cur["name"] + (":" + attrs.get("quantity") if cur["kind"] == "plurals" else "[%d]" % cur["idx"])
                cur["idx"] += 1
                stack.append({"kind": "item", "name": key, "buf": [], "depth": 0, "line": p.CurrentLineNumber,
                              "translatable": cur["translatable"], "parent": cur["name"]})
                return
            cur["depth"] += 1
            a = "".join(' %s="%s"' % kv for kv in attrs.items())
            cur["buf"].append("<%s%s>" % (name, a))
            return
        if name in ("string", "plurals", "string-array") and "name" in attrs:
            stack.append({"kind": name, "name": attrs["name"], "buf": [], "depth": 0, "idx": 0,
                          "line": p.CurrentLineNumber, "translatable": attrs.get("translatable") != "false"})

    def end(name):
        if not stack:
            return
        cur = stack[-1]
        if cur["depth"] > 0:
            cur["depth"] -= 1
            cur["buf"].append("</%s>" % name)
            return
        stack.pop()
        if cur["kind"] in ("string", "item"):
            raw = "".join(cur["buf"])
            key = cur["name"]
            meta = {"raw": raw, "translatable": cur["translatable"]}
            if cur["kind"] == "item":
                meta["base_key"] = cur["parent"]
            else:
                if key in seen:
                    cat.duplicates.append(Entry(key, "", cur["line"], {"top_level": False}))
                seen.add(key)
            cat.entries[key] = Entry(key, _unescape_android(raw.strip()), cur["line"], meta)
        elif cur["kind"] in ("plurals", "string-array"):
            if cur["name"] in seen:
                cat.duplicates.append(Entry(cur["name"], "", cur["line"], {"top_level": False}))
            seen.add(cur["name"])

    def chars(text):
        if stack:
            stack[-1]["buf"].append(text)

    p.StartElementHandler = start
    p.EndElementHandler = end
    p.CharacterDataHandler = chars
    try:
        p.Parse(data, True)
    except xml.parsers.expat.ExpatError as e:
        cat.errors.append((e.lineno, f"invalid XML: {xml.parsers.expat.ErrorString(e.code)}"))
    return cat
