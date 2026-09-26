#!/usr/bin/env python3
"""Build the QCrypt 2026 (Ottawa) CSVs from the saved live-site pages.

Inputs (``data/conferences/qcrypt_2026/raw/``, saved from https://qcrypt.net/2026/):

* ``accepted-papers.html`` — "List of Accepted Talks" (35) + "List of Accepted
  Posters" (112): title, initials-only authors, abstract; the submission id is
  the ``abstract-<id>`` element id.
* ``schedule.html``        — ``<section class=qc-day>`` per day, one
  ``qc-card`` per slot with a ``HH:MM–HH:MM`` range. Contributed slots are titled
  ``#<id> <title>`` (``#8/#100`` = two merged papers sharing one slot).
* ``session_<kind>_<name>.html`` — tutorial / invited / industry-panel pages
  (speaker, affiliation, abstract). The ``lecture_*`` pages (Brassard, Pan) are
  leftovers from the QCrypt 2025 site this one was cloned from — neither appears
  in the 2026 schedule, and both talks are already in ``qcrypt_2025/talks.csv`` —
  so they are ignored.
* ``photos_prizes.html``   — paper prizes (#22, #104) and poster prizes (#28, #53).
* ``arxiv_matches.json``   — full author names + arXiv ids from
  ``qcrypt_2026_arxiv_names.py``.

Author names: the site prints initials ("D. Tupkary"). Each list is expanded to
full names from its arXiv match when one was found; otherwise each initial is
expanded individually when exactly one full name with that surname + first
initial exists in the repo's other conference CSVs. Rows that still carry
initials are tagged ``names=initials_unresolved`` in ``notes``.

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

from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scrapers._lib import clean_display_name  # noqa: E402

DATA = Path(__file__).resolve().parents[3] / "data" / "conferences"
CONF = DATA / "qcrypt_2026"
RAW = CONF / "raw"
SITE = "https://qcrypt.net/2026"

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
    22: 'Best Student Paper Award (Theory) — S. Tokat',
    28: 'Poster Prize',
    53: 'Poster Prize',
}
UPGRADED_TO_INVITED = {104: 'li'}  # submission id -> invited session slug


def soup(name):
    return BeautifulSoup((RAW / name).read_text(encoding='utf-8'), 'html.parser')


def ws(s):
    return re.sub(r"\s+", " ", s or "").strip()


def fold(s):
    s = unicodedata.normalize('NFKD', s)
    return ''.join(c for c in s if not unicodedata.combining(c)).lower()


def parse_accepted():
    """-> [dict(pid, section, title, authors, abstract)] in page order."""
    out, section = [], None
    main = soup('accepted-papers.html').find('main')
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
    for day in soup('schedule.html').select('section.qc-day'):
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
    """(title, speaker, affiliation, abstract) from raw/session_<slug>.html."""
    strings = list(soup(f'session_{slug}.html').find('main').stripped_strings)
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
            return max(cands, key=len), True
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
            return max(groups[best], key=lambda c: (self.freq[c], len(c))), True
        return None, True


INITIAL = re.compile(r'^([A-Z]\.?[ -])+\S')  # "D. Tupkary", "R Wolf", "Y.-H. Li"


def dot_initials(name):
    """'A Kam' -> 'A. Kam' (consistent with the site's dotted form)."""
    return re.sub(r'\b([A-Z])(?=\s)', r'\1.', name)


def resolve_authors(p, arxiv, names):
    """-> (authors, arxiv_id, note).

    note: ``names=arxiv`` / ``names=repo_index`` when fully resolved;
    ``names=initials_new`` when the remaining initials have no same-surname
    candidate in the repo (new people — no duplicate risk);
    ``names=initials_ambiguous`` when some initial matches several repo people
    (possible duplicate author — review by hand before import)."""
    hit = arxiv.get(str(p['pid'])) or {}
    if not hit.get('unmatched') and hit.get('authors'):
        return [clean_display_name(a) for a in hit['authors']], hit['arxiv_id'], 'names=arxiv'
    out, new, ambiguous = [], 0, []
    for a in p['authors']:
        if not INITIAL.match(a):
            out.append(clean_display_name(a))
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
        note = 'names=repo_index'
    return out, '', note


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
    sched = parse_schedule()

    talks, seen = [], set()
    for s in sched:
        base = dict(scheduled_date=s['date'], scheduled_time=s['start'],
                    duration_minutes=str(s['minutes']))
        if s['kind'] in ('tutorial', 'invited'):
            slug = s['href'].rstrip('/').split('/sessions/')[1].replace('/', '_').lower()
            title, speaker, aff, abstract = session_page(slug)
            title = re.sub(r'^(Tutorial|Invited) Talk:\s*', '', title)
            notes = ['source_type=claude_extraction', f"Source: {SITE}/sessions/{slug.replace('_', '/', 1)}/"]
            award, arxiv_id, authors = '', '', speaker
            for pid, inv in UPGRADED_TO_INVITED.items():
                if slug == f'invited_{inv}':
                    p = by_pid[pid]
                    full, arxiv_id, nn = resolve_authors(p, arxiv, names)
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
            panel = sorted(f.stem.removeprefix('session_') for f in RAW.glob('session_industry_*.html'))
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
                authors, arxiv_id, nn = resolve_authors(p, arxiv, names)
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
        authors, arxiv_id, nn = resolve_authors(p, arxiv, names)
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
    for tag in ('names=arxiv', 'names=repo_index', 'names=initials_new', 'names=initials_ambiguous'):
        print(f'  {tag}: {sum(tag in r["notes"] for r in allrows)}')


if __name__ == '__main__':
    main()
