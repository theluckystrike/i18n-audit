import os

import pytest

from i18n_audit import checks, codescan, detect

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def fixture_path(name):
    return os.path.join(FIXTURES, name)


def audit(name, source_locale="en", code_scan=False, syntax=None):
    root = fixture_path(name)
    groups, _ = detect.discover(root, source_locale, syntax)
    findings = checks.run(groups)
    if code_scan:
        findings += codescan.scan(root, groups, source_locale)
    return groups, findings


def pick(findings, locale=None, key=None, kind=None):
    return [f for f in findings
            if (locale is None or f.locale == locale)
            and (key is None or f.key == key)
            and (kind is None or f.kind == kind)]


@pytest.fixture
def write_tree(tmp_path):
    """Create a small repo from {relative path: content}."""
    def make(files):
        for rel, content in files.items():
            p = tmp_path / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
        return str(tmp_path)
    return make
