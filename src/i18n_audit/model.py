"""Core data types shared by parsers, checks and reporters."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional

ERROR = "error"
WARNING = "warning"
INFO = "info"
SEVERITY_RANK = {INFO: 0, WARNING: 1, ERROR: 2}

# kind -> (default severity, one line description). Used by the reporters and SARIF rules.
KINDS: Dict[str, tuple] = {
    "placeholder_mismatch": (ERROR, "Placeholder set differs from the source string"),
    "plural_placeholder": (INFO, "Plural form omits a placeholder the source uses (often intentional)"),
    "wrong_syntax": (ERROR, "Placeholder written in the interpolation syntax of another library"),
    "invalid_icu": (ERROR, "Message is not valid ICU MessageFormat"),
    "unbalanced_braces": (ERROR, "Interpolation braces are not balanced"),
    "tag_mismatch": (ERROR, "Rich text / Trans tags differ from the source string"),
    "missing_key": (WARNING, "Key exists in the source locale but not in this locale"),
    "missing_file": (WARNING, "Catalog file exists for the source locale but not for this locale"),
    "stale_key": (INFO, "Key exists in this locale but no longer in the source locale"),
    "duplicate_key": (WARNING, "Key defined more than once in the same file (earlier values are lost)"),
    "missing_in_source": (ERROR, "Key used in code but missing from the source locale"),
    "android_apostrophe": (ERROR, "Unescaped apostrophe in Android string resource"),
    "parse_error": (ERROR, "Locale file could not be parsed"),
}


@dataclass
class Entry:
    """One translatable string."""
    key: str
    value: str
    line: int = 0
    # optional hints from the file format (gettext flags, plural form index, ...)
    meta: Dict[str, object] = field(default_factory=dict)


@dataclass
class Catalog:
    """All entries of one locale file."""
    path: str  # relative to the scanned repo
    locale: str
    fmt: str
    entries: Dict[str, Entry] = field(default_factory=dict)
    duplicates: List[Entry] = field(default_factory=list)
    errors: List[tuple] = field(default_factory=list)  # (line, message)

    def add(self, entry: Entry, top_level: bool = False) -> None:
        if entry.key in self.entries:
            entry.meta["top_level"] = top_level
            self.duplicates.append(entry)
        self.entries[entry.key] = entry


@dataclass
class Finding:
    file: str
    line: int
    key: str
    locale: str
    kind: str
    severity: str
    message: str
    source_text: Optional[str] = None
    locale_text: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Group:
    """A set of locale files that translate the same catalog."""
    template: str  # path with {loc} in place of the locale
    fmt: str
    syntax: str
    source_locale: str
    catalogs: Dict[str, Catalog] = field(default_factory=dict)
    # locales expected for this group (sibling locales) even when their file is missing
    expected_locales: List[str] = field(default_factory=list)

    @property
    def source(self) -> Optional[Catalog]:
        return self.catalogs.get(self.source_locale)
