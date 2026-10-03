from conftest import audit, pick
from i18n_audit import checks, codescan, detect


def scan(root):
    groups, _ = detect.discover(root)
    return codescan.scan(root, groups)


def test_fixture_code_scan():
    _, findings = audit("i18next", code_scan=True)
    found = pick(findings, kind="missing_in_source")
    assert {(f.file, f.line, f.key) for f in found} == {
        ("src/App.tsx", 8, "dashboard.emptyState"),
        ("src/App.tsx", 12, "auth:signup"),
    }
    assert all(f.severity == "error" for f in found)


def test_code_scan_patterns(write_tree):
    root = write_tree({
        "locales/en.json": '{"known": "K", "items_one": "1", "items_other": "n", "group": {"a": "A"}}',
        "locales/de.json": '{"known": "K"}',
        "src/a.js": "\n".join([
            "t('known')",
            't("missing.one")',
            "i18n.t('missing.two')",
            "i18next.t(`missing.three`)",
            "this.$t('missing.four')",
            "$t('known')",
            "t('items', { count: 2 })",
            "t('group')",
            "t(`dynamic.${x}`)",
            "t('a' + b)",
            "format('not.a.call')",
            "test('also not a call')",
            "<Trans i18nKey=\"missing.five\" />",
            "intl.formatMessage({ id: 'missing.six' })",
            "<FormattedMessage id=\"known\" />",
            "$tc('missing.seven', 2)",
            "t('.relative')",
        ]),
        "src/a.test.js": "t('ignored.in.tests')",
        "node_modules/x/index.js": "t('ignored.vendor')",
    })
    keys = [f.key for f in scan(root)]
    assert keys == ["missing.one", "missing.two", "missing.three", "missing.four", "missing.seven",
                    "missing.five", "missing.six"]


def test_code_scan_namespaces_and_key_prefix(write_tree):
    root = write_tree({
        "locales/en/common.json": '{"save": "Save"}',
        "locales/en/admin.json": '{"users": {"title": "Users"}}',
        "locales/de/common.json": '{"save": "Speichern"}',
        "locales/de/admin.json": '{"users": {"title": "Benutzer"}}',
        "src/A.tsx": "\n".join([
            "const { t } = useTranslation('admin', { keyPrefix: 'users' });",
            "t('title');",
            "t('subtitle');",
            "t('common:save');",
            "t('common:delete');",
            "t('admin:users.title');",
        ]),
    })
    assert [f.key for f in scan(root)] == ["subtitle", "common:delete"]


def test_code_scan_ruby(write_tree):
    root = write_tree({
        "config/locales/en.yml": "en:\n  users:\n    title: Users\n",
        "config/locales/de.yml": "de:\n  users:\n    title: Benutzer\n",
        "app/views/users/index.html.erb": "<%= t('users.title') %> <%= t('users.missing') %> <%= t('.lazy') %>",
        "app/models/user.rb": "I18n.t('users.gone')",
    })
    assert sorted(f.key for f in scan(root)) == ["users.gone", "users.missing"]


def test_code_scan_without_catalogs_is_silent(write_tree):
    root = write_tree({"src/a.js": "t('anything')"})
    assert scan(root) == []


def test_code_scan_off_by_default():
    _, findings = audit("i18next")
    assert pick(findings, kind="missing_in_source") == []
    assert checks  # imported for side effects only
