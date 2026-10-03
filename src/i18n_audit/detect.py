"""Find locale files in a repository, group them by catalog and detect the interpolation syntax."""
from __future__ import annotations

import json
import os
import re
from collections import Counter, defaultdict
from typing import Dict, Iterator, List, Optional, Tuple

from . import formats, locales
from .formats import yamlfile
from .model import Catalog, Group

SKIP_DIRS = {
    ".git", ".hg", ".svn", "node_modules", "bower_components", "vendor", "dist", "build", "out", ".next",
    ".nuxt", ".output", ".svelte-kit", "target", "coverage", "__pycache__", ".venv", "venv", "env",
    ".tox", ".mypy_cache", ".pytest_cache", "Pods", "Carthage", ".gradle", ".idea", ".cache", "tmp",
    "site-packages", ".turbo", ".yarn", "storybook-static",
}
CODE_EXTS = (".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".vue", ".svelte", ".rb", ".erb", ".haml", ".slim")

LIB_FAMILIES = {
    "i18next": re.compile(r"^(i18next|react-i18next|next-i18next|i18next-.*|vue-i18next|ng-i18next|svelte-i18next)$"),
    "icu": re.compile(r"^(react-intl|@formatjs/.*|intl-messageformat|@lingui/.*|next-intl|use-intl|@tolgee/.*|"
                      r"svelte-i18n|@messageformat/.*|messageformat|ember-intl|angular-l10n)$"),
    "vue": re.compile(r"^(vue-i18n|petite-vue-i18n|@nuxtjs/i18n|@intlify/.*)$"),
}


def walk(root: str) -> Iterator[str]:
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".") or d in (".tx",))
        for fn in sorted(filenames):
            yield os.path.join(dirpath, fn)


def classify(rel: str, abspath: str) -> Optional[Tuple[str, str, str]]:
    """Return (format, locale, template) for a locale file, else None.

    The template is the relative path with the locale replaced by ``{loc}`` so
    files that translate the same catalog share a template.
    """
    parts = rel.split("/")
    fn = parts[-1]
    stem, ext = os.path.splitext(fn)
    ext = ext.lower()

    if ext == ".strings" and len(parts) >= 2 and parts[-2].endswith(".lproj"):
        loc = parts[-2][:-6]
        if loc == "Base" or locales.parse(loc):
            return "apple", loc, "/".join(parts[:-2] + ["{loc}.lproj", fn])
        return None

    if ext == ".xml" and len(parts) >= 2 and parts[-2].startswith("values"):
        q = parts[-2][len("values"):]
        if q and not q.startswith("-"):
            return None
        if not _looks_like_android_strings(abspath):
            return None
        loc = "" if not q else locales.android_qualifier(q[1:])
        if loc is None:
            return None
        return "android", loc, "/".join(parts[:-2] + ["values{loc}", fn])

    if ext == ".properties":
        m = re.match(r"^(.+?)((?:_[A-Za-z]{2,3})(?:_[A-Za-z0-9]{2,8})*)?$", stem)
        if not m:
            return None
        base, suffix = m.group(1), m.group(2)
        loc = ""
        if suffix:
            loc = locales.parse(suffix[1:])
            if not loc:
                return None
        return "properties", loc, "/".join(parts[:-1] + [base + "{loc}.properties"])

    if ext in (".po", ".pot"):
        if ext == ".pot":
            return "po", "", "/".join(parts[:-1] + [fn])  # resolved to a group later
        return _by_path(rel, "po", ext)

    if ext == ".json":
        if fn in ("package.json", "package-lock.json", "tsconfig.json", "composer.json"):
            return None
        return _by_path(rel, "json", ext)

    if ext in (".yml", ".yaml"):
        hit = _by_path(rel, "yaml", ext)
        if hit:
            return hit
        root_loc = yamlfile.root_locale(abspath)
        if root_loc and locales.parse(root_loc):
            # config/locales/views/users.yml with an "en:" root and no locale in the name
            return "yaml", root_loc, rel + "#{loc}"
    return None


def _looks_like_android_strings(path: str) -> bool:
    try:
        with open(path, "rb") as f:
            head = f.read(4096)
    except OSError:
        return False
    return b"<resources" in head and (b"<string" in head or b"<plurals" in head)


def _by_path(rel: str, fmt: str, ext: str) -> Optional[Tuple[str, str, str]]:
    parts = rel.split("/")
    stem = parts[-1][: -len(ext)]
    # en.json, en-US.json, de.i18n.json, devise.en.yml, messages.fr.json, de_DE.po
    dots = stem.split(".")
    for idx in ([0, len(dots) - 1] if len(dots) > 1 else [0]):
        loc = locales.parse(dots[idx])
        if loc:
            dots2 = list(dots)
            dots2[idx] = "{loc}"
            return fmt, loc, "/".join(parts[:-1] + [".".join(dots2) + ext])
    # locales/en/common.json, locale/de/LC_MESSAGES/django.po
    for idx in range(len(parts) - 2, -1, -1):
        loc = locales.parse(parts[idx])
        if loc:
            p2 = list(parts)
            p2[idx] = "{loc}"
            return fmt, loc, "/".join(p2)
    return None


def package_libraries(root: str, rel_dir: str) -> set:
    """Interpolation library families declared in package.json files from rel_dir up to root."""
    fams = set()
    d = rel_dir
    while True:
        pj = os.path.join(root, d, "package.json")
        if os.path.isfile(pj):
            try:
                with open(pj, encoding="utf-8") as f:
                    data = json.load(f)
            except (ValueError, OSError):
                data = {}
            deps = {}
            for k in ("dependencies", "devDependencies", "peerDependencies"):
                if isinstance(data.get(k), dict):
                    deps.update(data[k])
            for name in deps:
                for fam, rx in LIB_FAMILIES.items():
                    if rx.match(name):
                        fams.add(fam)
        if not d:
            break
        d = os.path.dirname(d)
    return fams


def guess_syntax(texts: List[str], fams: set, fmt: str, template: str, root: str) -> str:
    if fmt in ("android", "apple"):
        return "printf"
    if fmt == "properties":
        return "javamf"
    if fmt == "po":
        return "icu" if "icu" in fams and len(fams) == 1 else "gettext"
    c = Counter()
    for t in texts:
        c["i18next"] += len(re.findall(r"\{\{[^{}]+\}\}", t))
        c["rails"] += len(re.findall(r"%\{\w+\}", t)) + len(re.findall(r"%<\w+>", t))
        c["single"] += len(re.findall(r"(?<![{%$])\{\s*\w+\s*(?:,[^{}]*)?\}(?!\})", t))
        c["icu_complex"] += len(re.findall(r"\{\s*\w+\s*,\s*(?:plural|select|selectordinal)\s*,", t))
        c["vue_link"] += len(re.findall(r"@:[\w.]", t))
    if fmt == "yaml" and (c["rails"] or "config/locales" in template or os.path.exists(os.path.join(root, "Gemfile"))):
        if c["rails"] >= c["i18next"]:
            return "rails"
    if len(fams) == 1:
        return next(iter(fams))
    if c["icu_complex"] and "vue" not in fams:
        return "icu"
    if fams:
        if c["i18next"] >= c["single"] and "i18next" in fams:
            return "i18next"
        for fam in ("icu", "vue", "i18next"):
            if fam in fams:
                return fam
    if c["rails"] > max(c["i18next"], c["single"]):
        return "rails"
    if c["vue_link"]:
        return "vue"
    if c["single"] > c["i18next"]:
        return "icu"
    return "i18next"


def discover(root: str, source_locale: str = "en", syntax: Optional[str] = None,
             only_formats: Optional[set] = None) -> Tuple[List[Group], List[str]]:
    """Return (groups, notes)."""
    root = os.path.abspath(root)
    by_template: Dict[str, Dict[str, Tuple[str, str]]] = defaultdict(dict)  # template -> loc -> (fmt, rel)
    fmt_of: Dict[str, str] = {}
    pots: Dict[str, str] = {}  # dir -> pot rel path
    notes: List[str] = []
    for path in walk(root):
        rel = os.path.relpath(path, root).replace(os.sep, "/")
        hit = classify(rel, path)
        if not hit:
            continue
        fmt, loc, template = hit
        if only_formats and fmt not in only_formats:
            continue
        if fmt == "po" and rel.endswith(".pot"):
            pots.setdefault(os.path.dirname(rel), rel)
            continue
        by_template[template][loc] = (fmt, rel)
        fmt_of[template] = fmt

    # sibling locales for directory style templates (locales/{loc}/ns.json)
    prefix_locales: Dict[str, set] = defaultdict(set)
    for template, locs in by_template.items():
        if "/{loc}/" in template or template.startswith("{loc}/"):
            prefix_locales[template.split("{loc}")[0]].update(locs)

    groups: List[Group] = []
    for template in sorted(by_template):
        locs = by_template[template]
        fmt = fmt_of[template]
        if fmt in ("android", "properties") and "" in locs:
            src = ""
        else:
            src = locales.pick_source([l for l in locs if l], source_locale)
            if src is None and fmt == "apple" and "Base" in locs:
                src = "Base"
        pot = None
        if fmt == "po":
            pot = _find_pot(template, pots)
        if src is None and not pot:
            if len(locs) > 1 and fmt != "po":
                notes.append(f"skipped {template}: no '{source_locale}' file among {len(locs)} locales")
            elif fmt != "po":
                continue
        if len(locs) < 2 and not pot and fmt != "po":
            continue
        g = Group(template=template, fmt=fmt, syntax="", source_locale=src if src is not None else "")
        for loc, (f, rel) in sorted(locs.items()):
            g.catalogs[loc] = formats.load(f, os.path.join(root, rel), rel, loc or source_locale)
        if pot and (src is None or src not in g.catalogs):
            cat = formats.load("po", os.path.join(root, pot), pot, source_locale)
            g.catalogs["__pot__"] = cat
            g.source_locale = "__pot__"
        if "{loc}" in template and template.split("{loc}")[0] in prefix_locales and src is not None:
            g.expected_locales = sorted(prefix_locales[template.split("{loc}")[0]])
        texts = [e.value for e in g.source.entries.values()] if g.source else []
        fams = package_libraries(root, os.path.dirname(template.split("{loc}")[0].rstrip("/")))
        g.syntax = syntax or guess_syntax(texts, fams, fmt, template, root)
        groups.append(g)
    return groups, notes


def _find_pot(template: str, pots: Dict[str, str]) -> Optional[str]:
    """locale/{loc}/LC_MESSAGES/django.po -> locale/django.pot (or any pot next to the locale dirs)."""
    domain = os.path.splitext(os.path.basename(template))[0]
    base = template.split("{loc}")[0].rstrip("/")
    for d in (base, os.path.dirname(base), os.path.join(base, "templates")):
        if d in pots:
            cand = pots[d]
            if domain in ("{loc}",) or os.path.splitext(os.path.basename(cand))[0] in (domain, "messages") \
                    or len([p for p in pots if p == d]) == 1:
                return cand
    return None
