"""End-to-end checks against the fixture repos: every planted bug is found (true
positives) and every correct string stays silent (true negatives)."""
import pytest

from conftest import audit, pick
from i18n_audit import checks, detect


def kinds(findings, locale, key):
    return sorted(f.kind for f in pick(findings, locale, key))


# ------------------------------------------------------------------ i18next (nested, namespaces)
@pytest.fixture(scope="module")
def i18next():
    return audit("i18next")


def test_i18next_detected(i18next):
    groups, _ = i18next
    assert {(g.template, g.syntax) for g in groups} == {
        ("locales/{loc}/common.json", "i18next"), ("locales/{loc}/auth.json", "i18next")}


@pytest.mark.parametrize("locale,key,kind", [
    ("de", "greeting", "wrong_syntax"),
    ("de", "welcome", "placeholder_mismatch"),
    ("de", "brand", "placeholder_mismatch"),
    ("de", "terms", "tag_mismatch"),
    ("de", "bold", "tag_mismatch"),
    ("de", "items_one", "plural_placeholder"),
    ("de", "removedLongAgo", "stale_key"),
    ("de", "onlyInSource", "missing_key"),
    ("de", "nested", "duplicate_key"),
    ("fr", "greeting", "unbalanced_braces"),
])
def test_i18next_true_positives(i18next, locale, key, kind):
    assert kinds(i18next[1], locale, key) == [kind]


def test_i18next_details(i18next):
    f = pick(i18next[1], "de", "greeting")[0]
    assert f.file == "locales/de/common.json" and f.line == 2 and f.severity == "error"
    assert f.source_text == "Hello {{name}}" and f.locale_text == "Hallo {name}"
    assert "{name} should be {{name}}" in f.message
    dup = pick(i18next[1], "de", "nested")[0]
    assert dup.severity == "error" and "top-level section" in dup.message
    tag = pick(i18next[1], "de", "terms")[0]
    assert "Trans component" in tag.message and "<1>" in tag.message and "<2>" in tag.message
    assert pick(i18next[1], "de", "items_one")[0].severity == "info"


def test_i18next_missing_file(i18next):
    (f,) = pick(i18next[1], kind="missing_file")
    assert f.locale == "fr" and f.file == "locales/fr/auth.json"


@pytest.mark.parametrize("locale,key", [
    ("de", "nested.deep.title"),  # the later duplicate block wins and is correct
    ("de", "link"), ("de", "prompt"), ("de", "plain"), ("de", "items_other"),
    ("ru", "items_few"), ("ru", "items_many"),  # plural forms the source lacks are not stale
    ("ru", "greeting"), ("ru", "terms"), ("ru", "bold"),
    ("fr", "welcome"), ("fr", "terms"),
])
def test_i18next_true_negatives(i18next, locale, key):
    assert pick(i18next[1], locale, key) == []


def test_i18next_clean_locale(i18next):
    assert pick(i18next[1], "ru") == []


# ------------------------------------------------------------------ i18next flat
def test_i18next_flat():
    groups, findings = audit("i18next_flat")
    assert groups[0].syntax == "i18next"
    assert [(f.locale, f.key, f.kind) for f in findings] == [("es", "nav.greeting", "placeholder_mismatch")]
    assert "renamed or translated" in findings[0].message


def test_clean_repo_has_no_findings():
    _, findings = audit("clean")
    assert findings == []


# ------------------------------------------------------------------ ICU (react-intl)
@pytest.fixture(scope="module")
def icu_findings():
    groups, findings = audit("icu")
    assert groups[0].syntax == "icu"
    return findings


@pytest.mark.parametrize("locale,key,kind,text", [
    ("fr", "inbox", "invalid_icu", "missing the required 'other'"),
    ("fr", "greeting", "wrong_syntax", "{{name}} should be {name}"),
    ("fr", "invite", "invalid_icu", "unclosed argument"),
    ("fr", "price", "invalid_icu", "invalid argument type 'numbre'"),
    ("fr", "apostrophe", "placeholder_mismatch", "apostrophe quoted"),
    ("fr", "rich", "tag_mismatch", "</link>"),
    ("it", "greeting", "placeholder_mismatch", "apostrophe quoted"),
    ("it", "invite", "placeholder_mismatch", "unexpected {progetto}"),
    ("de", "gender", "invalid_icu", "select argument 'gender'"),
])
def test_icu_true_positives(icu_findings, locale, key, kind, text):
    (f,) = pick(icu_findings, locale, key)
    assert f.kind == kind and text in f.message


@pytest.mark.parametrize("locale,key", [
    ("fr", "nested"),  # dropping {folder} in a non-other plural branch is allowed
    ("fr", "rank"), ("fr", "day"), ("fr", "escaped"), ("fr", "gender"),
    ("it", "apostrophe"),  # "l'elemento {thing}": apostrophe before a letter is literal
    ("it", "rank"),  # selectordinal with only "other" is valid
    ("it", "escaped"),  # source and translation both quote '{braces}'
    ("it", "rich"), ("it", "nested"), ("it", "price"),
    ("de", "apostrophe"), ("de", "rank"), ("de", "day"),
])
def test_icu_true_negatives(icu_findings, locale, key):
    assert pick(icu_findings, locale, key) == []


def test_icu_invalid_source_is_reported(write_tree):
    root = write_tree({
        "package.json": '{"dependencies": {"react-intl": "6"}}',
        "lang/en.json": '{"a": "{n, plural, one {#}}", "b": "ok {x}"}',
        "lang/de.json": '{"a": "{n, plural, one {#}}", "b": "ok {x}"}',
    })
    findings = checks.run(detect.discover(root)[0])
    assert [(f.locale, f.key, f.kind) for f in findings] == [("en", "a", "invalid_icu")]


def test_icu_unknown_plural_category(write_tree):
    root = write_tree({
        "package.json": '{"dependencies": {"@formatjs/intl": "2"}}',
        "lang/en.json": '{"a": "{n, plural, one {# day} other {# days}}"}',
        "lang/fr.json": '{"a": "{n, plural, one {# jour} autre {# jours} other {# jours}}"}',
    })
    (f,) = checks.run(detect.discover(root)[0])
    assert f.kind == "invalid_icu" and f.severity == "warning" and "'autre'" in f.message


def test_icu_quoted_tags_are_literal_text(write_tree):
    # Regression (umami): '<head>...</head>' is quoted literal text in formatjs,
    # so a translation without it is not a tag mismatch.
    root = write_tree({
        "package.json": '{"dependencies": {"react-intl": "6"}}',
        "lang/en.json": '{"a": "Place the code in the \'<head>...</head>\' section", "b": "<b>{x}</b> \'<i>\'"}',
        "lang/de.json": '{"a": "Tracking-Code", "b": "{x}"}',
    })
    findings = checks.run(detect.discover(root)[0])
    assert [(f.key, f.kind, f.message) for f in findings] == [
        ("b", "tag_mismatch", "Tags differ: missing </b>, <b>")]
    assert findings[0].source_text == "<b>{x}</b> '<i>'"


# ------------------------------------------------------------------ vue-i18n
def test_vue():
    groups, findings = audit("vue")
    assert groups[0].syntax == "vue"
    got = {(f.locale, f.key, f.kind) for f in findings}
    assert got == {
        ("de", "hello", "wrong_syntax"),
        ("de", "linked", "placeholder_mismatch"),
        ("es", "hello", "placeholder_mismatch"),
    }
    # negatives: reordered list args, literal {'@'}, pipe plurals
    assert pick(findings, key="list") == pick(findings, key="email") == pick(findings, key="apples") == []


# ------------------------------------------------------------------ Rails YAML
def test_rails():
    groups, findings = audit("rails")
    assert groups[0].syntax == "rails" and groups[0].fmt == "yaml"
    got = {(f.locale, f.key, f.kind) for f in findings}
    assert got == {
        ("de", "greeting", "wrong_syntax"),
        ("de", "inbox.one", "plural_placeholder"),
        ("de", "account.description", "placeholder_mismatch"),
        ("de", "old_key", "stale_key"),
        ("de", "only_en", "missing_key"),
        ("de", "account", "duplicate_key"),
    }
    assert pick(findings, "fr") == []
    f = pick(findings, "de", "account.description")[0]
    assert f.line == 8 and "%{konto}" in f.message


# ------------------------------------------------------------------ gettext
def test_gettext():
    groups, findings = audit("gettext")
    g = groups[0]
    assert g.fmt == "po" and g.source.path == "locale/django.pot"
    got = {(f.locale, f.key, f.kind) for f in findings}
    assert got == {
        ("de", "Hello %(name)s", "placeholder_mismatch"),
        ("de", "Welcome {user}", "placeholder_mismatch"),
        ("de", "%(count)d file[0]", "plural_placeholder"),
        ("de", "Read the <a>guide</a>", "tag_mismatch"),
        ("de", "Untranslated here", "missing_key"),
        ("fr", "Untranslated here", "duplicate_key"),
        ("ja", "Welcome {user}", "missing_key"),
        ("ja", "Read the <a>guide</a>", "missing_key"),
        ("ja", "Untranslated here", "missing_key"),
    }
    # negatives: positional reorder (%1$s/%2$d), fuzzy entries, msgctxt, ja single plural form
    assert pick(findings, key="%s uploaded %d files") == []
    assert pick(findings, key="Old %(thing)s") == []
    assert pick(findings, key="button|Open") == []
    assert pick(findings, "ja", "%(count)d file[1]") == []
    assert pick(findings, "de", "Untranslated here")[0].severity == "info"


def test_gettext_without_template(write_tree):
    root = write_tree({
        "po/de.po": '#, c-format\nmsgid "%s files"\nmsgstr "Dateien"\n\nmsgid "ok"\nmsgstr "gut"\n',
        "po/fr.po": '#, c-format\nmsgid "%s files"\nmsgstr "%s fichiers"\n',
    })
    findings = checks.run(detect.discover(root)[0])
    assert [(f.locale, f.key, f.kind) for f in findings] == [("de", "%s files", "placeholder_mismatch")]


# ------------------------------------------------------------------ Android
def test_android():
    groups, findings = audit("android")
    assert groups[0].fmt == "android" and set(groups[0].catalogs) == {"", "de", "pt-BR", "fr"}
    got = {(f.locale, f.key, f.kind) for f in findings}
    assert got == {
        ("de", "welcome", "placeholder_mismatch"),
        ("de", "cant_connect", "android_apostrophe"),
        ("de", "songs:one", "plural_placeholder"),
        ("de", "only_default", "duplicate_key"),
        ("pt-BR", "removed", "stale_key"),
        ("fr", "", "parse_error"),
    }
    # negatives: reordered %2$d/%1$s, extra plural quantity "many", translatable=false key, %% escapes,
    # apostrophe inside double quotes, values-night ignored
    assert pick(findings, "pt-BR", "welcome") == pick(findings, "pt-BR", "songs:many") == []
    assert pick(findings, key="app_name") == pick(findings, key="percent") == pick(findings, key="quoted") == []
    assert "%2$d" in pick(findings, "de", "welcome")[0].message


# ------------------------------------------------------------------ Apple
def test_apple():
    groups, findings = audit("apple")
    assert [g.template for g in groups] == ["App/{loc}.lproj/Localizable.strings"]
    got = {(f.locale, f.key, f.kind) for f in findings}
    assert got == {
        ("de", "greeting", "placeholder_mismatch"),
        ("de", "only_en", "missing_key"),
        ("de", "stale", "stale_key"),
        ("de", "plain", "duplicate_key"),
        ("fr", "", "parse_error"),
    }
    assert "missing %@" in pick(findings, "de", "greeting")[0].message
    assert pick(findings, "de", "files") == []  # %2$ld / %1$@ reordering is fine


# ------------------------------------------------------------------ Java properties
def test_properties():
    groups, findings = audit("properties")
    assert groups[0].syntax == "javamf" and groups[0].source_locale == ""
    got = {(f.locale, f.key, f.kind) for f in findings}
    assert got == {
        ("it", "user.deleted", "placeholder_mismatch"),
        ("de", "printf.style", "placeholder_mismatch"),
        ("de", "multi.line", "placeholder_mismatch"),
        ("de", "only.default", "missing_key"),
        ("fr", "plain", "duplicate_key"),
    }
    assert "apostrophe quoted" in pick(findings, "it", "user.deleted")[0].message
    # negatives: '' escaped apostrophe, choice format, continuation lines
    assert pick(findings, "fr", "user.deleted") == pick(findings, key="files") == []
    assert pick(findings, "it", "multi.line") == []


# ------------------------------------------------------------------ unit helpers
@pytest.mark.parametrize("key,fmt,expected", [
    ("items_one", "json", ("items", "one")),
    ("items_ordinal_few", "json", ("items", "few")),
    ("items_plural", "json", ("items", "plural")),
    ("inbox.one", "yaml", ("inbox", "one")),
    ("songs:many", "android", ("songs", "many")),
    ("%d file[2]", "po", ("%d file", "2")),
    ("someone", "json", None),
    ("done", "yaml", None),
])
def test_plural_base(key, fmt, expected):
    assert checks.plural_base(key, fmt) == expected


def test_ref_key_maps_extra_plural_forms():
    from i18n_audit.model import Entry
    src = {"items_one": Entry("items_one", "x"), "items_other": Entry("items_other", "y"),
           "n.other": Entry("n.other", "z"), "%d f[0]": Entry("%d f[0]", "a"), "%d f[1]": Entry("%d f[1]", "b")}
    assert checks.ref_key("items_few", src, "json") == "items_other"
    assert checks.ref_key("items_one", src, "json") == "items_one"
    assert checks.ref_key("n.many", src, "yaml") == "n.other"
    assert checks.ref_key("%d f[3]", src, "po") == "%d f[1]"
    assert checks.ref_key("unknown", src, "json") is None
