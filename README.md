# i18n-audit

Find the translation bugs your users actually see: dropped or renamed placeholders, broken ICU plurals, lost `<0>Trans</0>` tags and missing keys, in the locale files you already have.

Pure Python standard library, Python 3.9+, no network access, no API keys. Reads i18next, ICU (react-intl, formatjs, next-intl), vue-i18n, Rails YAML, gettext, Android, Apple `.strings` and Java `.properties`. Runs as a CLI or a GitHub Action with code scanning alerts.

## Quick start

```sh
pipx install git+https://github.com/theluckystrike/i18n-audit@v1.0.0
i18n-audit .
```

No pipx? `pip install git+https://github.com/theluckystrike/i18n-audit@v1.0.0` works too. The tool finds the locale files, works out which locale is the source (`en` by default, `--source-locale` to change it), compares every translation with its source string and prints each problem with file, line, key, locale, source text and translation. It exits 1 when there is at least one error, so it can gate CI as is.

## The four most common bugs

Each example below is a real string from a public repository, found by running `i18n-audit` on it, with the fix. Every one is covered by a test in `tests/test_readme_examples.py`.

### 1. Placeholder translated or renamed

The translator translated the variable name. The app passes `browse`, so `{bläddra}` has no value: formatjs throws and the UI falls back to English or prints the raw message. Strapi admin, Swedish:

```
source  "Drag & drop files, paste from the clipboard or {browse}."
before  "Dra och släpp filer, klistra in från urklipp eller {bläddra}."
after   "Dra och släpp filer, klistra in från urklipp eller {browse}."
```

```
translations/sv.json
  error   placeholder_mismatch :2      [sv] components.WysiwygBottomControls.uploadFiles
          missing {browse}; unexpected {bläddra}. Looks renamed or translated: the code passes {browse}
```

### 2. Placeholder dropped

The translation reads fine but lost the value. French users of the Medusa admin are never told how many promotions were added:

```
source  "Successfully added {{count}} promotion(s) to campaign"
before  "Promotion(s) ajoutée(s) à la campagne avec succès"
after   "{{count}} promotion(s) ajoutée(s) à la campagne avec succès"
```

```
src/i18n/translations/fr.json
  error   placeholder_mismatch :5      [fr] campaigns.promotions.toast.success
          missing {{count}}
```

### 3. ICU plural keywords translated

`one` and `other` are syntax, not text. With `um` and `outros`, the message has no `other` branch, which is invalid ICU, so the whole string fails to format. Strapi admin, Brazilian Portuguese:

```
source  "{number, plural, =0 {# users} one {# user} other {# users}} with this role"
before  "{number, plural, =0 {# usuários} um {# usuário} outros {# usuários}} com esse papel"
after   "{number, plural, =0 {# usuários} one {# usuário} other {# usuários}} com esse papel"
```

```
translations/pt-BR.json
  error   invalid_icu          :2      [pt-BR] Settings.roles.form.button.users-with-role
          Invalid ICU message: plural argument 'number' is missing the required 'other' option
```

Related checks catch translated `plural` and `select` keywords, translated argument names, unclosed braces and apostrophes that turn `{name}` into literal text.

### 4. Trans component tags lost

react-i18next turns `<0>...</0>` into the component passed at index 0, here a link. Without the tags, Greek users of the Medusa admin see "Reset" as plain text with nothing to click:

```
source  "Forgot password? - <0>Reset</0>"
before  "Ξεχάσατε τον κωδικό πρόσβασης; - Επαναφορά"
after   "Ξεχάσατε τον κωδικό πρόσβασης; - <0>Επαναφορά</0>"
```

```
src/i18n/translations/el.json
  error   tag_mismatch         :3      [el] login.forgotPassword
          Trans component tags differ: missing </0>, <0>
```

## All checks

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
| `duplicate_key` | error / warning | the same section twice in one file: the second silently replaces the first |
| `missing_key` | warning | key exists in the source locale but not in this locale |
| `missing_file` | warning | `locales/en/auth.json` exists, `locales/fr/auth.json` does not |
| `stale_key` | info | key exists in a locale but was removed from the source |
| `plural_placeholder` | info | `items_one` says "one item" without `{{count}}` (often intentional) |

Placeholders are compared as sets, so reordering is fine (`%1$s ... %2$d` against `%2$d ... %1$s`). An ICU argument used only in a non-`other` plural branch may be dropped, because many languages say "one file" instead of "1 file". Plural forms the source does not have (`_few`, `_many`, `quantity="many"`, `msgstr[2]`) are mapped to the source plural instead of being reported as stale.

## CI

### GitHub Action

Copy [`examples/i18n-audit.yml`](examples/i18n-audit.yml) to `.github/workflows/`, or add the step to an existing job:

```yaml
permissions:
  contents: read
  security-events: write   # for the SARIF upload to code scanning

steps:
  - uses: actions/checkout@v6
  - uses: theluckystrike/i18n-audit@v1
    with:
      path: .
      source-locale: en
      fail-on: 1
      format: text
```

Findings appear as code scanning alerts on the changed lines, as a Markdown table in the job summary, and in the log. Code scanning needs GitHub Advanced Security on private repositories; set `upload-sarif: "false"` there.

| Input | Default | Meaning |
| --- | --- | --- |
| `path` | `.` | Directory to scan. |
| `source-locale` | `en` | Source locale. |
| `fail-on` | `1` | Fail the job at this many error findings. `0` never fails. |
| `format` | `text` | Report printed to the log and saved as `report-file`: `text`, `json`, `md` or `sarif`. |
| `report-file` | `i18n-audit-report.<ext>` | Where the report is saved. |
| `code-scan` | `false` | Also check keys used in code. |
| `args` | | Extra CLI arguments, e.g. `--skip stale_key`. |
| `sarif-file` | `i18n-audit.sarif` | Where the SARIF report is written. |
| `upload-sarif` | `true` | Upload the SARIF report to code scanning. |
| `sarif-category` | `i18n-audit` | Code scanning category. |
| `python-version` | `3.12` | Python used to run the tool (installed in its own virtualenv). |

Outputs: `exit-code`, `report-file` and `sarif-file`.

### Any other CI

```sh
pipx run --spec git+https://github.com/theluckystrike/i18n-audit@v1.0.0 i18n-audit . --fail-on 1
```

To upload SARIF yourself on GitHub:

```yaml
  - run: pipx run --spec git+https://github.com/theluckystrike/i18n-audit@v1.0.0 i18n-audit . --format sarif -o i18n.sarif --fail-on 0
  - uses: github/codeql-action/upload-sarif@v4
    with:
      sarif_file: i18n.sarif
      category: i18n-audit
```

## CLI options

```sh
i18n-audit <path> [--source-locale en] [--format text|json|md|sarif] [-o FILE] [--fail-on N]
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

## Output formats

`text` (default) groups findings by file and ends with a summary:

```
src/lang/fr.json
  error   invalid_icu          :2      [fr] inbox
          Invalid ICU message: plural argument 'count' is missing the required 'other' option
          source: You have {count, plural, one {# message} other {# messages}}
          fr: Vous avez {count, plural, one {# message} autre {# messages}}
...

Scanned 1 catalog group(s): src/lang/{loc}.json (json, icu, 4 locales)
9 finding(s): 9 error, 0 warning, 0 info
```

`json` has `summary`, `tms`, `groups` and `findings`. Every finding has `file`, `line`, `key`, `locale`, `kind`, `severity`, `message`, `source_text` and `locale_text`.

`md` is a summary plus a findings table, ready for a PR comment or job summary.

`sarif` is SARIF 2.1.0 with one rule per kind and repository-relative paths, for GitHub code scanning and other SARIF viewers.

## Supported formats

Locale files are found automatically. The locale comes from the file name (`de.json`, `devise.de.yml`, `messages_de.properties`) or a directory (`locales/de/common.json`, `values-de/`, `de.lproj/`, `locale/de/LC_MESSAGES/`). Files that translate the same catalog are grouped and compared with the source locale file. `node_modules`, `vendor`, `dist`, `build` and hidden directories are skipped.

| Format | Typical paths | Placeholder syntax |
| --- | --- | --- |
| i18next JSON, nested and flat | `locales/{loc}/{ns}.json`, `public/locales/{loc}.json` | `{{x}}`, `{{x, format}}`, `{{- x}}`, `$t(key)`, `<0></0>` |
| ICU MessageFormat JSON (react-intl, formatjs, next-intl, Tolgee) | `lang/{loc}.json` | `{x}`, `{n, plural, ...}`, `{g, select, ...}`, `<b></b>` |
| vue-i18n JSON | `src/locales/{loc}.json` | `{x}`, `{0}`, `@:linked.key`, `a \| b` plurals |
| Rails YAML | `config/locales/{loc}.yml` | `%{x}`, `%<x>s` |
| gettext | `locale/{loc}/LC_MESSAGES/*.po`, `po/{loc}.po`, `.pot` | `%s`, `%(name)s`, `{name}` (from `#, *-format` flags), ICU for Lingui |
| Android | `res/values-{loc}/strings.xml` | `%s`, `%1$s`, `%d`, `<plurals>`, `<string-array>` |
| Apple | `{loc}.lproj/*.strings` | `%@`, `%1$@`, `%d`, `%lld` |
| Java | `messages_{loc}.properties` | `{0}`, `{0,number}`, `{0,choice,...}`, `%s` |

The interpolation library is taken from `package.json` dependencies near the locale files, and from the strings themselves when there is none. Use `--syntax` to override it. If the repository has a translation management system config (Crowdin, Lokalise, Transifex, Phrase, Weblate, Tolgee, Lingo.dev, LingoHub, Localazy), the report starts with a note that fixes may belong in the TMS rather than in a pull request.

## Limitations

- Static analysis only. It cannot tell whether a translation is correct, only whether it is structurally compatible with the source.
- `--code-scan` uses regular expressions. It sees literal keys (`t('a.b')`, `$t`, `<Trans i18nKey>`, `formatMessage({ id })`, `I18n.t`) and skips keys built at runtime or passed through custom wrappers.
- A locale needs a file next to the source locale file to be compared. Apple `.stringsdict` and `.xcstrings`, XLIFF, ARB, TOML and PHP arrays are not read yet.
- Missing and stale keys are reported per key, so a mostly untranslated locale produces many warnings. Use `--skip missing_key --skip stale_key` or `--min-severity error` if that is expected.
- gettext entries marked `fuzzy` are skipped, as gettext itself ignores them.
- The built-in YAML parser covers what locale files use. Files with complex YAML features fall back to PyYAML when installed (`pip install "i18n-audit[yaml] @ git+https://github.com/theluckystrike/i18n-audit@v1.0.0"`), without line numbers.
- Tag checks compare tag names, not attributes.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). False positives are bugs; please report them with the source and translated string. Changes are listed in [CHANGELOG.md](CHANGELOG.md). MIT licensed.

Paid fixed-scope audit + fix for your app: https://theluckystrike.github.io/oss-maintenance/i18n-audit/
