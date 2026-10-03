# Contributing

Bug reports and pull requests are welcome.

## Reporting a false positive or a missed bug

Open an issue with:

- the `i18n-audit --version` output and the command you ran,
- the source string and the translated string (or a link to the file and line
  in a public repository),
- what you expected the tool to report.

A false positive is a bug. The goal is that every error finding is something a
user of the translated app would actually see.

## Development setup

```sh
git clone https://github.com/theluckystrike/i18n-audit
cd i18n-audit
python -m venv .venv && . .venv/bin/activate
pip install -e ".[test]"
pytest
```

The package has no runtime dependencies and supports Python 3.9 and newer.
Please keep it that way: use only the standard library in `src/`.

## Pull requests

- Add a test for every behavior change. Checks are tested with small fixture
  repositories (see `tests/fixtures/` and the `write_tree` fixture in
  `tests/conftest.py`). A fix for a false positive needs a regression test with
  the string that triggered it.
- Every example in the README is checked by `tests/test_readme_examples.py`;
  update it when you change an example.
- Add a line under `## [Unreleased]` in `CHANGELOG.md`.
- Keep the diff focused on one change.

## Releasing (maintainers)

1. Update the version in `src/i18n_audit/__init__.py` and move the
   `Unreleased` entries in `CHANGELOG.md` under the new version.
2. Tag `vX.Y.Z`, move the major tag (`v1`) to the same commit, push both and
   create the GitHub release from the changelog entry.
