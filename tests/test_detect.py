import pytest

from i18n_audit import detect, locales


@pytest.mark.parametrize("code,ok", [
    ("en", True), ("en-US", True), ("en_us", True), ("pt-BR", True), ("zh-Hans", True), ("zh_Hant_TW", True),
    ("sr-Latn", True), ("es-419", True), ("fil", True), ("yue", True), ("ca@valencia", True),
    ("app", False), ("src", False), ("common", False), ("xx", False), ("EN", False), ("translation", False),
])
def test_locale_parse(code, ok):
    assert bool(locales.parse(code)) is ok


@pytest.mark.parametrize("q,loc", [
    ("de", "de"), ("pt-rBR", "pt-BR"), ("b+sr+Latn", "sr-Latn"), ("night", None), ("v21", None),
    ("sw600dp", None), ("land", None),
])
def test_android_qualifier(q, loc):
    assert locales.android_qualifier(q) == loc


def test_pick_source():
    assert locales.pick_source(["de", "en", "en-GB"], "en") == "en"
    assert locales.pick_source(["de", "en-GB", "en-US"], "en") == "en-US"
    assert locales.pick_source(["de", "en_GB"], "en") == "en_GB"
    assert locales.pick_source(["de", "fr"], "en") is None
    assert locales.pick_source(["de-DE", "en"], "de") == "de-DE"


@pytest.mark.parametrize("rel,expected", [
    ("locales/en/common.json", ("json", "en", "locales/{loc}/common.json")),
    ("public/locales/pt-BR/translation.json", ("json", "pt-BR", "public/locales/{loc}/translation.json")),
    ("src/i18n/de.json", ("json", "de", "src/i18n/{loc}.json")),
    ("lang/de.i18n.json", ("json", "de", "lang/{loc}.i18n.json")),
    ("messages/messages.fr.json", ("json", "fr", "messages/messages.{loc}.json")),
    ("config/locales/devise.en.yml", ("yaml", "en", "config/locales/devise.{loc}.yml")),
    ("config/locales/de.yml", ("yaml", "de", "config/locales/{loc}.yml")),
    ("locale/de/LC_MESSAGES/django.po", ("po", "de", "locale/{loc}/LC_MESSAGES/django.po")),
    ("po/fr.po", ("po", "fr", "po/{loc}.po")),
    ("App/de.lproj/Localizable.strings", ("apple", "de", "App/{loc}.lproj/Localizable.strings")),
    ("App/Base.lproj/Main.strings", ("apple", "Base", "App/{loc}.lproj/Main.strings")),
    ("src/main/resources/messages.properties", ("properties", "", "src/main/resources/messages{loc}.properties")),
    ("src/main/resources/messages_pt_BR.properties",
     ("properties", "pt_BR", "src/main/resources/messages{loc}.properties")),
    ("package.json", None),
    ("src/config/settings.json", None),
    ("tsconfig.json", None),
    ("docs/readme.md", None),
    ("app.properties", ("properties", "", "app{loc}.properties")),
    ("app_server.properties", ("properties", "", "app_server{loc}.properties")),
    ("error_msg.properties", ("properties", "", "error_msg{loc}.properties")),
    ("error_msg_de.properties", ("properties", "de", "error_msg{loc}.properties")),
])
def test_classify(rel, expected, tmp_path):
    assert detect.classify(rel, str(tmp_path / "nope")) == expected


def test_classify_android(tmp_path):
    xml = '<?xml version="1.0"?>\n<resources><string name="a">A</string></resources>'
    for d in ("values", "values-de", "values-pt-rBR", "values-night", "values-v21"):
        (tmp_path / d).mkdir()
        (tmp_path / d / "strings.xml").write_text(xml)
    (tmp_path / "values" / "colors.xml").write_text('<resources><color name="c">#fff</color></resources>')
    c = lambda rel: detect.classify(rel, str(tmp_path / rel))  # noqa: E731
    assert c("values/strings.xml") == ("android", "", "values{loc}/strings.xml")
    assert c("values-de/strings.xml") == ("android", "de", "values{loc}/strings.xml")
    assert c("values-pt-rBR/strings.xml")[1] == "pt-BR"
    assert c("values-night/strings.xml") is None
    assert c("values-v21/strings.xml") is None
    assert c("values/colors.xml") is None


def test_yaml_root_key_classification(tmp_path):
    p = tmp_path / "users.yml"
    p.write_text("en:\n  users:\n    title: Users\n")
    assert detect.classify("config/locales/views/users.yml", str(p)) == (
        "yaml", "en", "config/locales/views/users.yml#{loc}")


@pytest.mark.parametrize("texts,fams,fmt,expected", [
    (["Hello {{name}}"], set(), "json", "i18next"),
    (["Hello {name}"], set(), "json", "icu"),
    (["{n, plural, one {#} other {#}}"], set(), "json", "icu"),
    (["Hello {name}", "@:common.ok"], set(), "json", "vue"),
    (["Hello {name}"], {"vue"}, "json", "vue"),
    (["Hello {name}"], {"i18next"}, "json", "i18next"),
    (["Hello {{name}}"], {"icu"}, "json", "icu"),
    (["Hello %{name}"], set(), "yaml", "rails"),
    (["Hello {{name}}", "{x}"], {"i18next", "icu"}, "json", "i18next"),
    (["anything"], set(), "android", "printf"),
    (["anything"], set(), "apple", "printf"),
    (["anything"], set(), "properties", "javamf"),
    (["anything"], set(), "po", "gettext"),
    (["anything"], {"icu"}, "po", "icu"),
    ([], set(), "json", "i18next"),
])
def test_guess_syntax(texts, fams, fmt, expected, tmp_path):
    assert detect.guess_syntax(texts, fams, fmt, "x/{loc}.json", str(tmp_path)) == expected


def test_package_libraries(write_tree):
    root = write_tree({
        "package.json": '{"dependencies": {"react": "1"}}',
        "apps/web/package.json": '{"dependencies": {"next-intl": "3"}, "devDependencies": {"i18next": "1"}}',
        "apps/web/locales/en.json": "{}",
    })
    assert detect.package_libraries(root, "apps/web/locales") == {"icu", "i18next"}
    assert detect.package_libraries(root, "") == set()


def test_discover_skips_vendored_dirs_and_singletons(write_tree):
    root = write_tree({
        "node_modules/lib/locales/en.json": '{"a": "A"}',
        "node_modules/lib/locales/de.json": '{"a": "B {x}"}',
        "locales/en.json": '{"a": "A"}',
        "solo/en.json": '{"a": "A"}',
    })
    groups, notes = detect.discover(root)
    assert [g.template for g in groups] == []
    root2 = write_tree({"other/de.json": '{"a": "A"}', "other/fr.json": '{"a": "A"}'})
    groups, notes = detect.discover(root2)
    assert groups == [] and any("no 'en' file" in n for n in notes)


def test_discover_source_locale_option(write_tree):
    root = write_tree({"i18n/de-DE.json": '{"a": "Hallo {{n}}"}', "i18n/fr.json": '{"a": "Salut"}'})
    groups, _ = detect.discover(root, "de")
    assert groups[0].source_locale == "de-DE"


def test_discover_syntax_override(write_tree):
    root = write_tree({"i18n/en.json": '{"a": "Hi {{n}}"}', "i18n/de.json": '{"a": "Hallo {{n}}"}'})
    groups, _ = detect.discover(root, "en", syntax="icu")
    assert groups[0].syntax == "icu"


def test_discover_pot_source(write_tree):
    root = write_tree({
        "locale/django.pot": 'msgid "A"\nmsgstr ""\n',
        "locale/de/LC_MESSAGES/django.po": 'msgid "A"\nmsgstr "B"\n',
    })
    groups, _ = detect.discover(root)
    assert groups[0].source_locale == "__pot__"
    assert groups[0].source.path == "locale/django.pot"
