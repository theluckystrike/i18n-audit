"""Before/after examples: the "before" strings are reported, the "after"
strings are clean. The first four are the examples in README.md, taken
verbatim from public repositories; the rest are earlier audit examples."""
import os
import shutil

import pytest

from conftest import audit, fixture_path
from i18n_audit import checks, detect

CASES = [
    ("renamed", "translations/sv.json", "{bläddra}", "{browse}",
     "placeholder_mismatch", "Looks renamed or translated: the code passes {browse}"),
    ("dropped", "src/i18n/translations/fr.json", "Promotion(s) ajoutée(s)", "{{count}} promotion(s) ajoutée(s)",
     "placeholder_mismatch", "missing {{count}}"),
    ("icu_plural", "translations/pt-BR.json", "um {# usuário} outros", "one {# usuário} other",
     "invalid_icu", "missing the required 'other' option"),
    ("trans_lost", "src/i18n/translations/el.json", "- Επαναφορά", "- <0>Επαναφορά</0>",
     "tag_mismatch", "missing </0>, <0>"),
    ("whitelabel", "locales/de/common.json", "Willkommen bei Acme", "Willkommen bei {{whiteLabelText}}",
     "placeholder_mismatch", "missing {{whiteLabelText}}"),
    ("lingui", "src/locales/it/messages.po", "Eliminare '{name}'?", "Eliminare ''{name}''?",
     "placeholder_mismatch", "inside apostrophe quoted text"),
    ("trans", "public/locales/ko/auth.json", "<email>{{email}}로", "<email>{{email}}</email>로",
     "tag_mismatch", "missing </email>"),
]


@pytest.mark.parametrize("name,rel,before,after,kind,text", CASES)
def test_before_is_reported(name, rel, before, after, kind, text):
    _, findings = audit(os.path.join("readme_examples", name))
    (f,) = findings
    assert f.kind == kind and text in f.message and f.file == rel


@pytest.mark.parametrize("name,rel,before,after,kind,text", CASES)
def test_after_is_clean(tmp_path, name, rel, before, after, kind, text):
    root = tmp_path / name
    shutil.copytree(fixture_path(os.path.join("readme_examples", name)), str(root))
    p = root / rel
    content = p.read_text(encoding="utf-8")
    assert before in content
    p.write_text(content.replace(before, after), encoding="utf-8")
    assert checks.run(detect.discover(str(root))[0]) == []
