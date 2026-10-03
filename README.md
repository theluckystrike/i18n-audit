# i18n-audit

Finds translation bugs that users actually see: dropped `{{placeholders}}`, broken ICU messages, lost `<0>Trans</0>` tags, wrong interpolation syntax, and keys the code calls but locale files lack.

Seed code from an audit of 6 company repos on 2026-10-03 (602 broken strings found, 326 fixed in PRs). Being turned into a proper CLI.

Paid fixed-scope audit + fix for your app: https://theluckystrike.github.io/oss-maintenance/i18n-audit/
