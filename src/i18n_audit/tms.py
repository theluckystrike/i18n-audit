"""Detect translation management systems (TMS) that own the locale files."""
from __future__ import annotations

import json
import os
from typing import List, Tuple

# (name, relative paths that indicate it)
MARKERS = [
    ("Crowdin", ["crowdin.yml", "crowdin.yaml", ".crowdin.yml", ".crowdin.yaml", "crowdin.json"]),
    ("LingoHub", ["lingohub.yml", "lingohub.yaml", ".lingohub.yml", ".lingohub.yaml", "lingohub.json"]),
    ("Lingo.dev", ["i18n.lock"]),
    ("Tolgee", [".tolgeerc", ".tolgeerc.json", ".tolgeerc.yml", ".tolgeerc.yaml", "tolgee.config.js",
                "tolgee.config.ts", "tolgee.config.json", ".tolgee"]),
    ("Lokalise", ["lokalise.yml", "lokalise.yaml", ".lokalise.yml", ".lokalise.yaml", "lokalise.json",
                  "lokalise.config.json"]),
    ("Transifex", [".tx/config", "transifex.yml", "transifex.yaml", ".transifex.yml", ".transifex.yaml"]),
    ("Phrase", [".phrase.yml", ".phraseapp.yml", "phrase.yml"]),
    ("Weblate", [".weblate", "weblate.ini"]),
    ("Localazy", ["localazy.json"]),
    ("POEditor", ["poeditor.yml", ".poeditor.yml"]),
]
SEARCH_DEPTH = 3


def detect(root: str) -> List[Tuple[str, str]]:
    """Return [(TMS name, path relative to root)]."""
    found = []
    root = os.path.abspath(root)
    dirs = [""]
    for depth in range(SEARCH_DEPTH):
        nxt = []
        for d in dirs:
            for name, paths in MARKERS:
                for p in paths:
                    rel = os.path.join(d, p) if d else p
                    if os.path.isfile(os.path.join(root, rel)) and (name, rel) not in found:
                        found.append((name, rel))
            # Lingo.dev config: i18n.json with a lingo.dev $schema
            rel = os.path.join(d, "i18n.json") if d else "i18n.json"
            if os.path.isfile(os.path.join(root, rel)) and _is_lingo_config(os.path.join(root, rel)):
                if ("Lingo.dev", rel) not in found:
                    found.append(("Lingo.dev", rel))
            if depth + 1 < SEARCH_DEPTH:
                try:
                    for sub in sorted(os.listdir(os.path.join(root, d) if d else root)):
                        full = os.path.join(root, d, sub)
                        if os.path.isdir(full) and not sub.startswith(".") and sub not in ("node_modules", "vendor"):
                            nxt.append(os.path.join(d, sub) if d else sub)
                except OSError:
                    pass
        dirs = nxt
    return [(n, p.replace(os.sep, "/")) for n, p in found]


def _is_lingo_config(path: str) -> bool:
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (ValueError, OSError):
        return False
    return isinstance(data, dict) and "lingo.dev" in str(data.get("$schema", ""))


def note(found: List[Tuple[str, str]]) -> str:
    if not found:
        return ""
    names = sorted({n for n, _ in found})
    where = ", ".join(p for _, p in found)
    return (f"Translations appear to be managed by {', '.join(names)} ({where}). "
            "Pull requests that edit locale files directly may be rejected or overwritten on the next sync; "
            "fix translations in the TMS or report them to the maintainers instead.")
