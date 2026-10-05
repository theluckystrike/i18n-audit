# i18n-audit

Finds translation bugs that users actually see: dropped `{{placeholders}}`, broken ICU messages, lost `<0>Trans</0>` tags, wrong interpolation syntax, and keys the code calls but locale files lack.

It reads the locale files already in your repository, compares every translation with its source string, and reports each problem with file, line, key, locale, the source text and the translated text. Pure Python standard library, Python 3.9+, no network access, no API keys.

The checks come from an audit of 13 open source projects with locale files on 2026-10-03, which found 930 broken strings. Each example below is covered by a test in `tests/test_readme_examples.py`.

## What it catches

| Kind | Severity | Example |
| --- | --- | --- |
| `placeholder_mismatch` | error | source `Hello {{name}}`, translation `Hallo {{nom}}` or `Hallo` |
| `wrong_syntax` | error | `{name}` in an i18next project, `{{name}}` in ICU, `{name}` instead of Rails `%{name}` |
| `invalid_icu` | error | missing `other` branch, unclosed `{`, unknown argument type, translated plural keyword |
| `unbalanced_braces` | error | `Bonjour {{name}` |
| `tag_mismatch` | error | `<1>` became `<2>`, `<b>` never closed, `</link>` dropped |
| `android_apostrophe` | error | `Can't` without `\'` in `strings.xml` (aapt rejects it) |
| `parse_error` | error | invalid JSON, YAML, XML, `.strings` or `.po` syntax |
| `missing_in_source` | error | `t('dashboard.title')` in code, no such key in the source locale (`--code-scan`) |
| `duplicate_key` | error / warning | the same top-level section twice in one file: the second silently replaces the first |
| `missing_key` | warning | key exists in the source locale but not in this locale |
| `missing_file` | warning | `locales/en/auth.json` exists, `locales/fr/auth.json` does not |
| `stale_key` | info | key exists in a locale but was removed from the source |
| `plural_placeholder` | info | `items_one` says "one item" without `{{count}}` (often intentional) |

Placeholders are compared as sets, so reordering is fine (`%1$s ... %2$d` against `%2$d ... %1$s`, or `{a} {b}` against `{b} {a}`). ICU arguments that only appear in a non-`other` plural branch may be dropped by a translation, because many languages say "one file" instead of "1 file". Plural forms the source does not have (`_few`, `_many`, `quantity="many"`, `msgstr[2]`) are mapped to the source plural instead of being reported as stale.

## Three examples from the audit

The strings below are simplified, but each pattern is one the audit found in a real, actively maintained project.

### 1. A placeholder replaced by the value it usually has

A white-label product passed its brand name as `{{whiteLabelText}}`. Translators saw the English UI, where it rendered as the default product name, and typed the name directly. 46 strings in one project stopped following the configured brand.

```
source  "welcome": "Welcome to {{whiteLabelText}}"
before  "welcome": "Willkommen bei Acme"
after   "welcome": "Willkommen bei {{whiteLabelText}}"
```

```
locales/de/common.json
  error   placeholder_mismatch :3      [de] welcome
          missing {{whiteLabelText}}
```

### 2. An ICU apostrophe that turns an argument into literal text

In ICU MessageFormat an apostrophe directly before `{` starts quoted text. A translator who quoted a name the way Italian typography suggests made the UI print `{name}` verbatim.

```
source  msgid "Delete {name}?"
before  msgstr "Eliminare '{name}'?"
after   msgstr "Eliminare ''{name}''?"
```

```
src/locales/it/messages.po
  error   placeholder_mismatch :5      [it] Delete {name}?
          missing {name}. {name} is inside apostrophe quoted text and renders literally; use '' for a literal apostrophe
```

### 3. Trans markup shown to users

react-i18next only turns `<email>` into a component when the tag pair survives translation. When the closing tag was lost, Korean and Brazilian Portuguese users saw raw `<email>` markup.

```
source  "sent": "We sent a code to <email>{{email}}</email>"
before  "sent": "<email>{{email}}로 코드를 보냈습니다"
after   "sent": "<email>{{email}}</email>로 코드를 보냈습니다"
```

```
public/locales/ko/auth.json
  error   tag_mismatch         :2      [ko] sent
          Tags differ: missing </email>
```

## Install

Not on PyPI yet. Install from GitHub:

```sh
pipx install git+https://github.com/theluckystrike/i18n-audit
# or
pip install git+https://github.com/theluckystrike/i18n-audit
```

The only optional dependency is PyYAML, used as a fallback for YAML files that the built-in parser does not understand (complex anchors, tags, flow mappings):

```sh
pip install "i18n-audit[yaml] @ git+https://github.com/theluckystrike/i18n-audit"
```

## Usage

```sh
i18n-audit <repo-path> [--source-locale en] [--format text|json|md|sarif] [--fail-on N]
```

| Option | Default | Meaning |
| --- | --- | --- |
| `--source-locale LOC` | `en` | Source locale. `en` also matches `en-US`, `en_GB`, `en-us`. |
| `--format` | `text` | `text`, `json`, `md` or `sarif`. |
| `-o, --output FILE` | stdout | Write the report to a file. |
| `--fail-on N` | `1` | Exit 1 when there are at least N error findings. `0` never fails. |
| `--code-scan` | off | Also scan JS/TS/Vue/Svelte/Ruby code for keys missing from the source locale. |
| `--syntax` | auto | Force `i18next`, `icu`, `vue`, `rails`, `printf`, `brace` or `javamf`. |
| `--min-severity` | `info` | Hide findings below `warning` or `error`. |
| `--skip KIND` | | Drop a finding kind, for example `--skip stale_key`. Repeatable. |

Exit codes: `0` below the threshold, `1` threshold reached, `2` bad arguments.

Examples:

```sh
i18n-audit .                                    # human readable report
i18n-audit . --code-scan --skip stale_key       # include keys used in code
i18n-audit apps/web --source-locale en-US --format json > i18n.json
i18n-audit . --format md --min-severity warning > i18n-report.md
```

## Supported formats

Locale files are found automatically. The locale is read from the file name (`de.json`, `devise.de.yml`, `messages_de.properties`) or a directory (`locales/de/common.json`, `values-de/`, `de.lproj/`, `locale/de/LC_MESSAGES/`). Files that translate the same catalog are grouped, and each group is compared with its source locale file. `node_modules`, `vendor`, `dist`, `build` and hidden directories are skipped.

| Format | Typical paths | Placeholder syntax |
| --- | --- | --- |
| i18next JSON, nested and flat | `locales/{loc}/{ns}.json`, `public/locales/{loc}.json` | `{{x}}`, `{{x, format}}`, `{{- x}}`, `$t(key)`, `<0></0>` |
| ICU MessageFormat JSON (react-intl, formatjs, next-intl, Tolgee) | `lang/{loc}.json`, formatjs `defaultMessage` files | `{x}`, `{n, plural, ...}`, `{g, select, ...}`, `{n, selectordinal, ...}`, `<b></b>` |
| vue-i18n JSON | `src/locales/{loc}.json` | `{x}`, `{0}`, `@:linked.key`, `{'literal'}`, `a \| b` plurals |
| Rails YAML | `config/locales/{loc}.yml`, `devise.{loc}.yml` | `%{x}`, `%<x>s` |
| gettext | `locale/{loc}/LC_MESSAGES/*.po`, `po/{loc}.po`, `.pot` | `%s`, `%(name)s`, `{name}` (from `#, c-format` / `python-format` / `python-brace-format` flags), ICU for Lingui |
| Android | `res/values-{loc}/strings.xml` | `%s`, `%1$s`, `%d`, `<plurals>`, `<string-array>` |
| Apple | `{loc}.lproj/*.strings` | `%@`, `%1$@`, `%d`, `%lld` |
| Java | `messages_{loc}.properties` | `{0}`, `{0,number}`, `{0,choice,...}`, `%s` |

The interpolation library is taken from `package.json` dependencies near the locale files (`i18next`, `react-i18next`, `react-intl`, `@formatjs/*`, `@lingui/*`, `next-intl`, `@tolgee/*`, `vue-i18n`, `@nuxtjs/i18n`), and from the strings themselves when there is no `package.json`. Use `--syntax` to override it.

The ICU checks use a small parser written for this tool. It handles `plural`, `select`, `selectordinal`, `offset:`, `=N` selectors, `#`, nested arguments, number/date/time styles and apostrophe quoting in both ICU mode (`'` only quotes before `{`, `}` or `#`) and `java.text.MessageFormat` mode (every `'` quotes, so `L'utente {0}` loses its argument).

## Translation management systems

If the repository has a `crowdin.yml`, LingoHub config, Lingo.dev `i18n.json` / `i18n.lock`, `.tolgeerc`, `lokalise.yml`, `.tx/config` (Transifex), `.phrase.yml`, Weblate or Localazy config, the report starts with a note:

```
NOTE: Translations appear to be managed by Crowdin (crowdin.yml). Pull requests that edit locale
files directly may be rejected or overwritten on the next sync; fix translations in the TMS or
report them to the maintainers instead.
```

## GitHub Action

```yaml
name: i18n
on: [push, pull_request]

permissions:
  contents: read
  security-events: write   # for the SARIF upload

jobs:
  i18n-audit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: theluckystrike/i18n-audit@v1
        with:
          source-locale: en
          fail-on: 1
```

Findings appear as code scanning alerts on the changed lines, as a Markdown table in the job summary, and in the log. Code scanning uploads need GitHub Advanced Security on private repositories; set `upload-sarif: "false"` there.

| Input | Default | Meaning |
| --- | --- | --- |
| `path` | `.` | Directory to scan. |
| `source-locale` | `en` | Source locale. |
| `fail-on` | `1` | Fail the job at this many error findings. `0` never fails. |
| `code-scan` | `false` | Also check keys used in code. |
| `args` | | Extra CLI arguments, e.g. `--skip stale_key`. |
| `sarif-file` | `i18n-audit.sarif` | Where the SARIF report is written. |
| `upload-sarif` | `true` | Upload the report to code scanning. |
| `sarif-category` | `i18n-audit` | Code scanning category. |
| `python-version` | `3.12` | Python used to run the tool. |

Outputs: `sarif-file` and `exit-code`.

Without the action:

```yaml
      - run: pipx run --spec git+https://github.com/theluckystrike/i18n-audit i18n-audit . --format sarif -o i18n.sarif --fail-on 0
      - uses: github/codeql-action/upload-sarif@v3
        with:
          sarif_file: i18n.sarif
```

## Output formats

The `text` format (default) groups findings by file:

```
src/lang/fr.json
  error   invalid_icu          :2      [fr] inbox
          Invalid ICU message: plural argument 'count' is missing the required 'other' option
          source: You have {count, plural, one {# message} other {# messages}}
          fr: Vous avez {count, plural, one {# message} autre {# messages}}
  error   wrong_syntax         :3      [fr] greeting
          Placeholder in the wrong syntax for icu: {{name}} should be {name}
          source: Hello {name}
          fr: Bonjour {{name}}

Scanned 1 catalog group(s): src/lang/{loc}.json (json, icu, 4 locales)
9 finding(s): 9 error, 0 warning, 0 info
```

The `json` format has `summary`, `tms`, `groups` and `findings`. Every finding has `file`, `line`, `key`, `locale`, `kind`, `severity`, `message`, `source_text` and `locale_text`.

The `md` format is a summary plus a findings table, ready for a PR comment or job summary.

The `sarif` format is SARIF 2.1.0 with one rule per kind and repository-relative paths, for GitHub code scanning and other SARIF viewers.

## Limitations

- Static analysis only. It does not render messages, so it cannot tell whether a translation is correct, only whether it is structurally compatible with the source.
- `--code-scan` uses regular expressions. It sees literal keys (`t('a.b')`, `i18n.t`, `$t`, `<Trans i18nKey>`, `formatMessage({ id })`, `I18n.t`) and skips keys built at runtime. Custom wrapper functions are not recognized.
- A locale must have a file next to the source locale file to be compared. Single file catalogs with no translations, Apple `.stringsdict` and `.xcstrings`, XLIFF, ARB, TOML and PHP arrays are not read yet.
- Missing keys are reported per key. A locale that is mostly untranslated produces many `missing_key` warnings; use `--skip missing_key` or `--min-severity error` if that is expected.
- gettext entries marked `fuzzy` are skipped, as gettext itself ignores them.
- The YAML parser covers what locale files use. Files using complex YAML features fall back to PyYAML when it is installed, without line numbers.
- Tag checks compare tag names, not attributes, and treat `<` followed by a letter or digit and closed by `>` as a tag.

## Development

```sh
pip install -e ".[test]"
pytest
```

## Support

The tool is free and MIT licensed. If you want it run on your app with the fixes done for you, there is a [fixed-price i18n audit](https://theluckystrike.github.io/oss-maintenance/i18n-audit/). To support the work: [GitHub Sponsors](https://github.com/sponsors/theluckystrike).
