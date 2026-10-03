import pytest

from conftest import fixture_path
from i18n_audit import tms


@pytest.mark.parametrize("files,name", [
    ({"crowdin.yml": "files: []"}, "Crowdin"),
    ({"apps/web/crowdin.yaml": "files: []"}, "Crowdin"),
    ({".lingohub.yml": "x"}, "LingoHub"),
    ({"i18n.json": '{"$schema": "https://lingo.dev/schema/i18n.json"}'}, "Lingo.dev"),
    ({"apps/web/i18n.lock": "checksums: {}"}, "Lingo.dev"),
    ({".tolgeerc": "{}"}, "Tolgee"),
    ({"lokalise.yml": "x"}, "Lokalise"),
    ({".tx/config": "[main]"}, "Transifex"),
    ({"transifex.yml": "x"}, "Transifex"),
    ({".phrase.yml": "x"}, "Phrase"),
])
def test_detects(write_tree, files, name):
    found = tms.detect(write_tree(files))
    assert [n for n, _ in found] == [name]
    assert name in tms.note(found)
    assert "may be rejected" in tms.note(found)


@pytest.mark.parametrize("files", [
    {"i18n.json": '{"locales": ["en"]}'},  # i18n.json that is not a Lingo.dev config
    {"locales/en.json": "{}"},
    {"node_modules/pkg/crowdin.yml": "x"},
    {"a/b/c/d/crowdin.yml": "x"},  # deeper than the search depth
])
def test_no_false_positives(write_tree, files):
    assert tms.detect(write_tree(files)) == []
    assert tms.note([]) == ""


def test_fixture():
    assert tms.detect(fixture_path("tms")) == [("Crowdin", "crowdin.yml")]
    assert tms.detect(fixture_path("i18next")) == []
