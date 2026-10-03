"""Command line interface: ``i18n-audit <repo-path> [options]``."""
from __future__ import annotations

import argparse
import os
import sys
from typing import List, Optional

from . import __version__, checks, codescan, detect, report, tms
from .model import KINDS, SEVERITY_RANK
from .placeholders import SYNTAXES

FORMATS = ("text", "json", "md", "sarif")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="i18n-audit",
        description="Find translation bugs users actually see: broken placeholders, invalid ICU messages, "
                    "lost Trans tags, wrong interpolation syntax, missing and stale keys.",
    )
    p.add_argument("path", help="repository or directory to scan")
    p.add_argument("--source-locale", default="en", metavar="LOC",
                   help="source locale code (default: en; also matches en-US, en_GB, ...)")
    p.add_argument("--format", default="text", choices=FORMATS, help="output format (default: text)")
    p.add_argument("-o", "--output", metavar="FILE", help="write the report to FILE instead of stdout")
    p.add_argument("--fail-on", type=int, default=1, metavar="N",
                   help="exit 1 when there are at least N error findings (default: 1; 0 never fails)")
    p.add_argument("--code-scan", action="store_true",
                   help="also scan JS/TS/Vue/Ruby code for keys missing from the source locale")
    p.add_argument("--syntax", choices=SYNTAXES,
                   help="force the interpolation syntax instead of auto-detecting it per catalog")
    p.add_argument("--min-severity", default="info", choices=("info", "warning", "error"),
                   help="only report findings at or above this severity (default: info)")
    p.add_argument("--skip", action="append", default=[], metavar="KIND",
                   help="skip a finding kind (repeatable), e.g. --skip stale_key")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if not os.path.isdir(args.path):
        print(f"i18n-audit: not a directory: {args.path}", file=sys.stderr)
        return 2
    unknown = [k for k in args.skip if k not in KINDS]
    if unknown:
        print(f"i18n-audit: unknown kind(s): {', '.join(unknown)}. Known: {', '.join(sorted(KINDS))}",
              file=sys.stderr)
        return 2

    groups, notes = detect.discover(args.path, args.source_locale, args.syntax)
    findings = checks.run(groups)
    if args.code_scan:
        findings.extend(codescan.scan(args.path, groups, args.source_locale))
    min_rank = SEVERITY_RANK[args.min_severity]
    findings = [f for f in findings if SEVERITY_RANK[f.severity] >= min_rank and f.kind not in args.skip]
    findings.sort(key=report.sort_key)

    tms_found = tms.detect(args.path)
    tms_note = tms.note(tms_found)
    if not groups:
        notes.append(f"no locale files found under {args.path}")

    if args.format == "text":
        out = report.text(findings, groups, notes, tms_note)
    elif args.format == "json":
        out = report.as_json(findings, groups, notes, tms_found)
    elif args.format == "md":
        out = report.markdown(findings, groups, notes, tms_note)
    else:
        out = report.sarif(findings, groups, notes, tms_note)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(out)
    else:
        sys.stdout.write(out)
    if tms_note and (args.output or args.format != "text"):
        print("NOTE: " + tms_note, file=sys.stderr)

    errors = sum(1 for f in findings if f.severity == "error")
    return 1 if args.fail_on > 0 and errors >= args.fail_on else 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
