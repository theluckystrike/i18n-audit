import pytest

from i18n_audit.formats import android, apple, jsonfile, pofile, properties, yamlfile


def write(tmp_path, name, content, binary=False):
    p = tmp_path / name
    if binary:
        p.write_bytes(content)
    else:
        p.write_text(content, encoding="utf-8")
    return str(p)


# ---------------------------------------------------------------- JSON
def test_json_nested_and_lines(tmp_path):
    p = write(tmp_path, "en.json", '{\n  "a": {\n    "b": "B",\n    "c": ["x", "y"]\n  },\n  "n": 1,\n  "t": true\n}')
    cat = jsonfile.load(p, "en.json", "en")
    assert {k: e.value for k, e in cat.entries.items()} == {"a.b": "B", "a.c.0": "x", "a.c.1": "y"}
    assert cat.entries["a.b"].line == 3
    assert cat.entries["a.c.1"].line == 4


def test_json_flat_keys_with_dots(tmp_path):
    p = write(tmp_path, "en.json", '{"nav.home": "Home"}')
    assert list(jsonfile.load(p, "en.json", "en").entries) == ["nav.home"]


def test_json_escapes_and_bom(tmp_path):
    p = write(tmp_path, "en.json", '\ufeff{"q": "say \\"hi\\"\\n\\u00e9 \\ud83d\\ude00"}')
    assert jsonfile.load(p, "en.json", "en").entries["q"].value == 'say "hi"\n\u00e9 \U0001F600'


def test_json_duplicates(tmp_path):
    p = write(tmp_path, "en.json", '{"a": {"x": "1"},\n "b": {"y": "1", "y": "2"},\n "a": {"z": "3"}}')
    cat = jsonfile.load(p, "en.json", "en")
    dups = {(d.key, d.meta["top_level"], d.line) for d in cat.duplicates}
    assert dups == {("b.y", False, 2), ("a", True, 3)}
    assert "a.x" in cat.entries and cat.entries["b.y"].value == "2"


def test_json_no_duplicates(tmp_path):
    p = write(tmp_path, "en.json", '{"a": {"x": "1"}, "b": {"x": "1"}}')
    assert jsonfile.load(p, "en.json", "en").duplicates == []


def test_json_formatjs_extracted_format(tmp_path):
    p = write(tmp_path, "en.json",
              '{"app.title": {"defaultMessage": "Hi {name}", "description": "header"},'
              ' "ext": {"message": "Hello", "description": "chrome"}, "obj": {"message": "kept"}}')
    cat = jsonfile.load(p, "en.json", "en")
    assert {k: e.value for k, e in cat.entries.items()} == {
        "app.title": "Hi {name}", "ext": "Hello", "obj.message": "kept"}


@pytest.mark.parametrize("text", ['{"a": "x",}', '{"a" "x"}', '{"a": "x"', '{"a": \'x\'}', '{"a": "x"} extra'])
def test_json_errors(tmp_path, text):
    p = write(tmp_path, "en.json", text)
    cat = jsonfile.load(p, "en.json", "en")
    assert cat.errors and cat.errors[0][0] >= 1


# ---------------------------------------------------------------- YAML
YAML = """\
# comment
en:
  greeting: "Hello %{name}"   # trailing comment
  single: 'It''s %{x}'
  plain: Hello world # comment
  hash: Issue#1 # a comment
  colon: "a: b"
  inbox:
    one: "%{count} message"
    other: "%{count} messages"
  folded: >
    first line
    second line
  literal: |-
    line one
    line two
  days: [Sun, "Mon", 'Tue']
  list:
    - alpha
    - beta
  people:
    - name: Ann
      role: admin
  continued: this plain
    scalar continues
  empty:
  num: 3
  bool: true
  defaults: &defaults
    a: A
  derived:
    <<: *defaults
    b: B
"""


def test_yaml_rails(tmp_path):
    p = write(tmp_path, "en.yml", YAML)
    cat = yamlfile.load(p, "en.yml", "en")
    assert not cat.errors
    v = {k: e.value for k, e in cat.entries.items()}
    assert v["greeting"] == "Hello %{name}"
    assert v["single"] == "It's %{x}"
    assert v["plain"] == "Hello world"
    assert v["hash"] == "Issue#1"
    assert v["colon"] == "a: b"
    assert v["inbox.one"] == "%{count} message"
    assert v["folded"] == "first line second line\n"
    assert v["literal"] == "line one\nline two"
    assert [v["days.0"], v["days.1"], v["days.2"]] == ["Sun", "Mon", "Tue"]
    assert v["list.1"] == "beta"
    assert v["people.0.name"] == "Ann" and v["people.0.role"] == "admin"
    assert v["continued"] == "this plain scalar continues"
    assert v["defaults.a"] == "A" and v["derived.b"] == "B"
    assert "num" not in v and "bool" not in v and "empty" not in v
    assert cat.entries["greeting"].line == 3
    assert cat.entries["inbox.other"].line == 10


def test_yaml_without_root_locale(tmp_path):
    p = write(tmp_path, "de.yml", "title: Titel\nnested:\n  key: Wert\n")
    cat = yamlfile.load(p, "de.yml", "de")
    assert set(cat.entries) == {"title", "nested.key"}


def test_yaml_duplicates(tmp_path):
    p = write(tmp_path, "de.yml", "de:\n  a:\n    x: 1\n  a:\n    y: 2\n  b: x\n  c:\n    k: 1\n    k: 2\n")
    cat = yamlfile.load(p, "de.yml", "de")
    assert {(d.key, d.meta["top_level"], d.line) for d in cat.duplicates} == {("a", True, 4), ("c.k", False, 9)}


def test_yaml_quoted_escapes_and_multiline(tmp_path):
    p = write(tmp_path, "en.yml", 'en:\n  a: "tab\\there \\u00e9"\n  b: "multi\n    line"\n  c: x\n')
    cat = yamlfile.load(p, "en.yml", "en")
    assert cat.entries["a"].value == "tab\there \u00e9"
    assert cat.entries["b"].value == "multi line"
    assert cat.entries["c"].line == 5


def test_yaml_error_reported(tmp_path):
    p = write(tmp_path, "en.yml", 'en:\n  a: "unterminated\n')
    cat = yamlfile.load(p, "en.yml", "en")
    assert cat.errors


def test_yaml_root_locale(tmp_path):
    assert yamlfile.root_locale(write(tmp_path, "a.yml", "# c\n---\npt-BR:\n  a: b\n")) == "pt-BR"
    assert yamlfile.root_locale(write(tmp_path, "b.yml", "title: x\n")) is None


# ---------------------------------------------------------------- gettext
PO = r'''# Translator comment
msgid ""
msgstr ""
"Plural-Forms: nplurals=3;\n"

#: a.py:1
#, python-format
msgid "Hello %(name)s"
msgstr "Hallo %(name)s"

msgctxt "menu"
msgid "Open"
msgstr "Öffnen"

msgid ""
"multi "
"line"
msgstr ""
"mehr"
"zeilig"

#, fuzzy
msgid "Fuzzy"
msgstr "Unscharf"

msgid "%d file"
msgid_plural "%d files"
msgstr[0] "%d plik"
msgstr[1] "%d pliki"
msgstr[2] "%d plików"

#~ msgid "Gone"
#~ msgstr "Weg"
'''


def test_po_parse(tmp_path):
    p = write(tmp_path, "de.po", PO)
    cat = pofile.load(p, "de.po", "de")
    assert not cat.errors
    e = cat.entries
    assert e["Hello %(name)s"].value == "Hallo %(name)s"
    assert "python-format" in e["Hello %(name)s"].meta["flags"]
    assert e["Hello %(name)s"].line == 8
    assert e["menu|Open"].value == "Öffnen"
    assert e["multi line"].value == "mehrzeilig"
    assert e["Fuzzy"].meta["fuzzy"]
    assert [e[f"%d file[{i}]"].value for i in range(3)] == ["%d plik", "%d pliki", "%d plików"]
    assert e["%d file[2]"].meta["msgid_plural"] == "%d files"
    assert "Gone" not in e and "" not in e


def test_pot_values_are_msgids(tmp_path):
    p = write(tmp_path, "x.pot", 'msgid "A %s"\nmsgstr ""\n\nmsgid "%d x"\nmsgid_plural "%d xs"\nmsgstr[0] ""\nmsgstr[1] ""\n')
    cat = pofile.load(p, "x.pot", "en")
    assert cat.entries["A %s"].value == "A %s"
    assert cat.entries["%d x[1]"].value == "%d xs"


def test_po_duplicate(tmp_path):
    p = write(tmp_path, "de.po", 'msgid "a"\nmsgstr "1"\n\nmsgid "a"\nmsgstr "2"\n')
    cat = pofile.load(p, "de.po", "de")
    assert [d.key for d in cat.duplicates] == ["a"]


# ---------------------------------------------------------------- Android
ANDROID = """<?xml version="1.0" encoding="utf-8"?>
<resources>
    <string name="a">Can\\'t stop \\"now\\"\\n\\u00e9</string>
    <string name="b" translatable="false">Brand</string>
    <string name="c">Tap <b>here</b> &amp; go</string>
    <plurals name="songs">
        <item quantity="one">%d song</item>
        <item quantity="other">%d songs</item>
    </plurals>
    <string-array name="arr">
        <item>One</item>
        <item>Two</item>
    </string-array>
    <string name="q">"It's quoted"</string>
</resources>
"""


def test_android_parse(tmp_path):
    p = write(tmp_path, "strings.xml", ANDROID)
    cat = android.load(p, "strings.xml", "en")
    e = cat.entries
    assert e["a"].value == "Can't stop \"now\"\n\u00e9"
    assert e["a"].line == 3
    assert e["b"].meta["translatable"] is False
    assert e["c"].value == "Tap <b>here</b> & go"
    assert e["songs:other"].value == "%d songs" and e["songs:other"].line == 8
    assert e["arr[1]"].value == "Two"
    assert e["q"].value == "It's quoted"


@pytest.mark.parametrize("raw,bad", [
    ("Can't", True),
    ("Can\\'t", False),
    ('"Can\'t"', False),
    ("No apostrophe", False),
    ('"quoted" but it\'s not', True),
])
def test_android_apostrophe(raw, bad):
    assert android.unescaped_apostrophe(raw) is bad


def test_android_invalid_xml(tmp_path):
    p = write(tmp_path, "strings.xml", "<resources><string name='a'>x</resources>")
    assert android.load(p, "strings.xml", "en").errors


# ---------------------------------------------------------------- Apple
def test_apple_parse(tmp_path):
    p = write(tmp_path, "Localizable.strings",
              '/* c */\n"a" = "Hello %@";\n// c\n"b" = "say \\"hi\\"\\n";\nbare_key = "v";\n"multi" =\n  "line";\n')
    cat = apple.load(p, "Localizable.strings", "en")
    assert not cat.errors
    assert {k: e.value for k, e in cat.entries.items()} == {
        "a": "Hello %@", "b": 'say "hi"\n', "bare_key": "v", "multi": "line"}
    assert cat.entries["b"].line == 4


def test_apple_utf16(tmp_path):
    p = write(tmp_path, "Localizable.strings", '"a" = "Grüße";\n'.encode("utf-16"), binary=True)
    assert apple.load(p, "x", "de").entries["a"].value == "Grüße"


def test_apple_errors_and_duplicates(tmp_path):
    p = write(tmp_path, "Localizable.strings", '"a" = "1";\n"a" = "2";\n"b" = "x"\n"c" = "y";\n')
    cat = apple.load(p, "x", "de")
    assert [d.key for d in cat.duplicates] == ["a"]
    assert cat.errors and "missing ';'" in cat.errors[0][1]


# ---------------------------------------------------------------- properties
def test_properties_parse(tmp_path):
    p = write(tmp_path, "m.properties",
              "# comment\n! also comment\na=Hello {0}\nb : spaced\nc value\nlong=first \\\n    second\n"
              "esc=tab\\t\\u00e9 \\\\ end\nkey\\=with\\:sep=v\nempty=\n")
    cat = properties.load(p, "m.properties", "en")
    v = {k: e.value for k, e in cat.entries.items()}
    assert v == {"a": "Hello {0}", "b": "spaced", "c": "value", "long": "first second",
                 "esc": "tab\t\u00e9 \\ end", "key=with:sep": "v", "empty": ""}
    assert cat.entries["long"].line == 6


def test_properties_latin1(tmp_path):
    p = write(tmp_path, "m_de.properties", "a=Gr\xfc\xdfe\n".encode("latin-1"), binary=True)
    assert properties.load(p, "x", "de").entries["a"].value == "Grüße"


def test_properties_duplicates(tmp_path):
    p = write(tmp_path, "m.properties", "a=1\nb=2\na=3\n")
    cat = properties.load(p, "x", "en")
    assert [(d.key, d.line) for d in cat.duplicates] == [("a", 3)]
    assert cat.entries["a"].value == "3"
