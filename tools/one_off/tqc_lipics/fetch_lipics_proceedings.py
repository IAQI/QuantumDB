#!/usr/bin/env python3
"""Fetch TQC proceedings track papers from LIPIcs (Dagstuhl).

Each TQC year 2013-2025 has a LIPIcs volume page that lists all proceedings
papers as cards with structured metadata (title, authors, DOI, PDF URL).
This script fetches each volume page, parses the cards, and emits one CSV
per year to ../scraped_data/tqc_{year}_proceedings_talks.csv.

Raw HTML is cached in ./cache/ so re-runs don't re-hit Dagstuhl.

Usage:
    python fetch_lipics_proceedings.py [--year YEAR] [--all] [--no-cache] [--force]

Note: TQC pre-2013 was not published on LIPIcs. The seed file's old-style
semnr URLs for 2008-2012 redirect to unrelated conferences in the new
DROPS frontend, so this script covers 2013-2025 only.
"""

import argparse
import csv
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import List, Dict, Optional, Any

from bs4 import BeautifulSoup

SCRIPT_DIR = Path(__file__).parent
CACHE_DIR = SCRIPT_DIR / 'cache'
OUTPUT_DIR = SCRIPT_DIR.parent / 'scraped_data'

# LIPIcs volume IDs per TQC year, harvested from
# https://drops.dagstuhl.de/entities/conference/TQC.
VOLUME_BY_YEAR = {
    2013: 22,
    2014: 27,
    2015: 44,
    2016: 61,
    2017: 73,
    2018: 111,
    2019: 135,
    2020: 158,
    2021: 197,
    2022: 232,
    2023: 266,
    2024: 310,
    2025: 350,
}

VOLUME_URL_TPL = 'https://drops.dagstuhl.de/entities/volume/LIPIcs-volume-{volid}'
USER_AGENT = 'QuantumDB-LIPIcs-Fetcher/1.0 (https://github.com/IAQI/QuantumDB)'

CSV_FIELDS = [
    'venue', 'year', 'paper_type', 'is_proceedings_track',
    'title', 'speakers', 'authors', 'affiliations',
    'arxiv_ids', 'session_name',
    'scheduled_date', 'scheduled_time', 'duration_minutes',
    'presentation_url', 'video_url', 'youtube_id',
    'award', 'notes',
]

ARXIV_NEW_RE = re.compile(r'(?<!\d)(\d{4}\.\d{4,5})(?!\d)')
ARXIV_OLD_RE = re.compile(r'(?<![\w/])([a-z\-]+/\d{7})(?!\d)')


# ============================================================
# Network helpers
# ============================================================

def fetch_volume_html(year: int, use_cache: bool = True) -> str:
    """Fetch volume HTML, caching to disk."""
    volid = VOLUME_BY_YEAR[year]
    cache_path = CACHE_DIR / f'tqc_{year}_volume_{volid}.html'

    if use_cache and cache_path.exists():
        return cache_path.read_text(encoding='utf-8', errors='replace')

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    url = VOLUME_URL_TPL.format(volid=volid)
    req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read().decode('utf-8', errors='replace')
    except urllib.error.URLError as exc:
        raise RuntimeError(f'Failed to fetch {url}: {exc}')

    cache_path.write_text(data, encoding='utf-8')
    return data


# ============================================================
# Parsing
# ============================================================

def lipics_authors_to_full_names(raw_authors: List[str]) -> List[str]:
    """Convert ['Fawzi, Omar', 'Walter, Michael'] to ['Omar Fawzi', 'Michael Walter']."""
    out = []
    for a in raw_authors:
        a = a.strip()
        if not a:
            continue
        # LIPIcs always uses "Family, Given" format.
        if ',' in a:
            family, given = a.split(',', 1)
            out.append(f'{given.strip()} {family.strip()}')
        else:
            out.append(a)
    return out


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


def parse_volume(html: str, year: int) -> List[Dict[str, Any]]:
    """Parse a LIPIcs volume page into a list of talk dicts."""
    soup = BeautifulSoup(html, 'html.parser')
    talks: List[Dict[str, Any]] = []

    for card in soup.find_all('div', class_='card'):
        permid = card.get('data-permanent-id', '')
        if not permid.startswith('document/'):
            continue

        # Skip front matter and the volume-as-a-whole entry. Individual papers
        # have a DOI ending in ".N" where N is the paper number; the volume
        # itself ends with just ".YYYY" and front matter ends with ".0".
        if not re.match(r'^document/10\.4230/LIPIcs\.TQC\.\d{4}\.\d+$', permid):
            continue
        if permid.endswith('.0'):
            continue
        category_div = card.find('div', class_='category')
        category = category_div.get_text(' ', strip=True) if category_div else ''
        if 'front matter' in category.lower():
            continue

        title_h5 = card.find('h5', class_='card-title')
        if not title_h5:
            continue
        title = ' '.join(title_h5.get_text(' ', strip=True).split())
        if not title:
            continue

        author_spans = card.find_all('span', {'data-key': 'dagstuhl.contributor.author'})
        raw_authors = [s.get('data-value', '').strip() for s in author_spans if s.get('data-value')]
        authors = lipics_authors_to_full_names(raw_authors)
        if not authors:
            # Should not happen but skip just in case.
            continue

        # PDF URL — useful as a presentation/proceedings reference.
        pdf_a = card.find('a', href=lambda h: h and h.endswith('.pdf'))
        pdf_url = pdf_a['href'] if pdf_a else ''

        # DOI — store in notes for traceability.
        doi_div = card.find('div', class_='doi')
        doi_text = doi_div.get_text(' ', strip=True) if doi_div else ''
        doi = doi_text.replace('DOI:', '').strip()

        # Abstract is in a sibling `<div class="collapse">` keyed by id; locate
        # via the abstract toggle inside <aside>. We pull it for arXiv-id
        # extraction even when we don't write it to CSV.
        abstract_text = _extract_collapsible_text(card, 'abstract')

        bibtex_text = _extract_collapsible_text(card, 'bibtex')
        # Some LIPIcs entries embed an arXiv URL in the abstract or BibTex note.
        arxiv_search_blob = ' '.join((title, abstract_text or '', bibtex_text or ''))
        arxiv_ids = extract_arxiv_ids(arxiv_search_blob)

        notes_parts = []
        if doi:
            notes_parts.append(f'DOI: {doi}')
        notes_parts.append('LIPIcs proceedings (Dagstuhl)')
        notes = '; '.join(notes_parts)

        talks.append({
            'venue': 'TQC',
            'year': year,
            'paper_type': 'regular',
            'is_proceedings_track': 'TRUE',
            'title': title,
            # Presenter unknown for proceedings papers; leave blank so the
            # importer can fill it from a video/calendar source later.
            'speakers': '; '.join(authors),
            'authors': '; '.join(authors),
            'affiliations': '',
            'arxiv_ids': ', '.join(arxiv_ids),
            'session_name': 'Proceedings track (LIPIcs)',
            'scheduled_date': '',
            'scheduled_time': '',
            'duration_minutes': '',
            'presentation_url': pdf_url,
            'video_url': '',
            'youtube_id': '',
            'award': '',
            'notes': notes,
        })

    return talks


def _extract_collapsible_text(card, kind: str) -> Optional[str]:
    """Locate a sibling collapse div for the given card and return its text.

    LIPIcs renders the abstract and BibTex inside `<div class="collapse" id="abstract-NNNNN">`
    blocks that live as siblings of the card's parent column. We find them by
    matching the toggle-anchor's data-bs-target.
    """
    aside = card.find('aside')
    if not aside:
        return None
    target_anchor = None
    for a in aside.find_all('a'):
        title = a.get('title', '').lower()
        if kind == 'abstract' and 'abstract' in title:
            target_anchor = a
            break
        if kind == 'bibtex' and 'bibtex' in title:
            target_anchor = a
            break
    if not target_anchor:
        return None
    target_id = target_anchor.get('data-bs-target', '').lstrip('#')
    if not target_id:
        return None
    # The collapse div is somewhere in the document.
    parent = card
    while parent is not None and parent.name != 'html':
        sibling = parent.find_next('div', id=target_id)
        if sibling:
            return ' '.join(sibling.get_text(' ', strip=True).split())
        parent = parent.parent
    return None


# ============================================================
# CSV / CLI
# ============================================================

def save_csv(year: int, talks: List[Dict[str, Any]], output_dir: Path,
             force: bool = False) -> Optional[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / f'tqc_{year}_proceedings_talks.csv'

    if output_file.exists() and not force:
        print(f'  Skipping {output_file} (already exists, use --force to overwrite)')
        return None

    with open(output_file, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS, quoting=csv.QUOTE_MINIMAL)
        writer.writeheader()
        for t in talks:
            writer.writerow(t)
    return output_file


def fetch_year(year: int, output_dir: Path,
               use_cache: bool = True, force: bool = False) -> bool:
    if year not in VOLUME_BY_YEAR:
        print(f'  No LIPIcs volume known for TQC {year}')
        return False

    print(f'Fetching TQC {year} proceedings (LIPIcs vol {VOLUME_BY_YEAR[year]})...')
    try:
        html = fetch_volume_html(year, use_cache=use_cache)
        talks = parse_volume(html, year)
    except Exception as exc:
        import traceback
        print(f'  ERROR fetching TQC {year}: {exc}')
        traceback.print_exc()
        return False

    if not talks:
        print(f'  WARNING: No proceedings papers parsed for TQC {year}')
        return False

    output_file = save_csv(year, talks, output_dir, force)
    if output_file:
        print(f'  Saved {len(talks)} proceedings papers to {output_file}')
    return True


def main():
    ap = argparse.ArgumentParser(description='Fetch TQC LIPIcs proceedings (2013-2025).')
    ap.add_argument('--year', type=int, help='Specific year to fetch')
    ap.add_argument('--all', action='store_true', help='Fetch all known years')
    ap.add_argument('--no-cache', action='store_true', help='Skip the on-disk HTML cache')
    ap.add_argument('--output-dir', type=str, default=str(OUTPUT_DIR),
                    help=f'Output directory (default: {OUTPUT_DIR})')
    ap.add_argument('--force', action='store_true', help='Overwrite existing CSV files')
    args = ap.parse_args()

    output_dir = Path(args.output_dir)
    use_cache = not args.no_cache

    if args.year:
        fetch_year(args.year, output_dir, use_cache=use_cache, force=args.force)
    elif args.all:
        success = 0
        for year in sorted(VOLUME_BY_YEAR):
            if fetch_year(year, output_dir, use_cache=use_cache, force=args.force):
                success += 1
            # Be polite: small delay between live fetches.
            if not use_cache:
                time.sleep(1)
        print(f'\nDone: {success}/{len(VOLUME_BY_YEAR)} years fetched successfully.')
    else:
        ap.print_help()
        print(f'\nAvailable years: {sorted(VOLUME_BY_YEAR)}')


if __name__ == '__main__':
    main()
