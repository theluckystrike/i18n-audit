import fs from 'node:fs';
import { execSync } from 'node:child_process';
import { createIntl } from '@formatjs/intl';
import { parse } from '@formatjs/icu-messageformat-parser';
const repo = process.env.HOME + '/oss-work/i18n/openaev';
const ref = process.argv[2] || 'WORKTREE';
const langs = 'de en es fr it ja ko ru zh'.split(' ');
const load = (lg, r) => JSON.parse(r === 'WORKTREE'
  ? fs.readFileSync(`${repo}/openaev-front/src/utils/lang/${lg}.json`, 'utf8')
  : execSync(`git -C ${repo} show ${r}:openaev-front/src/utils/lang/${lg}.json`, { maxBuffer: 1e8 }).toString());
const LESSONS = 'We would like thank your for your participation in this simulation. You are kindly requested to fill this lessons learned questionnaire: <a href="${lessons_uri}">${lessons_uri}</a>.';
// values exactly as the callers pass them
const callerValues = {
  [LESSONS]: undefined,
  'getting_started_description_test_scenarios_text': { xtmHubLink: 'XTMHUB' },
  'Do you want to launch this atomic testing: {title}?': { title: 'TITLE' },
  'faq.howto.understand_results.details': undefined,
};
let bad = 0;
for (const lg of langs) {
  const cur = load(lg, ref), base = load(lg, 'origin/main');
  const changed = Object.keys(cur).filter(k => cur[k] !== base[k]);
  const keys = new Set([...changed, ...Object.keys(callerValues).filter(k => k in cur)]);
  const errors = [];
  const intl = createIntl({ locale: lg, messages: cur, onError: e => errors.push(e) });
  for (const k of keys) {
    errors.length = 0;
    let parsed = 'ok';
    try { parse(cur[k]); } catch (e) { parsed = 'PARSE_ERR ' + e.message; }
    const out = intl.formatMessage({ id: k, defaultMessage: callerValues[k] ? k : undefined }, callerValues[k]);
    const errs = errors.filter(e => e.code !== 'MISSING_TRANSLATION').map(e => e.code + ':' + (e.originalMessage || e.message).slice(0, 90));
    let note = '';
    if (k === LESSONS) note = out.includes('<a href="${lessons_uri}">${lessons_uri}</a>') && !out.includes("'<") ? 'html-intact' : 'HTML-BROKEN';
    if (errs.length || parsed !== 'ok' || note === 'HTML-BROKEN') bad++;
    console.log([lg, k.slice(0, 45), parsed, errs.join('|') || 'no-format-error', note, JSON.stringify(out).slice(-70)].join('\t'));
  }
  // full-catalog parse, informational
  let invalid = 0; for (const [k, v] of Object.entries(cur)) { try { parse(v); } catch { invalid++; } }
  console.log(`${lg}\tfull-catalog invalid ICU values: ${invalid}`);
}
console.log('FAILURES', bad);
process.exit(bad ? 1 : 0);
