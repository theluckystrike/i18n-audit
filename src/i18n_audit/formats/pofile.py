"""gettext .po / .pot catalogs (GNU gettext, Django, Lingui, Babel)."""
from __future__ import annotations

import re
from typing import Dict, List

from ..model import Catalog, Entry

_ESC = {"n": "\n", "t": "\t", "r": "\r", '"': '"', "\\": "\\", "a": "\a", "b": "\b", "f": "\f", "v": "\v"}


def _unquote(s: str, line: int, errors: List[tuple]) -> str:
    s = s.strip()
    if len(s) < 2 or not (s.startswith('"') and s.endswith('"')):
        errors.append((line, f"malformed string: {s[:40]}"))
        return ""
    return re.sub(r'\\(.)', lambda m: _ESC.get(m.group(1), m.group(1)), s[1:-1])


def parse(text: str):
    """Return (entries, errors). Each entry is a dict with msgctxt, msgid,
    msgid_plural, msgstr (list), flags, line."""
    entries: List[Dict] = []
    errors: List[tuple] = []
    cur: Dict = {}
    field = None

    def new():
        return {"msgctxt": None, "msgid": None, "msgid_plural": None, "msgstr": {}, "flags": set(), "line": 0}

    def push():
        if cur.get("msgid") is not None:
            entries.append(cur)

    cur = new()
    pending_flags: set = set()
    for n, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#~"):
            continue  # obsolete entry
        if line.startswith("#,"):
            if cur.get("msgid") is not None and field and field.startswith("msgstr"):
                push()
                cur = new()
                field = None
            pending_flags |= {f.strip() for f in line[2:].split(",") if f.strip()}
            continue
        if line.startswith("#"):
            if cur.get("msgid") is not None and field and field.startswith("msgstr"):
                push()
                cur = new()
                field = None
            continue
        m = re.match(r'^(msgctxt|msgid_plural|msgid|msgstr(?:\[(\d+)\])?)\s+(".*")$', line)
        if m:
            kw, idx, val = m.groups()
            if kw in ("msgctxt", "msgid") and field and field.startswith("msgstr"):
                push()
                cur = new()
            if kw == "msgctxt" or (kw == "msgid" and cur["msgctxt"] is None):
                cur["flags"] |= pending_flags
                pending_flags = set()
            if kw == "msgid":
                cur["line"] = n
            v = _unquote(val, n, errors)
            if kw.startswith("msgstr"):
                field = "msgstr[%s]" % (idx or 0)
                cur["msgstr"][int(idx or 0)] = v
            else:
                field = kw
                cur[kw] = v
            continue
        if line.startswith('"') and field:
            v = _unquote(line, n, errors)
            if field.startswith("msgstr["):
                k = int(field[7:-1])
                cur["msgstr"][k] += v
            else:
                cur[field] += v
            continue
        errors.append((n, f"unexpected line: {line[:60]}"))
    push()
    return entries, errors


def entry_key(e: Dict) -> str:
    return (e["msgctxt"] + "|" if e["msgctxt"] else "") + e["msgid"]


def load(path: str, rel: str, locale: str) -> Catalog:
    is_template = path.endswith(".pot")
    cat = Catalog(rel, locale, "po")
    with open(path, encoding="utf-8", errors="replace") as f:
        entries, errors = parse(f.read())
    cat.errors.extend(errors)
    seen = set()
    for e in entries:
        if e["msgid"] == "":
            continue  # header
        key = entry_key(e)
        if key in seen:
            cat.duplicates.append(Entry(key, "", e["line"], {"top_level": False}))
        seen.add(key)
        meta = {"flags": e["flags"], "msgid": e["msgid"], "fuzzy": "fuzzy" in e["flags"]}
        if e["msgid_plural"] is None:
            value = e["msgid"] if is_template else e["msgstr"].get(0, "")
            cat.entries[key] = Entry(key, value, e["line"], meta)
        else:
            forms = e["msgstr"] if not is_template else {0: e["msgid"], 1: e["msgid_plural"]}
            for idx in sorted(forms):
                m = dict(meta, plural_index=idx, msgid_plural=e["msgid_plural"], base_key=key)
                k = f"{key}[{idx}]"
                cat.entries[k] = Entry(k, forms[idx], e["line"], m)
    return cat
