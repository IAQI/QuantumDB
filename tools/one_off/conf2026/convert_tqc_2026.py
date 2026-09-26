#!/usr/bin/env python3
"""Build the TQC 2026 (Sherbrooke) CSVs from the saved live-site pages.

Inputs (``data/conferences/tqc_2026/raw/``, saved from https://tqc-conference.org/2026/):

* ``accepted-papers.html``  — 87 accepted contributed talks: title, authors with
  ``(affiliation)``, the presenter in ``<strong>``, abstract, and a ``[proceedings]``
  DOI link for the 8 papers in LIPIcs vol. 389.
* ``accepted-posters.html`` — 289 accepted posters (same markup).
* ``schedule.html``         — ``<article id=day_YYYY-MM-DD>`` per day; each
  parallel session lists its talks in order (presenter in ``<em>``).
* ``lipics-vol389.html``    — the Dagstuhl volume page (cross-check of the 8 DOIs).

Outputs (``data/conferences/tqc_2026/``):

* ``proceedings.csv`` — the 8 LIPIcs papers (``session_name = Proceedings track (LIPIcs)``).
* ``workshop.csv``    — the other contributed talks + the 4 invited talks.
* ``posters.csv``     — all accepted posters.

Talks sit in 30-minute slots (20 min + 5 min Q&A + changeover); a talk's
``scheduled_time`` is its session start + 30 min x its position in the session.
Idempotent: rerunning overwrites the three CSVs.

Usage: python3 tools/one_off/conf2026/convert_tqc_2026.py
"""
import csv
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scrapers._lib import clean_display_name  # noqa: E402

CONF = Path(__file__).resolve().parents[3] / "data" / "conferences" / "tqc_2026"
RAW = CONF / "raw"
SITE = "https://tqc-conference.org/2026"
SLOT_MINUTES = 30
INVITED_MINUTES = 60

FIELDNAMES = [
    'venue', 'year', 'paper_type', 'title', 'speakers', 'authors',
    'affiliations', 'abstract', 'arxiv_ids', 'presentation_url',
    'video_url', 'youtube_id', 'session_name', 'award', 'notes',
    'scheduled_date', 'scheduled_time', 'duration_minutes',
]


def soup(name):
    return BeautifulSoup((RAW / name).read_text(encoding='utf-8'), 'html.parser')


AWARD_RE = re.compile(r"\s*\((?:Winner of the )?(Best [^()]*?Award)!?\)\s*$")


def split_award(title):
    """'X (Winner of the Best Paper Award!)' -> ('X', 'Best Paper Award')."""
    m = AWARD_RE.search(title)
    return (title[:m.start()], m.group(1)) if m else (title, '')


def norm_title(s):
    s = split_award(s)[0]
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", "", s.lower())).strip()


def ws(s):
    return re.sub(r"\s+", " ", s or "").strip()


def split_authors(div):
    """``Name (Affil); <strong>Name</strong> (Affil); ...`` ->
    (names, affiliations, presenters)."""
    presenters = [clean_display_name(ws(s.get_text())) for s in div.find_all('strong')]
    names, affs = [], []
    for part in split_top_level(ws(div.get_text())):
        name, aff = part, ''
        # Affiliation = the trailing balanced (...) group; names may carry their
        # own parens ("Yifan (Frank) Zhang (UC Berkeley)").
        if part.endswith(')'):
            depth = 0
            for i in range(len(part) - 1, -1, -1):
                depth += {')': 1, '(': -1}.get(part[i], 0)
                if depth == 0:
                    name, aff = part[:i], part[i + 1:-1]
                    break
        names.append(clean_display_name(ws(name)))
        # Multiple affiliations are ';'-separated inside the parens; ';' would
        # corrupt the ';'-joined cell, so fold to ',' (as the poster parsers do).
        affs.append(ws(aff.replace(';', ',')))
    return names, affs, presenters


def split_top_level(text):
    """Split on ';' outside parentheses."""
    parts, depth, cur = [], 0, ''
    for ch in text:
        depth += {'(': 1, ')': -1}.get(ch, 0)
        if ch == ';' and depth == 0:
            parts.append(cur)
            cur = ''
        else:
            cur += ch
    parts.append(cur)
    return [p.strip() for p in parts if p.strip()]


def parse_list(name):
    out = []
    for p in soup(name).select('.paper-single'):
        names, affs, presenters = split_authors(p.select_one('.paper-authors'))
        ab = p.select_one('.paper-abstract-full')
        abstract = ''
        if ab:
            b = ab.find('b')
            if b:
                b.decompose()
            abstract = ab.get_text().strip()
        doi = ''
        pr = p.select_one('.paper-proceedings a')
        if pr:
            doi = pr['href'].replace('https://doi.org/', '')
        title, award = split_award(ws(p.select_one('.paper-title').get_text()))
        out.append(dict(title=title, award=award,
                        authors=names, affiliations=affs, speakers=presenters,
                        abstract=abstract, doi=doi))
    return out


def parse_schedule():
    """-> {norm_title: dict(date, time, session, room, presenter)}, [invited]."""
    s = soup('schedule.html')
    talks, invited = {}, []
    for day in s.select('article.day'):
        date = day['id'].removeprefix('day_')
        for sess in day.select('div.session'):
            hh = sess.select_one('.hh').get_text(strip=True)
            mm = sess.select_one('.mm').get_text(strip=True)
            start = datetime.strptime(f"{date} {hh}:{mm}", "%Y-%m-%d %H:%M")
            classes = sess.get('class') or []
            h4 = ws(sess.select_one('h4').get_text())
            href = (sess.select_one('a') or {}).get('href', '')
            if 'tag-invited' in classes:
                m = re.match(r'Invited Speaker:\s*(.*?)\s*[—-]\s*["“](.*)["”]\s*$', h4)
                invited.append(dict(speaker=m.group(1), title=m.group(2), date=date,
                                    time=start.strftime('%H:%M'), href=href))
                continue
            if 'tag-track' not in classes:
                continue
            room = ws(sess.select_one('.location-label').get_text())
            track = ws(sess.select_one('.location-description').get_text())
            num = re.search(r'contributed(\d+)', href).group(1)
            session_name = f"Session {num} {track}: {h4}"
            for i, li in enumerate(sess.select('li.paper-short')):
                em = li.select_one('.paper-authors em')
                talks[norm_title(li.select_one('.paper-title').get_text())] = dict(
                    date=date,
                    time=(start + timedelta(minutes=SLOT_MINUTES * i)).strftime('%H:%M'),
                    session=session_name, room=room,
                    presenter=clean_display_name(ws(em.get_text())) if em else '')
    return talks, invited


def speaker_affiliations():
    """Invited speakers' affiliations from speakers.html."""
    out = {}
    text = [ws(t) for t in soup('speakers.html').find('main').stripped_strings]
    for i, t in enumerate(text):
        if t.startswith('/2026/sessions/invited_') and i + 2 < len(text):
            out[text[i + 1]] = text[i + 2]
    return out


# The invited-speaker page bio identifies "Greg Meyer" as Greg Kahanamoku-Meyer;
# use the spelling already present in the repo's CSVs so he resolves to one author.
NAME_FIXES = {'Greg Meyer': 'Greg Kahanamoku-Meyer'}


def invited_abstract(href):
    """Abstract text from a saved session page (raw/session_<slug>.html)."""
    path = RAW / f"session_{href.strip('/').rsplit('/', 1)[1]}.html"
    if not path.exists():
        return ''
    text = ' '.join(soup(path.name).find('main').stripped_strings)
    i = text.rfind('Abstract')
    return text[i + len('Abstract'):].strip() if i >= 0 else ''


def row(**kw):
    r = {c: '' for c in FIELDNAMES}
    r.update(venue='TQC', year='2026')
    r.update({k: v for k, v in kw.items() if v is not None})
    return r


def main():
    papers = parse_list('accepted-papers.html')
    posters = parse_list('accepted-posters.html')
    sched, invited = parse_schedule()
    lipics = set(re.findall(r'LIPIcs\.TQC\.2026\.(\d+)', (RAW / 'lipics-vol389.html').read_text()))
    lipics.discard('0')

    proceedings, workshop, unscheduled = [], [], []
    for p in papers:
        s = sched.get(norm_title(p['title']))
        notes = ['source_type=claude_extraction', f'Source: {SITE}/accepted-papers/']
        speakers = p['speakers']
        if s:
            notes.append(f"room={s['room']}")
            # The schedule's <em> presenter is authoritative when it disagrees.
            if s['presenter'] and s['presenter'] not in speakers:
                notes.append(f"presenter per schedule: {s['presenter']}")
                speakers = [s['presenter']]
        else:
            unscheduled.append(p['title'])
            notes.append('not in published schedule')
        pres_url = ''
        if p['doi']:
            n = p['doi'].rsplit('.', 1)[1]
            assert n in lipics, p['doi']
            pres_url = ('https://drops.dagstuhl.de/storage/00lipics/lipics-vol389-tqc2026/'
                        f'LIPIcs.TQC.2026.{n}/LIPIcs.TQC.2026.{n}.pdf')
            notes.insert(0, f"DOI: {p['doi']}; LIPIcs proceedings (Dagstuhl)")
        r = row(paper_type='regular', title=p['title'],
                speakers='; '.join(speakers), authors='; '.join(p['authors']),
                affiliations='; '.join(p['affiliations']) if any(p['affiliations']) else '',
                abstract=p['abstract'], presentation_url=pres_url, award=p['award'],
                session_name='Proceedings track (LIPIcs)' if p['doi'] else (s['session'] if s else ''),
                notes='; '.join(notes),
                scheduled_date=s['date'] if s else '', scheduled_time=s['time'] if s else '',
                duration_minutes=str(SLOT_MINUTES) if s else '')
        if p['doi'] and s:
            r['notes'] += f"; session={s['session']}"
        (proceedings if p['doi'] else workshop).append(r)

    affs = speaker_affiliations()
    for inv in invited:
        notes = ['source_type=claude_extraction',
                 f"Source: https://tqc-conference.org{inv['href']}"]
        speaker = inv['speaker']
        if speaker in NAME_FIXES:
            notes.append(f"listed on site as {speaker}")
            speaker = NAME_FIXES[speaker]
        workshop.append(row(
            paper_type='invited', title=inv['title'], speakers=speaker,
            authors=speaker, affiliations=affs.get(inv['speaker'], ''),
            abstract=invited_abstract(inv['href']),
            session_name='Invited Talk',
            notes='; '.join(notes),
            scheduled_date=inv['date'], scheduled_time=inv['time'],
            duration_minutes=str(INVITED_MINUTES)))

    poster_rows = [row(
        paper_type='poster', title=p['title'], speakers='; '.join(p['speakers']),
        authors='; '.join(p['authors']),
        affiliations='; '.join(p['affiliations']) if any(p['affiliations']) else '',
        abstract=p['abstract'],
        session_name='Poster sessions (Mon 31 Aug + Tue 1 Sep)',
        notes=f'Source: {SITE}/accepted-posters/') for p in posters]

    key = lambda r: (r['scheduled_date'] or '9', r['scheduled_time'], r['session_name'])
    for name, rows in (('proceedings.csv', sorted(proceedings, key=key)),
                       ('workshop.csv', sorted(workshop, key=key)),
                       ('posters.csv', poster_rows)):
        with open(CONF / name, 'w', encoding='utf-8', newline='') as fh:
            w = csv.DictWriter(fh, fieldnames=FIELDNAMES)
            w.writeheader()
            w.writerows(rows)
        print(f"{name}: {len(rows)} rows")

    matched = sum(1 for p in papers if norm_title(p['title']) in sched)
    print(f"schedule: {len(sched)} talk slots, {matched}/{len(papers)} accepted papers matched")
    print("unscheduled:", unscheduled)
    stray = set(sched) - {norm_title(p['title']) for p in papers}
    print("schedule titles not in accepted list:", stray)


if __name__ == '__main__':
    main()
