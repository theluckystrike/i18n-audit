import pytest

from i18n_audit import icu

VALID = [
    "",
    "Plain text",
    "Hello {name}",
    "{ name }",
    "{a} and {b} and {a}",
    "You have {count, plural, one {# message} other {# messages}}",
    "{count, plural, =0 {none} =1 {one} other {#}}",
    "{count, plural, offset:1 =0 {nobody} one {you and # other} other {you and # others}}",
    "{gender, select, female {She} male {He} other {They}}",
    "{place, selectordinal, one {#st} two {#nd} few {#rd} other {#th}}",
    "{n, plural, one {{g, select, female {her file} other {their file}}} other {# files of {owner}}}",
    "{amount, number}",
    "{amount, number, ::currency/EUR}",
    "{amount, number, percent}",
    "{d, date, short} at {d, time, ::hhmm}",
    "{d, date, ::yyyyMMdd}",
    # apostrophes (ICU / formatjs: only special before { } or # in plural)
    "Don't worry",
    "It''s {name}",
    "Use '{literal}' braces",
    "'{'",
    "'}' closes",
    "{n, plural, one {'#' is a hash} other {# items}}",
    "unterminated quote '{ runs to the end",
    "{count, plural, one {# item} other {# items}} in {list}",
    "{count, plural,\n  one {# item}\n  other {# items}\n}",
    "Rich <b>text</b> with {arg}",
    "{0} positional",
    "{product.name}",
    "{user_name}",
]

INVALID = [
    ("{", "unclosed argument"),
    ("Hello {name", "unclosed argument"),
    ("Hello name}", "unmatched closing brace"),
    ("{}", "empty argument"),
    ("{ }", "empty argument"),
    ("{{name}}", "malformed argument name"),
    ("{name, numbre}", "invalid argument type"),
    ("{count, plural, one {# item}}", "missing the required 'other' option"),
    ("{gender, select, male {He} female {She}}", "missing the required 'other' option"),
    ("{count, plural, one {# item} other {# items}", "unclosed plural argument"),
    ("{count, plural, one {# item other {# items}}", "malformed argument name"),
    ("{count, plural one {# item} other {# items}}", "expected ','"),
    ("{count, plural, one # item other # items}", "expected '{'"),
    ("{count, plural, one {a} one {b} other {c}}", "duplicate selector"),
    ("{count, plural, other {a} other {b}}", "duplicate selector"),
    ("{count, plural, }", "has no options"),
    ("{name, }", "missing argument type"),
    ("{name, number, ::currency/EUR", "unclosed argument"),
    ("{name x}", "unexpected character"),
    ("{n, choice, 0#none|1#one}", "invalid argument type"),
]


@pytest.mark.parametrize("msg", VALID)
def test_valid_messages_parse(msg):
    icu.parse(msg)
    assert icu.is_valid(msg)


@pytest.mark.parametrize("msg,reason", INVALID)
def test_invalid_messages_raise(msg, reason):
    with pytest.raises(icu.ICUSyntaxError) as e:
        icu.parse(msg)
    assert reason in e.value.reason
    assert not icu.is_valid(msg)


def test_error_offset_points_at_problem():
    with pytest.raises(icu.ICUSyntaxError) as e:
        icu.parse("Hello name}")
    assert e.value.offset == 10


def test_ast_shape():
    nodes = icu.parse("Hi {n, plural, offset:1 =0 {none} other {# and {who}}}!")
    assert isinstance(nodes[0], icu.Text) and nodes[0].value == "Hi "
    arg = nodes[1]
    assert arg.name == "n" and arg.type == "plural" and arg.offset == 1
    assert list(arg.options) == ["=0", "other"]
    other = arg.options["other"]
    assert isinstance(other[0], icu.Pound)
    assert isinstance(other[2], icu.Argument) and other[2].name == "who"
    assert nodes[2].value == "!"


def test_simple_arg_style_kept():
    (arg,) = icu.parse("{v, number, ::currency/EUR}")
    assert arg.type == "number" and arg.style == "::currency/EUR"


def test_apostrophe_icu_mode():
    (t,) = icu.parse("It''s")
    assert t.value == "It's"
    (t,) = icu.parse("Don't")
    assert t.value == "Don't"
    nodes = icu.parse("'{name}' and {real}")
    assert nodes[0].value == "{name} and "
    assert nodes[1].name == "real"


def test_hash_is_literal_outside_plural_and_quoted_inside():
    (t,) = icu.parse("Issue #42")
    assert t.value == "Issue #42"
    (arg,) = icu.parse("{n, plural, other {'#' {n}}}")
    assert isinstance(arg.options["other"][0], icu.Text)
    assert arg.options["other"][0].value == "# "


def test_pound_inside_select_is_text():
    (arg,) = icu.parse("{g, select, other {#}}")
    assert isinstance(arg.options["other"][0], icu.Text)


def test_java_mode_single_apostrophe_quotes():
    names, _ = icu.arguments("L'utente {0} e {1}", "java")
    assert names == set()
    names, _ = icu.arguments("L''utente {0}", "java")
    assert names == {"0"}
    # the same text is fine in ICU mode
    names, _ = icu.arguments("L'utente {0}", "icu")
    assert names == {"0"}


def test_java_choice_format():
    icu.parse("{0,choice,0#no files|1#one file|1<{0,number,integer} files}", "java")


def test_arguments_required_vs_branch_only():
    names, req = icu.arguments(
        "{count, plural, =0 {No files in {folder}} one {One file} other {# files in {folder} by {owner}}}"
        " for {user}")
    assert names == {"count", "folder", "owner", "user"}
    assert req == {"count", "folder", "owner", "user"}
    names, req = icu.arguments("{count, plural, one {only {a}} other {many}}")
    assert names == {"count", "a"}
    assert req == {"count"}


def test_select_branches_are_required():
    _, req = icu.arguments("{g, select, female {{x}} other {{y}}}")
    assert req == {"g", "x", "y"}


def test_nested_selectordinal_inside_select():
    _, req = icu.arguments("{g, select, other {{p, selectordinal, one {#st {a}} other {#th {b}}}}}")
    assert req == {"g", "p", "b"}


def test_unknown_plural_selectors():
    assert icu.unknown_plural_selectors("{n, plural, one {a} autre {b} other {c}}") == ["autre"]
    assert icu.unknown_plural_selectors("{n, plural, =5 {a} few {b} other {c}}") == []
    assert icu.unknown_plural_selectors("{g, select, autre {a} other {c}}") == []


def test_literal_braces():
    assert icu.literal_braces("Ciao '{name}'") == ["name"]
    assert icu.literal_braces("Ciao {name}") == []
    assert icu.literal_braces("{n, plural, other {'{x}' #}}") == ["x"]
    assert icu.literal_braces("L'utente {0} il {1,date,short}", "java") == ["0", "1"]


def test_apostrophe_before_angle_bracket_quotes():
    # formatjs: '<' and '>' start quoted text, so '<'{name}'>' keeps {name} an argument
    names, _ = icu.arguments("'<'{name}'>'")
    assert names == {"name"}
    assert "".join(n.value for n in icu.parse("'<b>' tag") if isinstance(n, icu.Text)) == "<b> tag"


def test_strip_quoted():
    assert icu.strip_quoted("place it in '<head>...</head>' now") == "place it in  now"
    assert icu.strip_quoted("It''s <b>{x}</b>") == "It's <b>{x}</b>"
    assert icu.strip_quoted("Don't <b>x</b>") == "Don't <b>x</b>"
    assert icu.strip_quoted("L'utente <b>", "java") == "L"
