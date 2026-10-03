import pytest

from i18n_audit import placeholders as ph


def toks(s, syntax):
    return ph.tokens(s, syntax)[0]


@pytest.mark.parametrize("s,expected", [
    ("Hello {{name}}", {"{{name}}"}),
    ("{{ name }}", {"{{name}}"}),
    ("{{count, number}}", {"{{count}}"}),
    ("{{- html}}", {"{{html}}"}),
    ("See $t(common.brand)", {"$t(common.brand)"}),
    ("Hello {name}", set()),
    ("100%", set()),
])
def test_i18next_tokens(s, expected):
    assert toks(s, "i18next") == expected


def test_icu_tokens_required():
    allt, req = ph.tokens("{n, plural, one {only {a}} other {#}} {b}", "icu")
    assert allt == {"{n}", "{a}", "{b}"}
    assert req == {"{n}", "{b}"}


def test_icu_tokens_invalid_message_is_empty():
    assert ph.tokens("{unclosed", "icu") == (set(), set())


@pytest.mark.parametrize("s,expected", [
    ("Hello {name}", {"{name}"}),
    ("{0} and {1}", {"{0}", "{1}"}),
    ("@:common.ok", {"@:common.ok"}),
    ("@.upper:common.ok", {"@:common.ok"}),
    ("@:(common.ok)", {"@:common.ok"}),
    ("support{'@'}example.com", set()),
    ("Hallo {{name}}", set()),
])
def test_vue_tokens(s, expected):
    assert toks(s, "vue") == expected


@pytest.mark.parametrize("s,expected", [
    ("Hello %{name}", {"%{name}"}),
    ("%<amount>.2f left", {"%<amount>"}),
    ("{name}", set()),
])
def test_rails_tokens(s, expected):
    assert toks(s, "rails") == expected


@pytest.mark.parametrize("a,b", [
    ("%s uploaded %d", "%1$s hat %2$d"),
    ("%s uploaded %d", "%2$d von %1$s"),
    ("%@ shared %ld", "%1$@ teilte %2$lld"),
    ("%d items", "%i Elemente"),
    ("%.2f km", "%f km"),
    ("Hello %(name)s", "Hallo %(name)s"),
])
def test_printf_equivalent(a, b):
    assert toks(a, "printf") == toks(b, "printf")


@pytest.mark.parametrize("a,b", [
    ("%s uploaded %d", "%d hochgeladen %s"),  # swapped without positions
    ("%1$s", "%2$s"),
    ("%(name)s", "%(nom)s"),
    ("%s", "%d"),
])
def test_printf_different(a, b):
    assert toks(a, "printf") != toks(b, "printf")


def test_printf_escaped_percent_ignored():
    assert toks("100%% done", "printf") == set()
    assert toks("100%% of %s", "printf") == {"%1$s"}


def test_printf_display_original():
    assert ph.display("%1$s", "Hello %@") == "%@"
    assert ph.display("%(name)", "Hi %(name)s") == "%(name)s"
    assert ph.display("{x}", "whatever") == "{x}"


def test_brace_tokens():
    assert toks("Welcome {user} {0} {n:.2f}", "brace") == {"{user}", "{0}", "{n}"}
    assert toks("{{literal}}", "brace") == set()


def test_javamf_tokens():
    assert toks("Deleted {0} on {1,date,short}", "javamf") == {"{0}", "{1}"}
    assert toks("L'utente {0}", "javamf") == set()
    assert toks("No args, it's fine %s", "javamf") == {"%1$s"}


def test_any_syntax_names():
    found = ph.any_syntax_names("A {{a}} B {b} C %{c} D ${d} E __e__ F %(f)s G [[g]]")
    assert found == {"a": "{{a}}", "b": "{b}", "c": "%{c}", "d": "${d}", "e": "__e__",
                     "f": "%(f)s", "g": "[[g]]"}


def test_tags_counter():
    t = ph.tags('Click <0>here</0> or <a href="x">there</a><br/>')
    assert t == {"<0>": 1, "</0>": 1, "<a>": 1, "</a>": 1, "<br/>": 1}
    assert ph.tags("a < b and c > d") == {}


@pytest.mark.parametrize("s,bad", [
    ("<b>ok</b>", []),
    ("<b>open", ["<b>"]),
    ("close</b>", ["</b>"]),
    ("<b><i>x</b></i>", ["<i>", "</i>"]),
    ("line<br>break", []),
    ("<1/> self", []),
])
def test_unbalanced_tags(s, bad):
    assert ph.unbalanced_tags(s) == bad
