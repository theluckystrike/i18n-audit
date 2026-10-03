"""--code-scan: find translation keys referenced in code that the source locale lacks.

Regex based, so it only sees literal keys: ``t('a.b')``, ``i18n.t("a.b")``,
``i18next.t``, ``$t('a.b')``, ``this.$t``, ``$tc``, ``I18n.t`` (Ruby),
``<Trans i18nKey="a.b">``, ``formatMessage({ id: 'a.b' })`` and
``<FormattedMessage id="a.b">``. ``useTranslation('ns')`` and
``useTranslation('ns', { keyPrefix: 'x' })`` set the namespace / prefix for
the rest of the file. Keys built at runtime (template literals, concatenation)
are skipped.
"""
from __future__ import annotations

import os
import re
from typing import Dict, List, Optional, Set

from . import detect
from .checks import PLURAL_FORMS
from .model import KINDS, Finding, Group

_Q = r"""(['"`])((?:(?!\1)[^\\\n$]|\\.)+)\1"""
CALLS = [
    re.compile(r"(?<![\w$.])(?:(?:i18n|i18next|I18n|this|props|ctx|app|vm|\$i18n|intl)\??\.)?\$?(?:t|tc)\s*\(\s*" + _Q),
    re.compile(r"\bi18nKey\s*=\s*\{?\s*" + _Q),
    re.compile(r"(?:formatMessage|defineMessage|FormattedMessage|FormattedHTMLMessage)\b[^;]{0,80}?\bid\s*[:=]\s*\{?\s*" + _Q),
]
USE_TRANSLATION = re.compile(
    r"\b(?:useTranslation|withTranslation|getFixedT|useTranslations|getTranslations)\s*\(\s*"
    r"(?:\[\s*)?(?:(['\"])([\w./-]+)\1)?(?:[^)]*?keyPrefix\s*:\s*(['\"])([\w.-]+)\3)?"
)
NS_SEP = ":"


def _catalog_keys(groups: List[Group]):
    """All source keys, plus a namespace map for namespaced (one file per namespace) catalogs."""
    flat: Set[str] = set()
    by_ns: Dict[str, Set[str]] = {}
    for g in groups:
        if g.source is None:
            continue
        keys = set(g.source.entries)
        # plural forms are referenced by their base key
        for k in list(keys):
            m = re.match(r"^(.*?)(?:_ordinal)?_(?:%s|plural)$" % "|".join(PLURAL_FORMS), k)
            if m:
                keys.add(m.group(1))
            m = re.match(r"^(.*)\.(?:%s)$" % "|".join(PLURAL_FORMS), k)
            if m and g.fmt == "yaml":
                keys.add(m.group(1))
        flat |= keys
        ns = _namespace(g.template)
        if ns:
            by_ns.setdefault(ns, set()).update(keys)
    return flat, by_ns


def _namespace(template: str) -> Optional[str]:
    """locales/{loc}/common.json -> common; i18n/{loc}.json -> None."""
    if "/{loc}/" not in template and not template.startswith("{loc}/"):
        return None
    tail = template.split("{loc}/", 1)[1]
    return os.path.splitext(tail)[0]


def _prefixes(keys: Set[str]) -> Set[str]:
    out = set()
    for k in keys:
        parts = k.split(".")
        for i in range(1, len(parts)):
            out.add(".".join(parts[:i]))
    return out


def scan(root: str, groups: List[Group], source_locale: str = "en") -> List[Finding]:
    root = os.path.abspath(root)
    flat, by_ns = _catalog_keys(groups)
    if not flat:
        return []
    prefixes = _prefixes(flat)
    ns_prefixes = {n: _prefixes(k) for n, k in by_ns.items()}
    findings: List[Finding] = []
    seen = set()
    for path in detect.walk(root):
        if not path.endswith(detect.CODE_EXTS) or path.endswith((".d.ts", ".min.js")):
            continue
        rel = os.path.relpath(path, root).replace(os.sep, "/")
        if re.search(r"(^|/)(tests?|__tests__|__mocks__|spec|e2e|stories|fixtures)/|\.(test|spec|stories)\.", rel):
            continue
        try:
            with open(path, encoding="utf-8") as f:
                text = f.read()
        except (UnicodeDecodeError, OSError):
            continue
        if len(text) > 2_000_000:
            continue
        uses = [(m.start(), m.group(2), m.group(4)) for m in USE_TRANSLATION.finditer(text)]
        for rx in CALLS:
            for m in rx.finditer(text):
                key = m.group(2)
                if not _plausible_key(key):
                    continue
                ns, prefix = None, None
                for pos, n, p in uses:
                    if pos < m.start():
                        ns, prefix = n or ns, p
                if _known(key, ns, prefix, flat, by_ns, prefixes, ns_prefixes):
                    continue
                line = text.count("\n", 0, m.start()) + 1
                if (rel, line, key) in seen:
                    continue
                seen.add((rel, line, key))
                findings.append(Finding(rel, line, key, source_locale, "missing_in_source",
                                        KINDS["missing_in_source"][0],
                                        f"Code references {key!r} but no source locale catalog defines it"))
    return findings


def _plausible_key(key: str) -> bool:
    if key.startswith(".") or key.endswith(".") or "${" in key or "#{" in key:
        return False  # Rails lazy lookup or interpolated
    if len(key) > 200 or "\n" in key:
        return False
    if re.fullmatch(r"[\w-]+", key) and len(key) == 1:
        return False
    return True


def _known(key: str, ns: Optional[str], prefix: Optional[str], flat: Set[str],
           by_ns: Dict[str, Set[str]], prefixes: Set[str], ns_prefixes: Dict[str, Set[str]]) -> bool:
    cands = [key]
    if prefix:
        cands.insert(0, f"{prefix}.{key}")
    if NS_SEP in key:
        n, k = key.split(NS_SEP, 1)
        if n in by_ns:
            return k in by_ns[n] or k in ns_prefixes[n]
    if ns and ns in by_ns:
        pool = by_ns[ns]
        if any(c in pool for c in cands):
            return True
    if any(c in flat for c in cands):
        return True
    # t('section') returning an object (returnObjects) is a prefix of real keys
    return any(c in prefixes for c in cands)
