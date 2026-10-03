import json, re, sys, os, collections
D = os.path.expanduser('~/oss-work/medusa/packages/admin/dashboard/src/i18n/translations')
PH = re.compile(r'\{\{\s*-?\s*([^},\s]+)[^}]*\}\}')
SUF = ('_zero','_one','_two','_few','_many','_other')
def flat(o, p=''):
    out = {}
    for k, v in o.items():
        kk = f'{p}.{k}' if p else k
        if isinstance(v, dict): out.update(flat(v, kk))
        elif isinstance(v, str): out[kk] = v
    return out
SB = re.compile(r'(?<!\{)\{([A-Za-z_][A-Za-z0-9_]*)\}(?!\})')
TAG = re.compile(r'<(\d+)>')
def phs(s): return collections.Counter(['{{%s}}' % x for x in PH.findall(s)] + ['{%s}' % x for x in SB.findall(s)] + ['<%s>' % x for x in TAG.findall(s)])
en = flat(json.load(open(f'{D}/en.json')))
rows = []
summary = {}
for fn in sorted(os.listdir(D)):
    if not fn.endswith('.json') or fn in ('en.json', '$schema.json'): continue
    loc = fn[:-5]
    tr = flat(json.load(open(f'{D}/{fn}')))
    n = {'strict':0, 'count_only_plural':0}
    for k, v in tr.items():
        ref = None
        if k in en: ref = k
        else:
            for s in SUF:
                if k.endswith(s) and k[:-len(s)] + '_other' in en:
                    ref = k[:-len(s)] + '_other'; break
        if ref is None: continue  # stale key, out of scope
        a, b = set(phs(en[ref])), set(phs(v))
        if a == b: continue
        missing, extra = sorted(a - b), sorted(b - a)
        plural = k.endswith(SUF)
        kind = 'count_only_plural' if plural and missing == ['{{count}}'] and not extra else 'strict'
        n[kind] += 1
        rows.append((loc, k, kind, ','.join(missing), ','.join(extra), en[ref].replace('\t',' ').replace('\n','\\n'), v.replace('\t',' ').replace('\n','\\n')))
    summary[loc] = n
out = os.path.expanduser(sys.argv[1] if len(sys.argv) > 1 else '~/oss-pipeline/v6-claude/medusa-proof/placeholder-audit.tsv')
with open(out, 'w') as f:
    f.write('locale\tkey\tkind\tmissing\textra\ten\ttranslation\n')
    for r in rows: f.write('\t'.join(r) + '\n')
tot = collections.Counter()
for loc, n in summary.items():
    if n['strict'] or n['count_only_plural']: print(loc, n)
    tot.update(n)
print('TOTAL', dict(tot))
