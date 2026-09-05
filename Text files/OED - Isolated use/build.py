"""Filter the OED "isolated use" search exports down to words the OED has only one
source for at all.  Writes the theme list, glossary and annotated CSV alongside this
script.  See README.md for the reasoning behind each signal.

Reads every `OED Search Export*.csv` in this folder.  A file whose name contains
"Last use" is treated as a last-use-filtered slice and is used to resolve entries
whose printed date is open-ended; see `resolve_open()` and the README.
"""

import collections, csv, glob, os, re, sys, unicodedata

csv.field_size_limit(10**9)
SRC    = os.path.dirname(os.path.abspath(__file__))
MASTER = os.path.join(os.path.dirname(SRC), 'Word List - OED.csv')


def norm(s):
    """Crossword-normalised form: unaccented A-Z only, uppercase."""
    s = unicodedata.normalize('NFKD', s or '')
    s = ''.join(c for c in s if not unicodedata.combining(c))
    return re.sub(r'[^A-Za-z]', '', s).upper()


def dateshape(d):
    """What the OED's printed date range tells us about the spread of evidence.

    'open' means only that the entry is not marked obsolete -- it does NOT imply
    more than one quotation.  demi-world prints as '1862-' on a single 1862 source.
    """
    d = (d or '').strip()
    if not d:           return 'unknown'
    if d.endswith('-'): return 'open'           # last-quotation year is hidden
    if re.search(r'\d\s*[-–—]', d) or re.match(r'^Old English\s*[-–]', d):
        return 'range'                          # evidence at >= 2 separated dates
    return 'single'                             # all evidence in one year


def firstyear(d):
    if d.strip().startswith('Old English'): return 1000
    m = re.search(r'(\d{3,4})', d)
    return int(m.group(1)) if m else 9999


def read_export(path):
    """Return the entry rows, plus the from/to bounds declared in the file footer."""
    lo, hi, out = None, None, []
    with open(path, encoding='utf-8-sig', newline='') as fh:
        for x in csv.DictReader(fh):
            url = (x.get('OED URL') or '').strip()
            if url.startswith('http://www.oed.com/dictionary/'):
                out.append(x)
            elif 'dateOfUse' in (x.get('LEMMA') or ''):
                foot = x['LEMMA']
                m = re.search(r'dateOfUseFrom=(\d+)', foot); lo = int(m.group(1)) if m else 0
                m = re.search(r'dateOfUseTo=(\d+)', foot);   hi = int(m.group(1)) if m else 9999
    return out, (lo if lo is not None else 0, hi if hi is not None else 9999)


# ---------------------------------------------------------------- load exports
iso, seen_urls, lastuse = [], set(), {}
for f in sorted(glob.glob(os.path.join(SRC, 'OED Search Export*.csv'))):
    entries, (lo, hi) = read_export(f)
    if 'last use' in os.path.basename(f).lower():
        for x in entries:                       # last use lies somewhere in [lo, hi]
            u = x['OED URL'].strip()
            p = lastuse.get(u, (0, 9999))
            lastuse[u] = (max(p[0], lo), min(p[1], hi))
        print(f'  last-use slice {lo}-{hi}: {len(entries)} entries', file=sys.stderr)
        continue
    for x in entries:
        url = x['OED URL'].strip()
        if url not in seen_urls:
            seen_urls.add(url)
            iso.append(x)
print(f'isolated-use entries loaded: {len(iso)}'
      f' ({len(lastuse)} carrying last-use bounds)', file=sys.stderr)

# --------------------------------- index the current-use OED by crossword form
by_form = collections.defaultdict(list)
with open(MASTER, encoding='utf-8', newline='') as fh:
    for x in csv.DictReader(fh):
        k = norm(x['LEMMA'])
        if k:
            by_form[k].append((x['OBSOLESCENCE'], (x['OED URL'] or '').strip()))

# -------------------------------------------------------------------- annotate
rows = []
for x in iso:
    url  = x['OED URL'].strip()
    slug = url.rsplit('/', 1)[-1]
    form = norm(x['LEMMA'])
    others = [o for o in by_form.get(form, []) if o[1] != url]

    r = dict(lemma=x['LEMMA'], form=form, length=len(form), pos=x['PART OF SPEECH'],
             date=x['DATE OF USE'], band=x['FREQUENCY BAND NUMBER'],
             obs=x['OBSOLESCENCE'], formation=x['TYPE OF FORMATION'],
             usage=x['USAGE'], subject=x['SUBJECT'], definition=x['DEFINITION'],
             url=url, shape=dateshape(x['DATE OF USE']),
             first_year=firstyear(x['DATE OF USE']),
             other_current=sum(1 for o in others if o[0] == 'In current use'),
             # the OED appends a homograph number when a headword+PoS has siblings
             homograph=bool(re.search(r'_[a-z]+\d+$', slug)))
    # three independent tests that the letter-string is also some other English word
    r['collides'] = bool(r['other_current']) or r['homograph'] or r['formation'] == 'conversion'
    r['evidence'] = 'printed date range'
    rows.append(r)


def resolve_open(r):
    """Use last-use bounds to settle an entry whose printed date is open-ended.

    Last use falls somewhere in [lo, hi].  If lo > first_year the entry has evidence
    at a later date, so it is not a one-source word.  If hi <= first_year then last
    equals first and all its evidence sits in a single year.
    """
    lo, hi = lastuse.get(r['url'], (None, None))
    if lo is None:
        return
    if lo > r['first_year']:
        r['shape'], r['evidence'] = 'range', f'last use in {lo}-{hi}'
    elif hi <= r['first_year']:
        r['shape'], r['evidence'] = 'single', f'last use <= {hi}'
    else:
        r['evidence'] = f'last use in {lo}-{hi}, still unresolved'


for r in rows:
    if r['shape'] == 'open':
        resolve_open(r)


def tier(r):
    if r['shape'] == 'single':
        return ('1 - single year of evidence, form unique' if not r['collides']
                else '2 - single year of evidence, but form is another word too')
    if r['shape'] == 'range':
        return '3 - evidence at two or more separated dates'
    if r['shape'] == 'open':
        return '4 - unresolved: not marked obsolete, last-quotation year hidden'
    return '5 - no date'


for r in rows:
    r['tier'] = tier(r)
print(collections.Counter(r['tier'] for r in rows).most_common(), file=sys.stderr)

# ----------------------------------------------------------------------- write
with open(os.path.join(SRC, 'Isolated uses - annotated.csv'), 'w',
          encoding='utf-8-sig', newline='') as fh:
    w = csv.writer(fh)
    w.writerow(['tier', 'lemma', 'crossword_form', 'length', 'pos', 'date', 'first_year',
                'evidence', 'formation', 'band', 'usage', 'subject', 'definition',
                'other_current_oed_forms', 'oed_homograph_number', 'url'])
    for r in sorted(rows, key=lambda r: (r['tier'], r['length'], r['form'])):
        w.writerow([r['tier'], r['lemma'], r['form'], r['length'], r['pos'], r['date'],
                    r['first_year'], r['evidence'], r['formation'], r['band'], r['usage'],
                    r['subject'], r['definition'], r['other_current'],
                    'yes' if r['homograph'] else '', r['url']])

seen, uniq = set(), []
for r in sorted((r for r in rows if r['tier'].startswith('1')),
                key=lambda r: (r['length'], r['form'])):
    if r['form'] not in seen:
        seen.add(r['form'])
        uniq.append(r)
print(f'theme list: {len(uniq)} distinct forms', file=sys.stderr)

with open(os.path.join(SRC, 'Isolated uses - theme list.txt'), 'w',
          encoding='utf-8', newline='\n') as fh:
    fh.writelines(r['form'] + '\n' for r in uniq)

with open(os.path.join(SRC, 'Isolated uses - theme list (CC).txt'), 'w',
          encoding='utf-8', newline='\n') as fh:
    fh.writelines(f"{r['form']},50\n" for r in uniq)

with open(os.path.join(SRC, 'Isolated uses - glossary.csv'), 'w',
          encoding='utf-8-sig', newline='') as fh:
    w = csv.writer(fh)
    w.writerow(['crossword_form', 'length', 'lemma', 'pos', 'date', 'formation',
                'definition', 'url'])
    for r in uniq:
        w.writerow([r['form'], r['length'], r['lemma'], r['pos'], r['date'],
                    r['formation'], r['definition'], r['url']])

# the still-open pool, so it can be triaged by hand or fed a last-use export
un = [r for r in rows if r['tier'].startswith('4')]
with open(os.path.join(SRC, 'Isolated uses - unresolved.csv'), 'w',
          encoding='utf-8-sig', newline='') as fh:
    w = csv.writer(fh)
    w.writerow(['lemma', 'crossword_form', 'length', 'pos', 'date', 'first_year',
                'band', 'formation', 'definition', 'evidence', 'url'])
    for r in sorted(un, key=lambda r: (r['first_year'], r['form'])):
        w.writerow([r['lemma'], r['form'], r['length'], r['pos'], r['date'],
                    r['first_year'], r['band'], r['formation'], r['definition'],
                    r['evidence'], r['url']])
print(f'unresolved: {len(un)}', file=sys.stderr)
