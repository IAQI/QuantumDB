#!/usr/bin/env python3
"""Scrape TQC talk data from the local archive at ~/Web/tqc.iaqi.org/.

Outputs CSV files to scraped_data/ in the same shape as the QIP and QCrypt
talk CSVs, plus an `is_proceedings_track` column.

Usage:
    python scrape_tqc_talks_historical.py [--year YEAR] [--all] [--output-dir DIR]

Coverage:
- 2017: contributions.html (invited + contributed talks)
- 2019: accepted-talks/index.html (workshop talks; flat-text format)
- 2020: accepted-papers/index.html (workshop talks; <p>-per-talk)
- 2021: program/accepted-papers/index.html (workshop talks; table)
- 2025: accepted-talks/index.html (split into proceedings vs no-proceedings)

Years 2018, 2022 archives are JS-rendered or PDF-only (no parseable HTML).
LIPIcs proceedings (Phase 2) covers the proceedings track for 2008-2023.
"""

import argparse
import csv
import re
import sys
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Any

from bs4 import BeautifulSoup, Tag

ARCHIVE_BASE = Path.home() / 'Web' / 'tqc.iaqi.org'
OUTPUT_DIR = Path(__file__).parent / 'scraped_data'

CSV_FIELDS = [
    'venue', 'year', 'paper_type', 'is_proceedings_track',
    'title', 'speakers', 'authors', 'affiliations',
    'arxiv_ids', 'session_name',
    'scheduled_date', 'scheduled_time', 'duration_minutes',
    'presentation_url', 'video_url', 'youtube_id',
    'award', 'notes',
]


# ============================================================
# Shared helpers
# ============================================================

ARXIV_NEW_RE = re.compile(r'(?<!\d)(\d{4}\.\d{4,5})(?!\d)')
ARXIV_OLD_RE = re.compile(r'(?<![\w/])([a-z\-]+/\d{7})(?!\d)')


def read_html(path: Path) -> BeautifulSoup:
    with open(path, encoding='utf-8', errors='replace') as f:
        return BeautifulSoup(f.read(), 'html.parser')


def normalize_ws(text: str) -> str:
    return ' '.join(text.split())


def extract_arxiv_ids(text: str) -> List[str]:
    if not text:
        return []
    ids = list(ARXIV_NEW_RE.findall(text))
    ids += list(ARXIV_OLD_RE.findall(text))
    seen = set()
    out = []
    for x in ids:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def extract_youtube_id(url: str) -> Optional[str]:
    if not url:
        return None
    for pat in (
        r'youtube\.com/watch\?v=([A-Za-z0-9_-]{11})',
        r'youtu\.be/([A-Za-z0-9_-]{11})',
        r'youtube\.com/embed/([A-Za-z0-9_-]{11})',
    ):
        m = re.search(pat, url)
        if m:
            return m.group(1)
    return None


def split_authors(text: str) -> List[str]:
    """Split an author string like 'A, B, C and D' into a list."""
    if not text:
        return []
    text = re.sub(r'\s+and\s+', ', ', text)
    parts = [p.strip() for p in text.split(',')]
    return [p for p in parts if p]


def parse_author_with_affiliation(text: str) -> Tuple[str, Optional[str]]:
    """Parse 'Name (Affiliation)' or 'Name, Affiliation' into (name, affiliation)."""
    text = normalize_ws(text)
    m = re.match(r'^(.+?)\s*\(([^()]+)\)\s*$', text)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return text, None


def make_talk(year: int, paper_type: str, title: str,
              authors: List[str],
              speaker: Optional[str] = None,
              affiliations: Optional[List[Optional[str]]] = None,
              session_name: str = '',
              is_proceedings_track: bool = False,
              presentation_url: str = '',
              video_url: str = '',
              notes: str = '',
              text_for_arxiv: str = '',
              ) -> Dict[str, Any]:
    title = normalize_ws(title)
    authors_clean = [normalize_ws(a) for a in authors if a and a.strip()]

    if speaker:
        speakers_str = normalize_ws(speaker)
    elif authors_clean:
        speakers_str = '; '.join(authors_clean)
    else:
        speakers_str = ''

    affiliations = affiliations or []
    affiliations_str = '; '.join(a or '' for a in affiliations)

    arxiv_ids = extract_arxiv_ids(text_for_arxiv) or extract_arxiv_ids(title)
    youtube_id = extract_youtube_id(video_url) or ''

    return {
        'venue': 'TQC',
        'year': year,
        'paper_type': paper_type,
        'is_proceedings_track': 'TRUE' if is_proceedings_track else 'FALSE',
        'title': title,
        'speakers': speakers_str,
        'authors': '; '.join(authors_clean),
        'affiliations': affiliations_str,
        'arxiv_ids': ', '.join(arxiv_ids),
        'session_name': session_name,
        'scheduled_date': '',
        'scheduled_time': '',
        'duration_minutes': '',
        'presentation_url': presentation_url,
        'video_url': video_url,
        'youtube_id': youtube_id,
        'award': '',
        'notes': notes,
    }


# ============================================================
# Year parsers
# ============================================================

def parse_2017() -> List[Dict[str, Any]]:
    """TQC 2017: contributions.html with invited + contributed talks."""
    soup = read_html(ARCHIVE_BASE / '2017' / 'contributions.html')
    talks: List[Dict[str, Any]] = []

    # Each <h2> introduces a section; the next <ul> holds the talks.
    for h2 in soup.find_all('h2'):
        section = normalize_ws(h2.get_text(' ', strip=True)).lower()
        if 'invited' in section:
            paper_type = 'invited'
        elif 'contributed' in section:
            paper_type = 'regular'
        elif 'poster' in section:
            # Skip posters per project convention.
            continue
        else:
            continue

        ul = h2.find_next('ul')
        if not ul:
            continue

        for li in ul.find_all('li', recursive=False):
            title_span = li.find('span', class_='title')
            authors_span = li.find('span', class_='authors') or li.find('span', class_='author')
            if not title_span:
                continue

            title = normalize_ws(title_span.get_text(' ', strip=True))
            if not title:
                continue

            authors_text = normalize_ws(authors_span.get_text(' ', strip=True)) if authors_span else ''
            authors = split_authors(authors_text)
            speaker = authors[0] if (paper_type == 'invited' and authors) else None
            talks.append(
                make_talk(
                    year=2017, paper_type=paper_type,
                    title=title, authors=authors, speaker=speaker,
                    session_name='Invited' if paper_type == 'invited' else 'Contributed',
                )
            )

    return talks


def parse_2019() -> List[Dict[str, Any]]:
    """TQC 2019: accepted-talks/index.html — flat text inside one <p>.

    Format: leading submission number, then "Authors: Title" per entry.
    """
    soup = read_html(ARCHIVE_BASE / '2019' / 'accepted-talks' / 'index.html')
    article = soup.find('article')
    if not article:
        return []
    content = article.find(class_='entry-content') or article
    text = content.get_text('\n', strip=True)

    # Strip the intro paragraph if present.
    text = re.sub(r'^Accepted Talks\s*\n', '', text, flags=re.I)
    text = re.sub(
        r'^The list of accepted talks for TQC 2019.*?\n',
        '', text, flags=re.I,
    )

    # Replace newlines with spaces so we can regex on a flat string.
    flat = ' '.join(text.split())

    # Submission number boundary: digits 1-3 long, surrounded by spaces.
    # We capture (Authors: Title.) chunks between submission numbers.
    # Pattern: \b\d+\b\s+(content until next \b\d+\b or end)
    parts = re.split(r'\s(?=\b\d{1,3}\b\s+[A-ZÀ-ÿ])', ' ' + flat)
    talks: List[Dict[str, Any]] = []

    for chunk in parts:
        chunk = chunk.strip()
        m = re.match(r'^(\d{1,3})\s+(.+)$', chunk)
        if not m:
            continue
        body = m.group(2)
        # Body has format "Authors: Title." possibly with " merged with NN ..."
        # Split on first ":" — but ensure the colon is the "authors:title" colon.
        if ':' not in body:
            continue
        head, tail = body.split(':', 1)
        authors_text = head.strip()
        title = tail.strip()
        # Strip trailing period and "merged with..." remnants.
        title = re.sub(r'\s*\.\s*$', '', title)
        title = re.sub(r'\s*merged with.*$', '', title, flags=re.I).strip()
        if not title or not authors_text:
            continue

        authors = split_authors(authors_text)
        if not authors:
            continue

        talks.append(
            make_talk(
                year=2019, paper_type='regular',
                title=title, authors=authors,
                session_name='Accepted',
                text_for_arxiv=body,
            )
        )

    return talks


def parse_2020() -> List[Dict[str, Any]]:
    """TQC 2020: accepted-papers/index.html — one <p> per talk, "Authors. Title"."""
    soup = read_html(ARCHIVE_BASE / '2020' / 'accepted-papers' / 'index.html')
    article = soup.find('article')
    if not article:
        return []
    content = article.find(class_='entry-content') or article

    talks: List[Dict[str, Any]] = []
    for p in content.find_all('p'):
        raw = normalize_ws(p.get_text(' ', strip=True))
        if not raw or len(raw) < 20:
            continue
        # Skip non-talk paragraphs (e.g. dates).
        if re.search(r'(?:deadline|registration|submission)', raw, re.I):
            continue

        # Authors / title boundary on this page comes in two flavours:
        #  (a) "Authors. Title"   — period directly after the last surname.
        #  (b) "Authors . Title"  — extra space before the period (typo, but
        #      consistent enough that we can rely on it as a boundary signal).
        # Match (b) first, since (a) regex would otherwise stop at an initial
        # like "Joseph M." inside the author list.
        m = re.match(r'^(.+?)\s+\.\s+([A-ZÀ-ÿĀ-ſ].+)$', raw)
        if not m:
            # (a): require a 2+ letter lowercase word right before the period
            # so we don't break on initials such as "Joseph M.".
            m = re.match(r'^(.+?[a-zà-ÿĀ-ſ]{2,})\.\s+([A-ZÀ-ÿĀ-ſ].+)$', raw)
        if not m:
            continue
        authors_text = m.group(1).strip().rstrip('.')
        title = m.group(2).strip()
        if not title or not authors_text:
            continue

        authors = split_authors(authors_text)
        if not authors:
            continue

        talks.append(
            make_talk(
                year=2020, paper_type='regular',
                title=title, authors=authors,
                session_name='Accepted',
                text_for_arxiv=raw,
            )
        )

    return talks


def parse_2021() -> List[Dict[str, Any]]:
    """TQC 2021: program/accepted-papers/index.html — table with [title, authors] columns."""
    soup = read_html(ARCHIVE_BASE / '2021' / 'program' / 'accepted-papers' / 'index.html')
    article = soup.find('article')
    if not article:
        return []
    content = article.find(class_='entry-content') or article
    talks: List[Dict[str, Any]] = []

    for table in content.find_all('table'):
        for tr in table.find_all('tr'):
            cells = tr.find_all(['td', 'th'])
            if len(cells) < 2:
                continue
            title = normalize_ws(cells[0].get_text(' ', strip=True))
            authors_text = normalize_ws(cells[1].get_text(' ', strip=True))
            if not title or not authors_text:
                continue
            # Skip header row.
            if title.lower() in ('title', 'paper', 'talk') and authors_text.lower() in ('authors', 'author'):
                continue
            authors = split_authors(authors_text)
            if not authors:
                continue
            talks.append(
                make_talk(
                    year=2021, paper_type='regular',
                    title=title, authors=authors,
                    session_name='Accepted',
                    text_for_arxiv=authors_text,
                )
            )

    return talks


def parse_2025() -> List[Dict[str, Any]]:
    """TQC 2025: accepted-talks/index.html.

    Two sections:
    - "I. Talks without proceedings" → is_proceedings_track=False
    - "II. Talks with proceedings" → is_proceedings_track=True

    Each talk is an outer <li> with <strong>Title</strong> followed by a nested
    <ul><li><em>Author1 (Affil), Author2 (Affil), ...</em></li></ul>.
    """
    soup = read_html(ARCHIVE_BASE / '2025' / 'accepted-talks' / 'index.html')
    article = soup.find('article')
    if not article:
        return []
    content = article.find(class_='entry-content') or article

    talks: List[Dict[str, Any]] = []
    current_section = None  # 'workshop' | 'proceedings'

    for el in content.descendants:
        if not isinstance(el, Tag):
            continue
        if el.name in ('h2', 'h3', 'h4'):
            text = normalize_ws(el.get_text(' ', strip=True)).lower()
            if 'without proceedings' in text or 'no proceedings' in text:
                current_section = 'workshop'
            elif 'with proceedings' in text or 'proceedings track' in text:
                current_section = 'proceedings'
            elif 'invited' in text or 'tutorial' in text or 'keynote' in text:
                # Could extend later; ignore for now.
                current_section = None
        elif el.name == 'ol' and current_section:
            for li in el.find_all('li', recursive=False):
                talk = _parse_2025_talk(li, current_section)
                if talk:
                    talks.append(talk)
            current_section = None  # consume the list
    return talks


def _parse_2025_talk(li: Tag, section: str) -> Optional[Dict[str, Any]]:
    # Title is in the first <strong> direct child.
    strong = li.find('strong')
    if not strong:
        return None
    title = normalize_ws(strong.get_text(' ', strip=True))
    if not title or len(title) < 3:
        return None

    # Authors are inside a nested <ul><li><em>...</em></li>.
    nested_ul = li.find('ul')
    authors_text = ''
    if nested_ul:
        em = nested_ul.find('em')
        if em:
            authors_text = normalize_ws(em.get_text(' ', strip=True))
        else:
            authors_text = normalize_ws(nested_ul.get_text(' ', strip=True))

    authors_raw = split_authors_with_parens(authors_text)
    authors = [a[0] for a in authors_raw]
    affiliations = [a[1] for a in authors_raw]

    is_proceedings = (section == 'proceedings')
    return make_talk(
        year=2025, paper_type='regular',
        title=title, authors=authors,
        affiliations=affiliations,
        session_name='Talks with proceedings' if is_proceedings else 'Talks without proceedings',
        is_proceedings_track=is_proceedings,
        text_for_arxiv=authors_text,
    )


def split_authors_with_parens(text: str) -> List[Tuple[str, Optional[str]]]:
    """Split 'Name1 (Affil1), Name2 (Affil2), Name3' into [(name, affil), ...].

    Splits only on commas that are OUTSIDE parentheses.
    """
    out: List[Tuple[str, Optional[str]]] = []
    if not text:
        return out
    depth = 0
    buf = []
    for ch in text:
        if ch == '(':
            depth += 1
            buf.append(ch)
        elif ch == ')':
            depth = max(0, depth - 1)
            buf.append(ch)
        elif ch == ',' and depth == 0:
            chunk = ''.join(buf).strip()
            if chunk:
                out.append(parse_author_with_affiliation(chunk))
            buf = []
        else:
            buf.append(ch)
    if buf:
        chunk = ''.join(buf).strip()
        if chunk:
            out.append(parse_author_with_affiliation(chunk))
    return out


PARSERS = {
    2017: parse_2017,
    2019: parse_2019,
    2020: parse_2020,
    2021: parse_2021,
    2025: parse_2025,
}


# ============================================================
# CSV output / CLI
# ============================================================

def save_csv(year: int, talks: List[Dict[str, Any]], output_dir: Path,
             force: bool = False) -> Optional[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / f'tqc_{year}_workshop_talks.csv'

    if output_file.exists() and not force:
        print(f'  Skipping {output_file} (already exists, use --force to overwrite)')
        return None

    with open(output_file, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS, quoting=csv.QUOTE_MINIMAL)
        writer.writeheader()
        for t in talks:
            writer.writerow(t)
    return output_file


def scrape_year(year: int, output_dir: Path, force: bool = False) -> bool:
    if year not in PARSERS:
        print(f'  No parser for TQC {year}')
        return False

    print(f'Scraping TQC {year} talks...')
    try:
        talks = PARSERS[year]()
    except Exception as exc:
        import traceback
        print(f'  ERROR scraping TQC {year}: {exc}')
        traceback.print_exc()
        return False

    if not talks:
        print(f'  WARNING: No talks parsed for TQC {year}')
        return False

    # Deduplicate on (title, year).
    seen = set()
    unique = []
    for t in talks:
        key = (t['title'].lower().strip(), t['year'])
        if key not in seen:
            seen.add(key)
            unique.append(t)

    output_file = save_csv(year, unique, output_dir, force)
    if output_file:
        print(f'  Saved {len(unique)} talks to {output_file}')
    return True


def main():
    parser = argparse.ArgumentParser(description='Scrape TQC historical talk data')
    parser.add_argument('--year', type=int, help='Specific year to scrape')
    parser.add_argument('--all', action='store_true', help='Scrape all years with parsers')
    parser.add_argument('--output-dir', type=str, default=str(OUTPUT_DIR),
                        help=f'Output directory (default: {OUTPUT_DIR})')
    parser.add_argument('--force', action='store_true', help='Overwrite existing files')
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    if args.year:
        scrape_year(args.year, output_dir, args.force)
    elif args.all:
        success = 0
        for year in sorted(PARSERS):
            if scrape_year(year, output_dir, args.force):
                success += 1
        print(f'\nDone: {success}/{len(PARSERS)} years scraped successfully.')
    else:
        parser.print_help()
        print(f'\nAvailable years: {sorted(PARSERS)}')


if __name__ == '__main__':
    main()
