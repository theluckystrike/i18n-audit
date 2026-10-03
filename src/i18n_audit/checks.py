"""All catalog checks. Input: discovered groups. Output: a list of Findings."""
from __future__ import annotations

import re
from typing import Dict, Iterable, List, Optional, Set

from . import icu
from . import placeholders as ph
from .formats.android import unescaped_apostrophe
from .model import ERROR, INFO, KINDS, WARNING, Catalog, Entry, Finding, Group

PLURAL_FORMS = ("zero", "one", "two", "few", "many", "other")
_I18NEXT_PLURAL = re.compile(r"^(.*?)(?:_ordinal)?_(zero|one|two|few|many|other|plural)$")
_DOT_PLURAL = re.compile(r"^(.*)\.(zero|one|two|few|many|other)$")
_ANDROID_PLURAL = re.compile(r"^(.*):(zero|one|two|few|many|other)$")
_PO_PLURAL = re.compile(r"^(.*)\[(\d+)\]$")


def _finding(cat: Catalog, entry: Optional[Entry], kind: str, message: str, src: Optional[str] = None,
             severity: Optional[str] = None, key: Optional[str] = None, line: Optional[int] = None) -> Finding:
    return Finding(
        file=cat.path,
        line=line if line is not None else (entry.line if entry else 0),
        key=key if key is not None else (entry.key if entry else ""),
        locale=cat.locale,
        kind=kind,
        severity=severity or KINDS[kind][0],
        message=message,
        source_text=src,
        locale_text=entry.value if entry is not None and entry.value != "" else None,
    )


# --------------------------------------------------------------------------- plural keys
def plural_base(key: str, fmt: str) -> Optional[tuple]:
    """(base, form) when ``key`` is one plural form of a pluralized message."""
    rx = {"android": _ANDROID_PLURAL, "yaml": _DOT_PLURAL}.get(fmt)
    for r in ([rx] if rx else []) + [_I18NEXT_PLURAL]:
        m = r.match(key)
        if m:
            return m.group(1), m.group(2)
    if fmt == "po":
        m = _PO_PLURAL.match(key)
        if m:
            return m.group(1), m.group(2)
    return None


def _plural_key(base: str, form: str, like: str, fmt: str) -> str:
    if fmt == "po":
        return f"{base}[{form}]"
    if fmt == "android" and _ANDROID_PLURAL.match(like):
        return f"{base}:{form}"
    if _DOT_PLURAL.match(like) and not _I18NEXT_PLURAL.match(like):
        return f"{base}.{form}"
    sep = "_ordinal_" if "_ordinal_" in like else "_"
    return f"{base}{sep}{form}"


def ref_key(key: str, src: Dict[str, Entry], fmt: str) -> Optional[str]:
    """The source key a locale key translates (handles plural forms the source lacks)."""
    if key in src:
        return key
    pb = plural_base(key, fmt)
    if not pb:
        return None
    base, form = pb
    if fmt == "po":
        cands = [f"{base}[1]", f"{base}[0]"]
    else:
        cands = [_plural_key(base, f, key, fmt) for f in ("other", "one", "plural")] + [base]
    for c in cands:
        if c in src:
            return c
    return None


def has_plural_sibling(key: str, keys: Set[str], fmt: str) -> bool:
    pb = plural_base(key, fmt)
    if not pb:
        return False
    base, _ = pb
    if fmt == "po":
        return any(k.startswith(base + "[") for k in keys)
    forms = PLURAL_FORMS + ("plural",)
    return any(_plural_key(base, f, key, fmt) in keys for f in forms)


# --------------------------------------------------------------------------- syntax per entry
def entry_syntax(group: Group, entry: Entry, src_text: str) -> str:
    if group.syntax != "gettext":
        return group.syntax
    flags = entry.meta.get("flags") or set()
    if "python-brace-format" in flags:
        return "brace"
    if any(f.endswith("-format") and not f.startswith("no-") for f in flags):
        return "printf"
    if re.search(r"\{\{\s*\w+\s*\}\}", src_text):
        return "i18next"
    if ph.PRINTF.search(ph.strip_printf_escapes(src_text)):
        return "printf"
    return "brace"


# --------------------------------------------------------------------------- string comparison
def compare(group: Group, cat: Catalog, entry: Entry, src: str, ref: str) -> List[Finding]:
    out: List[Finding] = []
    tr = entry.value
    syntax = entry_syntax(group, entry, src)
    plural = plural_base(entry.key, cat.fmt) is not None or entry.meta.get("plural_index") is not None

    src_all, src_req = ph.tokens(src, syntax)
    src_names = {ph.names(t): t for t in src_all}

    # 1. syntax validity
    if syntax == "icu":
        try:
            icu.parse(tr)
        except icu.ICUSyntaxError as e:
            wrong = _wrong_syntax(tr, src_names, syntax)
            if wrong:
                out.append(_finding(cat, entry, "wrong_syntax", _wrong_msg(wrong, syntax), src))
            elif icu.is_valid(src):
                out.append(_finding(cat, entry, "invalid_icu", f"Invalid ICU message: {e.reason}", src))
            return out
        unknown = icu.unknown_plural_selectors(tr)
        if unknown:
            out.append(_finding(cat, entry, "invalid_icu",
                                "Unknown plural categor%s %s (only zero, one, two, few, many, other, =N are valid; "
                                "the branch is never used)" % ("ies" if len(unknown) > 1 else "y",
                                                               ", ".join(repr(u) for u in unknown)),
                                src, severity=WARNING))
    elif syntax == "i18next":
        if tr.count("{{") != tr.count("}}") and src.count("{{") == src.count("}}"):
            out.append(_finding(cat, entry, "unbalanced_braces",
                                "Unbalanced {{ }}: %d opening, %d closing" % (tr.count("{{"), tr.count("}}")), src))
            return out
    elif syntax in ("vue", "rails", "brace"):
        if _brace_depth_bad(tr) and not _brace_depth_bad(src):
            out.append(_finding(cat, entry, "unbalanced_braces", "Unbalanced { } braces", src))
            return out

    # 2. placeholders
    tr_all, _ = ph.tokens(tr, syntax)
    missing = sorted(src_req - tr_all)
    extra = sorted(tr_all - src_all)
    show = lambda toks, text: ", ".join(ph.display(t, text) for t in toks)  # noqa: E731
    if missing:
        wrong = _wrong_syntax(tr, {ph.names(t): t for t in missing}, syntax)
        if wrong:
            out.append(_finding(cat, entry, "wrong_syntax", _wrong_msg(wrong, syntax), src))
            fixed = set(wrong)
            missing = [t for t in missing if ph.names(t) not in fixed]
            extra = [t for t in extra if ph.names(t) not in fixed]
    if missing or extra:
        if plural and missing and not extra:
            out.append(_finding(cat, entry, "plural_placeholder",
                                "Plural form omits %s (fine if the language spells the number out)"
                                % show(missing, src), src))
        else:
            parts = []
            if missing:
                parts.append("missing " + show(missing, src))
            if extra:
                parts.append("unexpected " + show(extra, tr))
            msg = "; ".join(parts)
            hint = _hint(src, tr, missing, extra, syntax)
            out.append(_finding(cat, entry, "placeholder_mismatch", msg + (". " + hint if hint else ""), src))

    # 3. tags
    out.extend(_tag_findings(cat, entry, src, tr))
    return out


def _brace_depth_bad(s: str) -> bool:
    s = re.sub(r"'[^']*'", "", s) if "'" in s else s
    depth = 0
    for c in s:
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth < 0:
                return True
    return depth != 0


def _wrong_syntax(tr: str, wanted: Dict[str, str], syntax: str) -> Dict[str, tuple]:
    """Placeholders from ``wanted`` (name -> expected token) present in ``tr`` in another syntax."""
    found = ph.any_syntax_names(tr)
    out = {}
    for name, expected in wanted.items():
        got = found.get(name)
        if got is None or got == expected:
            continue
        if syntax in ("icu", "vue", "brace", "javamf") and got == "{%s}" % name:
            continue
        if syntax == "i18next" and got == "{{%s}}" % name:
            continue
        if syntax == "rails" and got == "%%{%s}" % name:
            continue
        out[name] = (expected, got)
    return out


def _wrong_msg(wrong: Dict[str, tuple], syntax: str) -> str:
    items = ", ".join(f"{got} should be {exp}" for exp, got in wrong.values())
    return f"Placeholder in the wrong syntax for {syntax}: {items}"


def _hint(src: str, tr: str, missing: List[str], extra: List[str], syntax: str) -> str:
    if syntax in ("icu", "javamf"):
        try:
            lit = icu.literal_braces(tr, "java" if syntax == "javamf" else "icu")
        except icu.ICUSyntaxError:
            lit = []
        quoted = [m for m in missing if ph.names(m) in lit]
        if quoted:
            return ("%s %s inside apostrophe quoted text and renders literally; use '' for a literal apostrophe"
                    % (", ".join(quoted), "is" if len(quoted) == 1 else "are"))
    if missing and extra and len(missing) == len(extra):
        return "Looks renamed or translated: the code passes %s" % ", ".join(ph.display(m, src) for m in missing)
    return ""


def _tag_findings(cat: Catalog, entry: Entry, src: str, tr: str) -> List[Finding]:
    st, tt = ph.tags(src), ph.tags(tr)
    if not st and not tt:
        return []
    out = []
    if st != tt:
        missing = sorted((st - tt).elements())
        extra = sorted((tt - st).elements())
        parts = []
        if missing:
            parts.append("missing " + ", ".join(missing))
        if extra:
            parts.append("unexpected " + ", ".join(extra))
        trans = any(re.match(r"<\d", t) for t in missing + extra)
        sev = ERROR if trans or missing else WARNING
        out.append(_finding(cat, entry, "tag_mismatch",
                            ("Trans component tags differ: " if trans else "Tags differ: ") + "; ".join(parts),
                            src, severity=sev))
        return out
    bad = ph.unbalanced_tags(tr)
    if bad and not ph.unbalanced_tags(src):
        out.append(_finding(cat, entry, "tag_mismatch", "Unbalanced tags: " + ", ".join(bad), src))
    return out


# --------------------------------------------------------------------------- per catalog
def _file_level(cat: Catalog) -> List[Finding]:
    out = []
    for line, msg in cat.errors:
        out.append(_finding(cat, None, "parse_error", msg, line=line))
    for d in cat.duplicates:
        top = d.meta.get("top_level")
        msg = ("Duplicate top-level section %r: the later block replaces the earlier one" % d.key if top
               else "Duplicate key %r: only the last value is used" % d.key)
        out.append(_finding(cat, d, "duplicate_key", msg, severity=ERROR if top else WARNING))
    if cat.fmt == "android":
        for e in cat.entries.values():
            if e.meta.get("translatable", True) and unescaped_apostrophe(str(e.meta.get("raw", ""))):
                out.append(_finding(cat, e, "android_apostrophe",
                                    "Apostrophe must be escaped as \\' (or the string wrapped in double quotes)"))
    return out


def source_text(group: Group, entry: Entry, ref: Optional[str]) -> Optional[str]:
    src = group.source
    if src is not None and ref is not None and ref in src.entries and src.entries[ref].value:
        return src.entries[ref].value
    if group.fmt == "po":
        idx = entry.meta.get("plural_index")
        if idx is not None and idx >= 1:
            return entry.meta.get("msgid_plural")
        return entry.meta.get("msgid")
    return None


def check_group(group: Group) -> List[Finding]:
    out: List[Finding] = []
    src = group.source
    src_entries = src.entries if src else {}
    if src is not None:
        out.extend(_file_level(src))
        if group.syntax == "icu":
            for e in src_entries.values():
                try:
                    icu.parse(e.value)
                except icu.ICUSyntaxError as err:
                    out.append(_finding(src, e, "invalid_icu", f"Invalid ICU message in source: {err.reason}"))

    for loc, cat in sorted(group.catalogs.items()):
        if cat is src:
            continue
        out.extend(_file_level(cat))
        if cat.errors and cat.fmt != "po":
            continue  # a partial parse would report every later key as missing
        keys = set(cat.entries)
        for key, entry in cat.entries.items():
            if entry.meta.get("fuzzy"):
                continue
            ref = ref_key(key, src_entries, cat.fmt) if src is not None else key
            if src is not None and ref is None:
                if not has_plural_sibling(key, set(src_entries), cat.fmt):
                    out.append(_finding(cat, entry, "stale_key", "Key is not in the source locale"))
                continue
            if src is not None and ref in src_entries and src_entries[ref].meta.get("translatable") is False:
                continue
            s = source_text(group, entry, ref)
            if not entry.value or s is None or s == entry.value:
                continue
            out.extend(compare(group, cat, entry, s, ref))
        if src is None:
            continue
        for key, sentry in src_entries.items():
            if sentry.meta.get("translatable") is False or not sentry.value:
                continue
            if key in keys:
                if cat.fmt == "po" and not cat.entries[key].value:
                    out.append(_finding(cat, cat.entries[key], "missing_key", "Untranslated (empty msgstr)",
                                        sentry.value, severity=INFO))
                continue
            if has_plural_sibling(key, keys, cat.fmt):
                continue
            out.append(_finding(cat, None, "missing_key", "Key is missing in this locale", sentry.value,
                                key=key, line=0))
    if src is not None:
        for loc in group.expected_locales:
            if loc not in group.catalogs and loc != group.source_locale:
                path = group.template.replace("{loc}", loc)
                out.append(Finding(path, 0, "", loc, "missing_file", KINDS["missing_file"][0],
                                   f"No {path} although {src.path} exists ({len(src_entries)} keys untranslated)"))
    return out


def run(groups: Iterable[Group]) -> List[Finding]:
    out: List[Finding] = []
    for g in groups:
        out.extend(check_group(g))
    return out
