#!/usr/bin/env python3
"""Build the QCrypt 2026 (Ottawa) CSVs from the conference site.

Pages are read from the static mirror ``~/Web/qcrypt.iaqi.org/2026/`` when
present, else fetched from https://qcrypt.net/2026/ (see ``_pages.py``):

* ``technical/accepted-papers/`` — "List of Accepted Talks" (35) + "List of
  Accepted Posters" (112): title, initials-only authors, abstract; the
  submission id is the ``abstract-<id>`` element id.
* ``schedule/``        — ``<section class=qc-day>`` per day, one ``qc-card``
  per slot with a ``HH:MM–HH:MM`` range. Contributed slots are titled
  ``#<id> <title>`` (``#8/#100`` = two merged papers sharing one slot).
* ``sessions/{tutorial,invited,industry}/<name>/`` — speaker, affiliation,
  abstract; the industry panelists are found via ``speakers/``. The
  ``sessions/lecture/*`` pages (Brassard, Pan) are leftovers from the QCrypt
  2025 site this one was cloned from — neither appears in the 2026 schedule, and
  both talks are already in ``qcrypt_2025/talks.csv`` — so they are ignored.
* ``photos_prizes/``   — paper prizes (#22, #104) and poster prizes (#28, #53),
  transcribed into ``AWARDS`` below.

Plus ``data/conferences/qcrypt_2026/raw/arxiv_matches.json`` — full author
names + arXiv ids from ``qcrypt_2026_arxiv_names.py``.

Author names: the site's HotCRP export first printed initials only ("D.
Tupkary"). Since 2026-09-29 the site carries full given names, filled in from
the private HotCRP author export. They are read from the website repo's
``data/accepted-papers-2026.json`` and ``data/posters-2026.json`` (local clone at
``~/Web/qcrypt-website``, keyed by submission id), which are version-controlled
and so more reproducible than the rendered page. Only if a submission is absent
there, or a name is still initials-only, does the old fallback apply: the arXiv
match, then per-initial expansion from the repo's other conference CSVs (see
``resolve_authors`` for the ``names=...`` tags written to ``notes``).

Outputs (``data/conferences/qcrypt_2026/``): ``talks.csv``, ``posters.csv``.

Usage: python3 tools/one_off/conf2026/convert_qcrypt_2026.py
"""
import csv
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from scrapers._lib import clean_display_name  # noqa: E402
from _pages import Site  # noqa: E402

DATA = Path(__file__).resolve().parents[3] / "data" / "conferences"
CONF = DATA / "qcrypt_2026"
RAW = CONF / "raw"  # holds only arxiv_matches.json
WEBSITE_DATA = Path.home() / 'Web' / 'qcrypt-website' / 'data'
SITE_NAME_FILES = ('accepted-papers-2026.json', 'posters-2026.json')
SITE = "https://qcrypt.net/2026"
PAGES = Site(SITE, 'qcrypt.iaqi.org')

FIELDNAMES = [
    'venue', 'year', 'paper_type', 'title', 'speakers', 'authors',
    'affiliations', 'abstract', 'arxiv_ids', 'presentation_url',
    'video_url', 'youtube_id', 'session_name', 'award', 'notes',
    'scheduled_date', 'scheduled_time', 'duration_minutes',
]

# From the PC report (sessions/slides/QCrypt 2026-Program Committee Report.pdf)
# and photos_prizes.html. #104 was upgraded to an invited talk (Yu-Huai Li).
AWARDS = {
    104: 'Best Student Paper Award (Experiment) — Min-Yan Wang',
    22: 'Best Student Paper Award (Theory) — Saliha Tokat',
    28: 'Poster Prize',
    53: 'Poster Prize',
}
UPGRADED_TO_INVITED = {104: 'li'}  # submission id -> invited session slug



def ws(s):
    return re.sub(r"\s+", " ", s or "").strip()


def fold(s):
    s = unicodedata.normalize('NFKD', s)
    return ''.join(c for c in s if not unicodedata.combining(c)).lower()


def parse_accepted():
    """-> [dict(pid, section, title, authors, abstract)] in page order."""
    out, section = [], None
    main = PAGES.soup('technical/accepted-papers').find('main')
    for el in main.find_all(['h2', 'div']):
        if el.name == 'h2':
            t = el.get_text(' ', strip=True)
            section = 'talk' if 'Talks' in t else 'poster' if 'Posters' in t else section
            continue
        if 'paper-single' not in (el.get('class') or []):
            continue
        ab = el.select_one('.paper-abstract-full')
        pid = int(ab['id'].removeprefix('abstract-'))
        if any(q['pid'] == pid for q in out):  # #100 is listed twice
            continue
        b = ab.find('b')
        if b:
            b.decompose()
        authors = [ws(a) for a in el.select_one('.paper-authors').get_text().split(';') if ws(a)]
        out.append(dict(pid=pid, section=section,
                        title=ws(el.select_one('.paper-title').get_text()),
                        authors=authors, abstract=ab.get_text().strip()))
    return out


def parse_schedule():
    """-> [dict(date, start, minutes, kind, title, speaker, affiliation, href)]."""
    out = []
    for day in PAGES.soup('schedule').select('section.qc-day'):
        date = datetime.strptime(day.select_one('.qc-day-title').get_text(strip=True),
                                 '%A, %B %d, %Y').date().isoformat()
        for row in day.select('div.qc-row'):
            a, b = row.select_one('.range').get_text(strip=True).split('–')
            minutes = int((datetime.strptime(b, '%H:%M') - datetime.strptime(a, '%H:%M')).seconds / 60)
            card = row.select_one('.qc-card')
            kind = [c for c in card.get('class') if c != 'qc-card'][0]
            sp = card.select_one('.qc-speaker')
            af = card.select_one('.qc-affiliation')
            out.append(dict(date=date, start=a, minutes=minutes, kind=kind,
                            title=ws(card.select_one('.qc-title').get_text()),
                            speaker=ws(sp.get_text()) if sp else '',
                            affiliation=ws(af.get_text()) if af else '',
                            href=card.get('href', '')))
    return out


def session_page(slug):
    """(title, speaker, affiliation, abstract) from sessions/<kind>/<name>/,
    given slug ``<kind>_<name>``."""
    strings = list(PAGES.soup('sessions/' + slug.replace('_', '/', 1)).find('main').stripped_strings)
    abstract = ''
    if 'Abstract' in strings:
        abstract = ' '.join(strings[strings.index('Abstract') + 1:])
    return strings[0], strings[2], strings[4], abstract


class NameIndex:
    """(surname, first initial) -> full names seen in the repo's other CSVs."""

    def __init__(self):
        self.idx = defaultdict(set)
        self.freq = Counter()
        for f in DATA.glob('*/*.csv'):
            if f.parent.name == 'qcrypt_2026':
                continue
            with f.open(newline='', encoding='utf-8') as fh:
                for r in csv.DictReader(fh):
                    for col in ('authors', 'speakers', 'full_name', 'name'):
                        for n in (r.get(col) or '').split(';'):
                            n = ws(n)
                            parts = n.replace('.', ' ').split()
                            # Only index real given names, not initials.
                            if len(parts) >= 2 and len(parts[0]) > 1:
                                self.idx[self.key(n)].add(n)
                                self.freq[n] += 1

    @staticmethod
    def key(name):
        parts = fold(name).replace('.', ' ').split()
        return (parts[-1], parts[0][0]) if parts else ('', '')

    def pick(self, spellings):
        """Most frequent spelling; ties -> longest, then the accented form
        ('René' > 'Rene'). Deterministic regardless of set order."""
        return max(spellings, key=lambda c: (self.freq[c], len(c), c))

    def canonical(self, name):
        """A full site name -> the repo's spelling of the same person, so the
        import does not create a duplicate author ("Adnan Adil Ebrahim Hajomer"
        -> "Adnan Hajomer", "Ernest Y.-Z Tan" -> "Ernest Y.-Z. Tan"). Matches on
        surname + first given name; keeps the site name when the repo has no such
        person or the first given name is only an initial."""
        name = re.sub(r'^(Prof|Dr)\.?\s+', '', name)
        if name in self.freq:
            return name
        parts = fold(name).replace('.', ' ').split()
        if len(parts) < 2 or len(parts[0]) < 2:
            return name
        # Common surnames (Nguyen, Li, ...): same first name is no proof.
        surname = self.key(name)[0]
        if len({i for (s, i) in self.idx if s == surname}) >= 3:
            return name
        cands = {c for c in self.idx.get(self.key(name), set())
                 if fold(c).replace('.', ' ').split()[0] == parts[0]}
        if not cands:
            return name
        best = self.pick(cands)
        # Accent-only differences: the importer folds accents, so keep the
        # site's (usually accented) spelling.
        return name if fold(best) == fold(name) else best

    def expand(self, name):
        """-> (full name | None, has_candidates)."""
        surname = self.key(name)[0]
        # Common surnames (Li, Wang, Kim, ...): several people share the surname
        # under different initials, so a lone same-initial match proves nothing.
        initials = {i for (s, i) in self.idx if s == surname}
        cands = self.idx.get(self.key(name), set())
        if len(initials) >= 3:
            return None, bool(cands)
        if not cands:
            return None, False
        # Spellings differing only in accents/middle names are one person.
        if len({fold(c).split()[0] for c in cands}) == 1:
            return self.pick(cands), True
        # Variant/typo spellings in the repo ("Anotnio Acín", "Chris Majenz"):
        # accept a clearly dominant spelling.
        # Accent-only differences count as the same spelling.
        groups = defaultdict(list)
        for c in cands:
            groups[fold(c)].append(c)
        weight = {g: sum(self.freq[c] for c in cs) for g, cs in groups.items()}
        total = sum(weight.values())
        best = max(weight, key=weight.get)
        if total >= 3 and weight[best] >= 0.75 * total:
            return self.pick(groups[best]), True
        return None, True


INITIAL = re.compile(r'^([A-Z]\.?[ -])+\S')  # "D. Tupkary", "R Wolf", "Y.-H. Li"


def dot_initials(name):
    """'A Kam' -> 'A. Kam' (consistent with the site's dotted form)."""
    return re.sub(r'\b([A-Z])(?=\s)', r'\1.', name)


def load_site_names():
    """-> {submission id: [full author names]} from the website repo's data
    files; {} when the clone is absent."""
    out = {}
    for fn in SITE_NAME_FILES:
        f = WEBSITE_DATA / fn
        if not f.exists():
            print(f"note: {f} not found — falling back to arXiv / repo-index names")
            continue
        for item in json.loads(f.read_text(encoding='utf-8')):
            out[int(item['pid'])] = [ws(f"{a.get('first', '')} {a.get('last', '')}")
                                     for a in item['authors']]
    return out


def resolve_authors(p, arxiv, names, site=None):
    """-> (authors, arxiv_id, note).

    note: ``names=site`` when the website data has full names for every author;
    ``names=arxiv`` / ``names=repo_index`` when fully resolved by the fallbacks;
    ``names=initials_new`` when the remaining initials have no same-surname
    candidate in the repo (new people — no duplicate risk);
    ``names=initials_ambiguous`` when some initial matches several repo people
    (possible duplicate author — review by hand before import)."""
    hit = arxiv.get(str(p['pid'])) or {}
    matched = not hit.get('unmatched') and hit.get('authors')
    arxiv_id = hit['arxiv_id'] if matched else ''
    site_names = (site or {}).get(p['pid'])
    if not site_names and matched:
        return [clean_display_name(a) for a in hit['authors']], arxiv_id, 'names=arxiv'
    out, new, ambiguous = [], 0, []
    for a in site_names or p['authors']:
        if not INITIAL.match(a):
            full = clean_display_name(a)
            out.append(names.canonical(full) if site_names else full)
            continue
        full, has_cands = names.expand(a)
        if full:
            out.append(full)
            continue
        out.append(dot_initials(clean_display_name(a)))
        if has_cands:
            ambiguous.append(out[-1])
        else:
            new += 1
    if ambiguous:
        note = 'names=initials_ambiguous (' + ', '.join(ambiguous) + ')'
    elif new:
        note = 'names=initials_new'
    else:
        note = 'names=site' if site_names else 'names=repo_index'
    if site_names and note != 'names=site':
        note = 'names=site; ' + note
    return out, arxiv_id if site_names else '', note


def row(**kw):
    r = {c: '' for c in FIELDNAMES}
    r.update(venue='QCRYPT', year='2026')
    r.update({k: v for k, v in kw.items() if v is not None})
    return r


def main():
    accepted = parse_accepted()
    by_pid = {p['pid']: p for p in accepted}
    arxiv = json.loads((RAW / 'arxiv_matches.json').read_text()) if (RAW / 'arxiv_matches.json').exists() else {}
    names = NameIndex()
    site = load_site_names()
    sched = parse_schedule()

    talks, seen = [], set()
    for s in sched:
        base = dict(scheduled_date=s['date'], scheduled_time=s['start'],
                    duration_minutes=str(s['minutes']))
        if s['kind'] in ('tutorial', 'invited'):
            slug = (s['href'].rstrip('/').split('sessions/')[1]
                    .removesuffix('.html').replace('/', '_').lower())
            title, speaker, aff, abstract = session_page(slug)
            title = re.sub(r'^(Tutorial|Invited) Talk:\s*', '', title)
            notes = ['source_type=claude_extraction', f"Source: {SITE}/sessions/{slug.replace('_', '/', 1)}/"]
            award, arxiv_id, authors = '', '', speaker
            for pid, inv in UPGRADED_TO_INVITED.items():
                if slug == f'invited_{inv}':
                    p = by_pid[pid]
                    full, arxiv_id, nn = resolve_authors(p, arxiv, names, site)
                    seen.add(pid)
                    award = AWARDS.get(pid, '')
                    notes += [f'submission #{pid} "{p["title"]}" upgraded to invited talk', nn]
                    if not abstract:
                        abstract = p['abstract']
            talks.append(row(paper_type=s['kind'], title=title, speakers=speaker,
                             authors=authors, affiliations=aff, abstract=abstract,
                             arxiv_ids=arxiv_id, award=award,
                             session_name=f"{s['kind'].title()} Talk",
                             notes='; '.join(notes), **base))
        elif s['title'].startswith('Industry Panel'):
            # A plain 'program' card; the per-panelist session pages carry the
            # canonical spellings (schedule says "Steve", bio says "Steeve").
            panel = sorted({'industry_' + m.lower() for m in re.findall(
                r'sessions/industry/(\w+)', PAGES.html('speakers'))})
            people = [session_page(p) for p in panel]
            talks.append(row(paper_type='industry', title=s['title'].removeprefix('Industry Panel: '),
                             speakers='; '.join(x[1] for x in people),
                             authors='; '.join(x[1] for x in people),
                             affiliations='; '.join(x[2] for x in people),
                             session_name='Industry Panel',
                             notes=f'source_type=claude_extraction; panel; Source: {SITE}/speakers/', **base))
        elif s['kind'] == 'contributed':
            m = re.match(r'Contributed Talk:\s*((?:#\d+/?)+)\s+(.*)$', s['title'])
            pids = [int(x) for x in re.findall(r'\d+', m.group(1))]
            for pid in pids:
                p = by_pid[pid]
                seen.add(pid)
                authors, arxiv_id, nn = resolve_authors(p, arxiv, names, site)
                notes = ['source_type=claude_extraction', f'submission #{pid}', nn,
                         f'Source: {SITE}/sessions/contributed/{pid}/']
                if len(pids) > 1:
                    notes.insert(2, f"merged talk ({m.group(1)}) sharing one slot")
                talks.append(row(paper_type='regular', title=p['title'],
                                 authors='; '.join(authors), abstract=p['abstract'],
                                 arxiv_ids=arxiv_id, award=AWARDS.get(pid, ''),
                                 session_name='Contributed Talk',
                                 notes='; '.join(notes), **base))

    unscheduled = [p for p in accepted if p['section'] == 'talk' and p['pid'] not in seen]
    posters = []
    for p in accepted:
        if p['section'] != 'poster':
            continue
        authors, arxiv_id, nn = resolve_authors(p, arxiv, names, site)
        posters.append(row(paper_type='poster', title=p['title'], authors='; '.join(authors),
                           abstract=p['abstract'], arxiv_ids=arxiv_id,
                           award=AWARDS.get(p['pid'], ''),
                           session_name=('Poster Session (Even Numbers), Mon 24 Aug' if p['pid'] % 2 == 0
                                         else 'Poster Session (Odd Numbers), Tue 25 Aug'),
                           notes=f"submission #{p['pid']}; {nn}; Source: {SITE}/technical/accepted-papers/",
                           scheduled_date='2026-08-24' if p['pid'] % 2 == 0 else '2026-08-25'))

    for name, rows in (('talks.csv', talks), ('posters.csv', posters)):
        with open(CONF / name, 'w', encoding='utf-8', newline='') as fh:
            w = csv.DictWriter(fh, fieldnames=FIELDNAMES)
            w.writeheader()
            w.writerows(rows)
        print(f"{name}: {len(rows)} rows")
    print('accepted:', sum(p['section'] == 'talk' for p in accepted), 'talks,',
          sum(p['section'] == 'poster' for p in accepted), 'posters')
    print('accepted talks not scheduled:', [(p['pid'], p['title'][:50]) for p in unscheduled])
    allrows = talks + posters
    for tag in ('names=site', 'names=arxiv', 'names=repo_index', 'names=initials_new', 'names=initials_ambiguous'):
        print(f'  {tag}: {sum(tag in r["notes"] for r in allrows)}')
    PAGES.report()


if __name__ == '__main__':
    main()
