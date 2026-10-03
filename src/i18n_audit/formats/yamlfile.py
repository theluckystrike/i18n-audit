"""YAML catalogs (Rails ``config/locales/*.yml``, i18next / vue-i18n YAML).

A line-aware parser for the YAML subset locale files use: nested mappings,
sequences, plain / quoted / block scalars, flow sequences, comments, anchors.
If it cannot handle a file and PyYAML is installed (``pip install
i18n-audit[yaml]``) PyYAML is used instead, without line numbers.
"""
from __future__ import annotations

import re
from typing import List, Optional, Tuple

from ..model import Catalog, Entry

_KEY = re.compile(
    r"""^(?:"((?:[^"\\]|\\.)*)"|'((?:[^']|'')*)'|([^\s#'"\-?:,\[\]{}&*!|>%@`][^#]*?|-[^\s#][^#]*?|\?[^#]*?))"""
    r"""\s*:(?:\s+(.*))?$"""
)
_DQ_ESC = {"n": "\n", "t": "\t", "r": "\r", "\\": "\\", '"': '"', "/": "/", "0": "\0", " ": " ", "e": "\x1b"}


class YAMLError(ValueError):
    def __init__(self, msg: str, line: int):
        super().__init__(f"{msg} (line {line})")
        self.line = line


def _strip_comment(s: str) -> str:
    """Remove a trailing ' # comment' outside of quotes."""
    if "#" not in s:
        return s.rstrip()
    q = None
    for i, c in enumerate(s):
        if q:
            if c == q:
                q = None
            continue
        if c in "\"'" and (i == 0 or s[i - 1] in " :[{,"):
            q = c
        elif c == "#" and (i == 0 or s[i - 1] in " \t"):
            return s[:i].rstrip()
    return s.rstrip()


def _dq(raw: str, line: int) -> str:
    out = []
    i = 0
    while i < len(raw):
        c = raw[i]
        if c != "\\":
            out.append(c)
            i += 1
            continue
        e = raw[i + 1] if i + 1 < len(raw) else ""
        if e in _DQ_ESC:
            out.append(_DQ_ESC[e])
            i += 2
        elif e in "xuU":
            width = {"x": 2, "u": 4, "U": 8}[e]
            out.append(chr(int(raw[i + 2:i + 2 + width], 16)))
            i += 2 + width
        else:
            raise YAMLError(f"invalid escape \\{e}", line)
    return "".join(out)


class _Parser:
    def __init__(self, text: str):
        self.raw = text.replace("\r\n", "\n").replace("\t", "  ").split("\n")
        self.lines: List[Optional[Tuple[int, str]]] = []
        for ln in self.raw:
            body = ln.lstrip(" ")
            if not body or body.startswith("#") or body.startswith("%") or body in ("---", "...") \
                    or body.startswith("--- "):
                self.lines.append(None)
            else:
                self.lines.append((len(ln) - len(body), body))
        self.leaves: List[Tuple[List[str], object, int]] = []
        self.dups: List[Tuple[List[str], int]] = []

    def next_sig(self, i: int) -> int:
        while i < len(self.lines) and self.lines[i] is None:
            i += 1
        return i

    def block(self, i: int, parent_indent: int, path: List[str], allow_same_seq: bool = False) -> int:
        i = self.next_sig(i)
        if i >= len(self.lines):
            return i
        ind, body = self.lines[i]
        is_seq = body == "-" or body.startswith("- ")
        if ind > parent_indent or (allow_same_seq and ind == parent_indent and is_seq):
            if is_seq:
                return self.seq(i, ind, path)
            return self.mapping(i, ind, path)
        return i

    def mapping(self, i: int, indent: int, path: List[str]) -> int:
        seen = set()
        while True:
            i = self.next_sig(i)
            if i >= len(self.lines):
                return i
            ind, body = self.lines[i]
            if ind < indent:
                return i
            if ind > indent:
                raise YAMLError("bad indentation", i + 1)
            if body == "-" or body.startswith("- "):
                return i
            m = _KEY.match(_strip_comment(body)) if not body.startswith(("'", '"')) else _KEY.match(body)
            if not m:
                raise YAMLError("expected 'key: value'", i + 1)
            dq, sq, plain, rest = m.groups()
            key = _dq(dq, i + 1) if dq is not None else sq.replace("''", "'") if sq is not None else plain.strip()
            if key in ("<<",):
                i += 1
                i = self.block(i, ind, path + ["<<"])
                continue
            if key in seen:
                self.dups.append((path + [key], i + 1))
            seen.add(key)
            i = self.value(i, ind, path + [key], rest or "")

    def seq(self, i: int, indent: int, path: List[str]) -> int:
        idx = 0
        while True:
            i = self.next_sig(i)
            if i >= len(self.lines):
                return i
            ind, body = self.lines[i]
            if ind != indent or not (body == "-" or body.startswith("- ")):
                if ind > indent:
                    raise YAMLError("bad indentation in sequence", i + 1)
                return i
            item = body[1:].lstrip(" ")
            sub = path + [str(idx)]
            idx += 1
            if not item:
                i = self.block(i + 1, ind, sub)
            elif _KEY.match(_strip_comment(item)) and not item.startswith(("'", '"', "[", "{")):
                col = ind + (len(body) - len(item))
                self.lines[i] = (col, item)
                i = self.mapping(i, col, sub)
            else:
                i = self.value(i, ind, sub, item)

    def value(self, i: int, ind: int, path: List[str], rest: str) -> int:
        line = i + 1
        rest = rest.strip()
        if rest.startswith("&"):
            rest = rest.split(None, 1)[1] if " " in rest else ""
        if rest.startswith("!"):
            rest = rest.split(None, 1)[1] if " " in rest else ""
        if not rest or rest.startswith("#"):
            return self.block(i + 1, ind, path, allow_same_seq=True)
        if rest.startswith("*"):
            return i + 1
        if rest[0] in "|>":
            return self.block_scalar(i, ind, path, rest)
        if rest[0] in "\"'":
            return self.quoted(i, path, rest)
        rest = _strip_comment(rest)
        if rest.startswith("[") and rest.endswith("]"):
            for n, part in enumerate(self.flow_items(rest[1:-1])):
                self.leaves.append((path + [str(n)], part, line))
            return i + 1
        if rest == "{}":
            return i + 1
        # plain scalar, possibly continued on more-indented lines
        parts = [rest]
        j = i + 1
        while j < len(self.lines):
            nxt = self.lines[j]
            if nxt is None:
                if self.raw[j].strip() == "":
                    j += 1
                    continue
                break
            if nxt[0] <= ind:
                break
            parts.append(_strip_comment(nxt[1]))
            j += 1
        val = " ".join(parts)
        self.leaves.append((path, self.plain_value(val), line))
        return j

    @staticmethod
    def plain_value(v: str):
        if v in ("~", "null", "Null", "NULL"):
            return None
        if v in ("true", "True", "TRUE", "false", "False", "FALSE"):
            return v.lower() == "true"
        if re.fullmatch(r"[-+]?\d+(\.\d+)?", v):
            return float(v)  # numbers are configuration (precision, delimiters), not translations
        return v

    @staticmethod
    def flow_items(s: str) -> List[str]:
        out = []
        for m in re.finditer(r"""\s*("(?:[^"\\]|\\.)*"|'(?:[^']|'')*'|[^,]*)\s*(?:,|$)""", s):
            tok = m.group(1).strip()
            if not tok and m.end() >= len(s):
                break
            if tok.startswith('"'):
                tok = _dq(tok[1:-1], 0)
            elif tok.startswith("'"):
                tok = tok[1:-1].replace("''", "'")
            out.append(tok)
            if m.end() >= len(s):
                break
        return out

    def quoted(self, i: int, path: List[str], rest: str) -> int:
        q = rest[0]
        line = i + 1
        text = rest
        j = i
        pat = re.compile(r'^"((?:[^"\\]|\\.)*)"' if q == '"' else r"^'((?:[^']|'')*)'")
        while True:
            m = pat.match(text)
            if m:
                tail = _strip_comment(text[m.end():]).strip()
                if tail:
                    raise YAMLError("unexpected text after quoted scalar", j + 1)
                break
            j += 1
            if j >= len(self.raw):
                raise YAMLError("unterminated quoted scalar", line)
            nxt = self.raw[j].strip()
            if q == '"' and text.endswith("\\"):
                text = text[:-1] + nxt
            else:
                text = text + ("\n" if not nxt else " ") + nxt
        body = m.group(1)
        val = _dq(body, line) if q == '"' else body.replace("''", "'")
        self.leaves.append((path, val, line))
        return j + 1

    def block_scalar(self, i: int, ind: int, path: List[str], header: str) -> int:
        line = i + 1
        style = header[0]
        chomp = "-" if "-" in header else "+" if "+" in header else ""
        m = re.search(r"\d", header)
        lines: List[str] = []
        j = i + 1
        block_ind = ind + int(m.group(0)) if m else None
        while j < len(self.raw):
            raw = self.raw[j].replace("\t", "  ")
            if raw.strip() == "":
                lines.append("")
                j += 1
                continue
            cur = len(raw) - len(raw.lstrip(" "))
            if cur <= ind:
                break
            if block_ind is None:
                block_ind = cur
            if cur < block_ind:
                break
            lines.append(raw[block_ind:])
            j += 1
        trailing = 0
        while lines and lines[-1] == "":
            lines.pop()
            trailing += 1
        if style == "|":
            val = "\n".join(lines)
        else:
            val = ""
            for n, ln in enumerate(lines):
                if n == 0:
                    val = ln
                elif ln == "" or ln.startswith(" ") or lines[n - 1] == "" or lines[n - 1].startswith(" "):
                    val += "\n" + ln
                else:
                    val += " " + ln
        if chomp == "+":
            val += "\n" * (trailing + 1)
        elif chomp != "-" and lines:
            val += "\n"
        self.leaves.append((path, val, line))
        return j

    def parse(self):
        i = self.block(0, -1, [])
        i = self.next_sig(i)
        if i < len(self.lines):
            raise YAMLError("unexpected content", i + 1)
        return self


def _pyyaml_leaves(text: str):
    import yaml  # optional dependency

    out = []

    def walk(o, p):
        if isinstance(o, dict):
            for k, v in o.items():
                walk(v, p + [str(k)])
        elif isinstance(o, list):
            for n, v in enumerate(o):
                walk(v, p + [str(n)])
        else:
            out.append((p, o, 0))

    walk(yaml.safe_load(text), [])
    return out


def load(path: str, rel: str, locale: str, strip_root: bool = True) -> Catalog:
    cat = Catalog(rel, locale, "yaml")
    with open(path, encoding="utf-8") as f:
        text = f.read()
    dups = []
    try:
        p = _Parser(text).parse()
        leaves, dups = p.leaves, p.dups
    except (YAMLError, IndexError, ValueError) as e:
        try:
            leaves = _pyyaml_leaves(text)
        except ImportError:
            cat.errors.append((getattr(e, "line", 0), f"{e}; install i18n-audit[yaml] for full YAML support"))
            return cat
        except Exception as e2:  # yaml.YAMLError
            mark = getattr(e2, "problem_mark", None)
            cat.errors.append(((mark.line + 1) if mark else 0, str(e2).splitlines()[0]))
            return cat
    # Rails files wrap everything in a top-level key that is the locale ("en:" / "pt-BR:")
    roots = {pth[0] for pth, _, _ in leaves if pth}
    strip = strip_root and len(roots) == 1 and _same_locale(next(iter(roots)), locale)
    for pth, ln in dups:
        sub = pth[1:] if strip else pth
        if sub:
            cat.duplicates.append(Entry(".".join(sub), "", ln, {"top_level": len(sub) == 1}))
    for pth, val, ln in leaves:
        if strip:
            pth = pth[1:]
        if not pth or "<<" in pth or not isinstance(val, str):
            continue
        key = ".".join(pth)
        cat.entries[key] = Entry(key, val, ln)
    return cat


def root_locale(path: str) -> Optional[str]:
    """The single top-level key of a Rails style YAML file, if any."""
    try:
        with open(path, encoding="utf-8") as f:
            for ln in f:
                if ln.strip() and not ln.lstrip().startswith(("#", "---", "%")):
                    m = re.match(r"""^["']?([A-Za-z]{2,3}(?:[-_][A-Za-z0-9]{2,8})*)["']?\s*:\s*(#.*)?$""", ln.rstrip())
                    return m.group(1) if m else None
    except (OSError, UnicodeDecodeError):
        return None
    return None


def _same_locale(a: str, b: str) -> bool:
    return a.replace("_", "-").lower() == b.replace("_", "-").lower()
