# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/). The public interface covered by
semver is the CLI (options, exit codes), the JSON and SARIF report fields, the
finding kinds, and the GitHub Action inputs and outputs.

## [Unreleased]

## [1.0.0] - 2026-10-03

First public release.

### Added

- `i18n-audit` CLI: scans a repository, finds locale files, groups them into
  catalogs and compares every translation with its source string. Pure Python
  standard library, Python 3.9 to 3.13, no network access.
- Locale formats: i18next JSON (nested and flat), ICU MessageFormat JSON
  (react-intl, formatjs, next-intl, Tolgee), vue-i18n JSON, Rails YAML, gettext
  `.po`/`.pot` (including Lingui), Android `strings.xml`, Apple `.strings`, Java
  `.properties`.
- Interpolation syntax detection from `package.json` dependencies and from the
  strings themselves, with a `--syntax` override.
- Finding kinds: `placeholder_mismatch`, `wrong_syntax`, `invalid_icu`,
  `unbalanced_braces`, `tag_mismatch`, `android_apostrophe`, `parse_error`,
  `missing_in_source` (with `--code-scan`), `duplicate_key`, `missing_key`,
  `missing_file`, `stale_key`, `plural_placeholder`.
- An ICU MessageFormat parser covering plural, select, selectordinal, offsets,
  `=N` selectors, `#`, nested arguments and apostrophe quoting in ICU/formatjs
  and `java.text.MessageFormat` modes.
- Output formats: `text`, `json`, `md` and SARIF 2.1.0.
- `--fail-on N`, `--min-severity`, `--skip KIND` and `--source-locale`.
- A note when a translation management system (Crowdin, Lokalise, Transifex,
  Phrase, Weblate, Tolgee, Lingo.dev, LingoHub, Localazy) owns the locale files.
- Composite GitHub Action (`theluckystrike/i18n-audit@v1`) with inputs `path`,
  `source-locale`, `fail-on`, `format`, `code-scan`, `args` and SARIF upload to
  code scanning, plus a job summary table.
- `examples/i18n-audit.yml`, a ready-to-copy workflow.

### Fixed (since the pre-release audit scripts)

- Apostrophe-quoted markup in ICU messages, such as `'<head>...</head>'`, is
  literal text in formatjs and no longer reported as a lost tag.

[Unreleased]: https://github.com/theluckystrike/i18n-audit/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/theluckystrike/i18n-audit/releases/tag/v1.0.0
