"""Output formats: text, json, md, sarif."""
from __future__ import annotations

import json
from collections import Counter
from typing import Dict, List

from . import __version__
from .model import KINDS, SEVERITY_RANK, Finding, Group

INFO_URI = "https://github.com/theluckystrike/i18n-audit#what-it-catches"


def _short(s, n=100):
    if s is None:
        return ""
    s = s.replace("\n", "\\n")
    return s if len(s) <= n else s[: n - 3] + "..."


def summary(findings: List[Finding]) -> Dict:
    return {
        "total": len(findings),
        "by_severity": dict(Counter(f.severity for f in findings)),
        "by_kind": dict(sorted(Counter(f.kind for f in findings).items())),
        "by_locale": dict(sorted(Counter(f.locale for f in findings).items())),
    }


def text(findings: List[Finding], groups: List[Group], notes: List[str], tms_note: str) -> str:
    out = []
    if tms_note:
        out.append("NOTE: " + tms_note)
    for n in notes:
        out.append("note: " + n)
    cur = None
    for f in findings:
        if f.file != cur:
            cur = f.file
            out.append("")
            out.append(cur)
        loc = f":{f.line}" if f.line else ""
        out.append(f"  {f.severity:<7} {f.kind:<20} {loc:<7} [{f.locale}] {f.key}")
        out.append(f"          {f.message}")
        if f.source_text is not None:
            out.append(f"          source: {_short(f.source_text)}")
        if f.locale_text is not None:
            out.append(f"          {f.locale}: {_short(f.locale_text)}")
    s = summary(findings)
    out.append("")
    out.append("Scanned %d catalog group(s): %s" % (len(groups), ", ".join(
        f"{g.template} ({g.fmt}, {g.syntax}, {len([c for c in g.catalogs if c != '__pot__'])} locales)" for g in groups) or "none found"))
    sev = s["by_severity"]
    out.append("%d finding(s): %d error, %d warning, %d info" % (
        s["total"], sev.get("error", 0), sev.get("warning", 0), sev.get("info", 0)))
    if s["by_kind"]:
        out.append("By kind: " + ", ".join(f"{k}={v}" for k, v in s["by_kind"].items()))
    return "\n".join(out).lstrip("\n") + "\n"


def as_json(findings: List[Finding], groups: List[Group], notes: List[str], tms_found) -> str:
    data = {
        "version": __version__,
        "summary": summary(findings),
        "tms": [{"name": n, "path": p} for n, p in tms_found],
        "notes": notes,
        "groups": [
            {"template": g.template, "format": g.fmt, "syntax": g.syntax, "source_locale": g.source_locale,
             "locales": sorted(l for l in g.catalogs if l != "__pot__")}
            for g in groups
        ],
        "findings": [f.to_dict() for f in findings],
    }
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def _md_cell(s) -> str:
    return _short(s, 80).replace("|", "\\|").replace("`", "'") if s is not None else ""


def markdown(findings: List[Finding], groups: List[Group], notes: List[str], tms_note: str) -> str:
    s = summary(findings)
    sev = s["by_severity"]
    out = ["# i18n-audit report", ""]
    if tms_note:
        out += ["> **Note:** " + tms_note, ""]
    out.append("%d finding(s): %d error, %d warning, %d info across %d catalog group(s)." % (
        s["total"], sev.get("error", 0), sev.get("warning", 0), sev.get("info", 0), len(groups)))
    out.append("")
    if s["by_kind"]:
        out += ["| Kind | Count |", "| --- | --- |"]
        out += [f"| {k} | {v} |" for k, v in s["by_kind"].items()]
        out.append("")
    for n in notes:
        out.append(f"- {n}")
    if findings:
        out += ["## Findings", "",
                "| Severity | Kind | File | Locale | Key | Message | Source | Translation |",
                "| --- | --- | --- | --- | --- | --- | --- | --- |"]
        for f in findings:
            loc = f"{f.file}:{f.line}" if f.line else f.file
            out.append("| " + " | ".join([f.severity, f.kind, _md_cell(loc), f.locale, _md_cell(f.key),
                                           _md_cell(f.message), _md_cell(f.source_text),
                                           _md_cell(f.locale_text)]) + " |")
    return "\n".join(out) + "\n"


def sarif(findings: List[Finding], groups: List[Group], notes: List[str], tms_note: str) -> str:
    kinds = sorted(KINDS)
    rules = [
        {
            "id": k,
            "name": "".join(w.capitalize() for w in k.split("_")),
            "shortDescription": {"text": KINDS[k][1]},
            "helpUri": INFO_URI,
            "defaultConfiguration": {"level": _level(KINDS[k][0])},
        }
        for k in kinds
    ]
    results = []
    for f in findings:
        msg = f.message
        if f.key:
            msg = f"[{f.locale}] {f.key}: {msg}"
        if f.source_text is not None:
            msg += f"\nsource: {_short(f.source_text, 300)}"
        if f.locale_text is not None:
            msg += f"\n{f.locale}: {_short(f.locale_text, 300)}"
        loc = {"artifactLocation": {"uri": f.file, "uriBaseId": "%SRCROOT%"}}
        if f.line:
            loc["region"] = {"startLine": f.line}
        results.append({
            "ruleId": f.kind,
            "ruleIndex": kinds.index(f.kind),
            "level": _level(f.severity),
            "message": {"text": msg},
            "locations": [{"physicalLocation": loc}],
            "partialFingerprints": {"i18nAudit/v1": f"{f.file}|{f.locale}|{f.key}|{f.kind}"},
        })
    run = {
        "tool": {"driver": {"name": "i18n-audit", "version": __version__, "informationUri": INFO_URI,
                            "rules": rules}},
        "results": results,
    }
    if tms_note or notes:
        run["invocations"] = [{"executionSuccessful": True, "toolExecutionNotifications": [
            {"level": "note", "message": {"text": t}} for t in ([tms_note] if tms_note else []) + notes]}]
    doc = {"$schema": "https://json.schemastore.org/sarif-2.1.0.json", "version": "2.1.0", "runs": [run]}
    return json.dumps(doc, indent=2, ensure_ascii=False) + "\n"


def _level(sev: str) -> str:
    return {"error": "error", "warning": "warning", "info": "note"}[sev]


def sort_key(f: Finding):
    return (f.file, f.line or 0, f.locale, f.key, -SEVERITY_RANK[f.severity], f.kind)
