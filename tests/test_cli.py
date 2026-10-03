import json
import subprocess
import sys

import pytest

from conftest import fixture_path
from i18n_audit import __version__
from i18n_audit.cli import main
from i18n_audit.model import KINDS


def run(capsys, *args):
    code = main(list(args))
    out, err = capsys.readouterr()
    return code, out, err


def test_text_output(capsys):
    code, out, _ = run(capsys, fixture_path("i18next"))
    assert code == 1
    assert "locales/de/common.json" in out
    assert "wrong_syntax" in out and "Hallo {name}" in out
    assert "finding(s):" in out


def test_clean_repo_exits_zero(capsys):
    code, out, _ = run(capsys, fixture_path("clean"))
    assert code == 0 and "0 finding(s)" in out


@pytest.mark.parametrize("fail_on,expected", [("0", 0), ("1", 1), ("7", 1), ("8", 0), ("100", 0)])
def test_fail_on(capsys, fail_on, expected):
    # the i18next fixture has 7 error findings without --code-scan
    code, _, _ = run(capsys, fixture_path("i18next"), "--fail-on", fail_on)
    assert code == expected


def test_json_output(capsys):
    code, out, _ = run(capsys, fixture_path("icu"), "--format", "json")
    data = json.loads(out)
    assert data["version"] == __version__
    assert data["groups"][0]["syntax"] == "icu"
    assert data["summary"]["total"] == len(data["findings"])
    f = data["findings"][0]
    assert set(f) == {"file", "line", "key", "locale", "kind", "severity", "message", "source_text",
                      "locale_text"}


def test_markdown_output(capsys):
    _, out, _ = run(capsys, fixture_path("rails"), "--format", "md")
    assert out.startswith("# i18n-audit report")
    assert "| Severity | Kind | File |" in out
    assert "config/locales/de.yml:2" in out


def test_sarif_output(capsys, tmp_path):
    target = tmp_path / "out.sarif"
    code, out, _ = run(capsys, fixture_path("android"), "--format", "sarif", "-o", str(target))
    assert out == ""
    doc = json.loads(target.read_text())
    assert doc["version"] == "2.1.0"
    (r,) = doc["runs"]
    rules = r["tool"]["driver"]["rules"]
    assert {x["id"] for x in rules} == set(KINDS)
    res = r["results"]
    assert res and all(x["ruleId"] == rules[x["ruleIndex"]]["id"] for x in res)
    loc = res[0]["locations"][0]["physicalLocation"]
    assert loc["artifactLocation"]["uriBaseId"] == "%SRCROOT%"
    assert not loc["artifactLocation"]["uri"].startswith("/")
    assert {x["level"] for x in res} <= {"error", "warning", "note"}


def test_tms_note(capsys):
    _, out, _ = run(capsys, fixture_path("tms"))
    assert out.startswith("NOTE: Translations appear to be managed by Crowdin")
    _, out, err = run(capsys, fixture_path("tms"), "--format", "json")
    assert json.loads(out)["tms"] == [{"name": "Crowdin", "path": "crowdin.yml"}]
    assert "Crowdin" in err
    _, out, _ = run(capsys, fixture_path("tms"), "--format", "sarif")
    notes = json.loads(out)["runs"][0]["invocations"][0]["toolExecutionNotifications"]
    assert "Crowdin" in notes[0]["message"]["text"]


def test_min_severity_and_skip(capsys):
    _, out, _ = run(capsys, fixture_path("i18next"), "--format", "json", "--min-severity", "error")
    assert {f["severity"] for f in json.loads(out)["findings"]} == {"error"}
    _, out, _ = run(capsys, fixture_path("i18next"), "--format", "json", "--skip", "tag_mismatch",
                    "--skip", "stale_key")
    assert not {f["kind"] for f in json.loads(out)["findings"]} & {"tag_mismatch", "stale_key"}


def test_code_scan_flag(capsys):
    _, out, _ = run(capsys, fixture_path("i18next"), "--format", "json", "--code-scan")
    assert "missing_in_source" in {f["kind"] for f in json.loads(out)["findings"]}


def test_source_locale_flag(capsys):
    _, out, _ = run(capsys, fixture_path("i18next_flat"), "--format", "json", "--source-locale", "es")
    data = json.loads(out)
    assert data["groups"][0]["source_locale"] == "es"


def test_bad_arguments(capsys, tmp_path):
    assert main([str(tmp_path / "missing")]) == 2
    assert main([str(tmp_path), "--skip", "nope"]) == 2
    with pytest.raises(SystemExit):
        main([str(tmp_path), "--format", "xml"])


def test_empty_directory(capsys, tmp_path):
    code, out, _ = run(capsys, str(tmp_path))
    assert code == 0 and "no locale files found" in out


def test_module_entry_point():
    p = subprocess.run([sys.executable, "-m", "i18n_audit", "--version"], capture_output=True, text=True)
    assert p.returncode == 0 and __version__ in p.stdout
