#!/usr/bin/env python3
"""Scrape TQC committee data for all historical years from local archive.

Usage:
    python scrape_tqc_historical.py [--year YEAR] [--all] [--output-dir DIR]

Outputs CSV files to scraped_data/ (or specified output dir).

Local archive root: ~/Web/tqc.iaqi.org/
"""

import argparse
import csv
import re
from pathlib import Path
from typing import List, Dict, Optional, Tuple

from bs4 import BeautifulSoup, Tag

ARCHIVE_BASE = Path.home() / 'Web' / 'tqc.iaqi.org'
OUTPUT_DIR = Path(__file__).parent / 'scraped_data'


# ============================================================
# Shared helpers
# ============================================================

def make_member(committee_type: str, position: str, full_name: str,
                affiliation: Optional[str] = None,
                role_title: Optional[str] = None) -> Dict:
    return {
        'committee_type': committee_type,
        'position': position,
        'full_name': full_name.strip(),
        'affiliation': affiliation.strip() if affiliation else '',
        'role_title': role_title or '',
    }


def read_html(path: Path, encoding: str = 'utf-8') -> BeautifulSoup:
    with open(path, encoding=encoding, errors='replace') as f:
        return BeautifulSoup(f.read(), 'html.parser')


def normalize_name(name: str) -> str:
    return ' '.join(name.split())


# Map heading text to (committee_type, default_position).
# Order matters: "local organising" must be matched before "organising committee".
HEADING_PATTERNS = [
    (re.compile(r'\blocal\s+organi[sz]ing\b', re.I), 'local_organizing'),
    (re.compile(r'\blocal\s+organi[sz]ation\b', re.I), 'local_organizing'),
    (re.compile(r'\blocal\s+organi[sz]ers?\b', re.I), 'local_organizing'),
    (re.compile(r'\blocal\s+arrangements?\b', re.I), 'local_organizing'),
    (re.compile(r'\blocal\s+committee\b', re.I), 'local_organizing'),
    (re.compile(r'\bsteering\s+committee\b', re.I), 'steering'),
    (re.compile(r'\badvisory\s+(?:board|committee)\b', re.I), 'steering'),
    (re.compile(r'\b(?:program|programme)\s+committee\b', re.I), 'program'),
    (re.compile(r'\bnational\s+organi[sz]ers?\b', re.I), 'organizing'),
    (re.compile(r'\binternational\s+organi[sz]ers?\b', re.I), 'organizing'),
    (re.compile(r'\borgani[sz]ing\s+committee\b', re.I), 'organizing'),
    (re.compile(r'\borgani[sz]ation\b', re.I), 'organizing'),
]


def classify_heading(text: str) -> Optional[str]:
    """Map a heading like 'Programme Committee of TQC 2025' to a committee_type."""
    for pat, ctype in HEADING_PATTERNS:
        if pat.search(text):
            return ctype
    return None


# Specific role phrases (longest first so 'program chair' beats bare 'chair').
ROLE_PHRASE = (
    r'(?:co[-\s]?chair'
    r'|pc[-\s]?chair'
    r'|program(?:me)?\s*chair'
    r'|steering\s*chair'
    r'|general\s*chair'
    r'|local\s*chair'
    r'|local\s*organi[sz]ing\s*chair'
    r'|publicity\s*chair'
    r'|chair)'
)
ROLE_RE = re.compile(r'\b' + ROLE_PHRASE + r'\b', re.I)

# Bracketed annotations that are entirely chair/role markers, e.g. "[chair]",
# "(co-chair)", "[chair, contact person]", "(host)", "[NISQ]".
BRACKET_ANNOTATION_RE = re.compile(
    r'\[\s*(?:' + ROLE_PHRASE + r'|host|contact\s+person|nisq|lc\s+contact:[^\]]*)\b[^\]]*\]'
    r'|\(\s*(?:' + ROLE_PHRASE + r'|host)\s*\)',
    re.I,
)

# Trailing dash-separated role: " - chair", " – co-chair".
TRAIL_DASH_ROLE_RE = re.compile(
    r'\s*[-–—]\s*' + ROLE_PHRASE + r'\b.*$',
    re.I,
)


def detect_position(text: str) -> Tuple[str, Optional[str]]:
    """Detect (position, role_title) from raw text.

    position is 'chair' / 'co_chair' / 'member'. role_title is a human-readable
    title like 'Program Chair' (only set when a chair role is detected).
    """
    if re.search(r'\bco[-\s]?chair\b', text, re.I):
        return 'co_chair', 'Co-Chair'
    if re.search(r'\bprogram(?:me)?\s*chair\b|\bpc[-\s]?chair\b', text, re.I):
        return 'chair', 'Program Chair'
    if re.search(r'\bsteering\s*chair\b', text, re.I):
        return 'chair', 'Steering Chair'
    if re.search(r'\blocal\s*(?:organi[sz]ing\s*)?chair\b', text, re.I):
        return 'chair', 'Local Chair'
    if re.search(r'\bgeneral\s*chair\b', text, re.I):
        return 'chair', 'General Chair'
    if re.search(r'\bpublicity\s*chair\b', text, re.I):
        return 'chair', 'Publicity Chair'
    if re.search(r'\bchair\b', text, re.I):
        return 'chair', 'Chair'
    return 'member', None


def _strip_role_phrases(text: str) -> str:
    """Remove role phrases from text wherever they appear, plus surrounding
    punctuation/connectors that get orphaned by the removal."""
    out = text

    # 1. Whole-bracket annotations: [chair], (co-chair), [chair, contact], (host).
    out = BRACKET_ANNOTATION_RE.sub('', out)

    # 2. Hyphenated co-chair / pc-chair must be stripped as a unit, otherwise
    # subsequent regexes can swallow only "chair" and leave dangling "co" or "pc".
    out = re.sub(r'\bco[-\s]?chair\b', '', out, flags=re.I)
    out = re.sub(r'\bpc[-\s]?chair\b', '', out, flags=re.I)

    # 3. " - chair" / " – chair" inside parens or trailing — REQUIRE leading
    # whitespace so we never eat the dash inside "co-chair".
    out = re.sub(
        r'\s+[-–—]\s*' + ROLE_PHRASE + r'\b[^,;()\[\]]*',
        '',
        out,
        flags=re.I,
    )

    # 4. ", chair" / "; chair" / ": chair" with comma-style connector.
    out = re.sub(
        r'[,;:]\s*' + ROLE_PHRASE + r'\b',
        '',
        out,
        flags=re.I,
    )

    # 5. Bare role phrase ("Program Chair", "Chair") anywhere left. Removing
    # the surrounding whitespace too so we don't leave double spaces.
    out = re.sub(
        r'\s*\b' + ROLE_PHRASE + r'\b\s*',
        ' ',
        out,
        flags=re.I,
    )

    # 6. Mop up dangling leading punctuation inside parens left by step 4-5
    # (e.g. "(; UC Santa Barbara)").
    out = re.sub(r'\(\s*[,;:\-–—]+\s*', '(', out)
    out = re.sub(r'\s*[,;:\-–—]+\s*\)', ')', out)
    # And stray spaces just inside parens ("( Foxconn)" → "(Foxconn)").
    out = re.sub(r'\(\s+', '(', out)
    out = re.sub(r'\s+\)', ')', out)

    # 7. Empty parens / brackets after stripping.
    out = re.sub(r'\(\s*\)', '', out)
    out = re.sub(r'\[\s*\]', '', out)

    # 8. Collapse whitespace & trim leading/trailing punctuation.
    out = re.sub(r'\s+', ' ', out).strip()
    out = re.sub(r'[\s,;:\-–—]+$', '', out).strip()
    out = re.sub(r'^[\s,;:\-–—]+', '', out).strip()
    return out


def split_name_affiliation(text: str) -> Tuple[str, Optional[str]]:
    """Split into (name, affiliation) using whichever delimiter appears first."""
    text = text.strip().strip(',;').strip()
    if not text:
        return text, None

    # If the entire text is just "Name (Affiliation)" with one paren group,
    # use that. Detect by checking the first separator.
    first_paren = text.find('(')
    first_comma = text.find(',')

    use_paren_first = (
        first_paren >= 0
        and (first_comma < 0 or first_paren < first_comma)
    )

    if use_paren_first:
        m = re.match(r'^(.*?)\s*\(([^()]*(?:\([^()]*\)[^()]*)*)\)\s*$', text)
        if m:
            name = m.group(1).strip().strip(',;').strip()
            aff = m.group(2).strip().strip(',;').strip()
            return name, (aff or None)

    # Default: split on first comma. Multi-comma affiliations (e.g.
    # "QMATH, University of Copenhagen") stay together as the affiliation.
    if first_comma >= 0:
        parts = text.split(',', 1)
        name = parts[0].strip()
        aff = parts[1].strip().strip(',;').strip()
        return name, (aff or None)

    return text, None


def parse_member_text(text: str, committee_type: str) -> Optional[Dict]:
    """Parse a single committee-member text fragment into a member dict."""
    raw = ' '.join(text.split())
    if not raw or len(raw) < 2:
        return None

    position, role_title = detect_position(raw)
    cleaned = _strip_role_phrases(raw)

    name, affiliation = split_name_affiliation(cleaned)
    name = normalize_name(name)
    # Strip residual decoration in the name (semicolons, dashes, "the").
    name = re.sub(r'^[\s,;:\-–—]+', '', name).strip()
    name = re.sub(r'[\s,;:\-–—]+$', '', name).strip()
    if affiliation:
        affiliation = re.sub(r'^[\s,;:\-–—]+', '', affiliation).strip()
        affiliation = re.sub(r'[\s,;:\-–—]+$', '', affiliation).strip() or None

    if not name or len(name) < 2:
        return None
    if name.lower() in {'tba', 'tbd', 'tbc'}:
        return None
    # Reject obvious non-name content (e.g. "and the entire QI group at UPMC").
    if re.match(r'^(?:and\s+)?the\b', name, re.I):
        return None

    return make_member(committee_type, position, name, affiliation, role_title)


# ============================================================
# Generic WordPress / heading-based parser
# ============================================================

def _iter_heading_groups(soup: BeautifulSoup,
                         heading_tags: Tuple[str, ...] = ('h1', 'h2', 'h3', 'h4'),
                         strong_paragraph: bool = False) -> List[Tuple[str, List[Tag]]]:
    """Walk the document and yield (committee_type, [<ul>...]) groups.

    The current heading defines the committee type. Each heading collects
    every <ul> that follows it until the next heading is encountered.
    If `strong_paragraph` is True, also treat <p><strong>...</strong></p> as
    a heading-like marker (used by 2022 and parts of 2024/2025).
    """
    groups: List[Tuple[str, List[Tag]]] = []
    current_type: Optional[str] = None
    current_uls: List[Tag] = []

    main = (soup.find('article') or soup.find(class_='entry-content')
            or soup.find('main') or soup.body or soup)

    for el in main.descendants:
        if not isinstance(el, Tag):
            continue
        if el.name in heading_tags:
            text = el.get_text(' ', strip=True)
            ctype = classify_heading(text)
            if ctype is not None:
                if current_type and current_uls:
                    groups.append((current_type, current_uls))
                current_type = ctype
                current_uls = []
            else:
                # Non-committee heading — flush so we don't bleed into
                # unrelated sections.
                if current_type and current_uls:
                    groups.append((current_type, current_uls))
                current_type = None
                current_uls = []
        elif strong_paragraph and el.name == 'p':
            strong = el.find('strong')
            if strong:
                text = strong.get_text(' ', strip=True)
                ctype = classify_heading(text)
                if ctype is not None:
                    if current_type and current_uls:
                        groups.append((current_type, current_uls))
                    current_type = ctype
                    current_uls = []
        elif el.name == 'ul' and current_type:
            # Skip nested ULs we already collected via the parent.
            if any(el is u or el in u.find_all('ul') for u in current_uls):
                continue
            current_uls.append(el)

    if current_type and current_uls:
        groups.append((current_type, current_uls))
    return groups


def _members_from_ul(ul: Tag, committee_type: str) -> List[Dict]:
    members = []
    for li in ul.find_all('li', recursive=False):
        # Drop nested lists from the text extraction.
        for nested in li.find_all('ul'):
            nested.decompose()
        text = li.get_text(' ', strip=True)
        member = parse_member_text(text, committee_type)
        if member:
            members.append(member)
    return members


def parse_generic_wp(path: Path, strong_paragraph: bool = True) -> List[Dict]:
    """Parse a WordPress-style TQC committee page (2019-2025).

    Strategy: walk h2/h3/h4 headings (and optionally <p><strong>...</strong></p>
    paragraphs); each one classified by HEADING_PATTERNS owns the following <ul>s.
    """
    soup = read_html(path)
    members: List[Dict] = []
    for ctype, uls in _iter_heading_groups(soup, strong_paragraph=strong_paragraph):
        for ul in uls:
            members.extend(_members_from_ul(ul, ctype))
    return members


# ============================================================
# Year-specific parsers
# ============================================================

def parse_2014() -> List[Dict]:
    """TQC 2014 (Singapore): web.archive.org snapshot of tqc.quantumlah.org.

    Layout: <h3>Section</h3><p>Name1<br>Name2<br>...</p>. Chair markers use
    `<b>(chair)</b>` / `<b>(co-chair)</b>`.
    """
    path = (ARCHIVE_BASE / 'web.archive.org' / 'web' / '20190902000118'
            / 'http:' / 'tqc.quantumlah.org' / 'committees.php.html')
    if not path.exists():
        return []
    soup = read_html(path)
    members: List[Dict] = []

    for h3 in soup.find_all('h3'):
        ctype = classify_heading(h3.get_text(' ', strip=True))
        if not ctype:
            continue
        # Find the next <p> sibling with members.
        node = h3.find_next_sibling()
        # Skip non-content siblings.
        while node is not None and node.name not in ('p', 'h3', 'h2'):
            node = node.find_next_sibling()
        if node is None or node.name != 'p':
            continue

        # Split paragraph contents on <br>.
        html = str(node)
        parts = re.split(r'<br\s*/?>', html)
        for part in parts:
            text = BeautifulSoup(part, 'html.parser').get_text(' ', strip=True)
            text = ' '.join(text.split())
            if not text or len(text) < 4:
                continue
            # Stop processing this section once we hit the contact footer.
            if re.search(r'\bcontacts?\s+details?\b', text, re.I):
                break
            # Skip address-like or non-name lines.
            if re.search(r'\b(?:phone|fax|email|tel\.?|copyright)\b', text, re.I):
                continue
            if re.match(r'^\d', text) or re.search(r'\d{5,}', text):
                continue
            # Names should have at least one space-separated token sequence
            # starting with an uppercase letter and a comma (Name, Affiliation)
            # — otherwise skip. We're permissive here so chairs without affil
            # still parse, but reject bare "Centre for ..." header rows.
            if ',' not in text and not re.match(
                r'^[A-ZÀ-ÿ][A-Za-zÀ-ÿ\'\-]+(?:\s+[A-Za-zÀ-ÿ\'\-]+){1,4}\s*$',
                text,
            ):
                continue
            member = parse_member_text(text, ctype)
            if member:
                members.append(member)
    return members


def parse_2015() -> List[Dict]:
    """TQC 2015 (Brussels): committees.html with simple <h2>+<ul> layout."""
    path = ARCHIVE_BASE / '2015' / 'committees.html'
    soup = read_html(path)
    members: List[Dict] = []

    for h2 in soup.find_all('h2'):
        ctype = classify_heading(h2.get_text(' ', strip=True))
        if not ctype:
            continue
        ul = h2.find_next_sibling('ul')
        if ul:
            members.extend(_members_from_ul(ul, ctype))
    return members


def parse_2017() -> List[Dict]:
    """TQC 2017 (Paris): committees.html with <h2>+<ul class="committee">."""
    path = ARCHIVE_BASE / '2017' / 'committees.html'
    soup = read_html(path)
    members: List[Dict] = []

    for h2 in soup.find_all('h2'):
        text = h2.get_text(' ', strip=True)
        ctype = classify_heading(text)
        if not ctype:
            continue
        ul = h2.find_next_sibling('ul')
        if ul:
            members.extend(_members_from_ul(ul, ctype))
    return members


def parse_2019() -> List[Dict]:
    """TQC 2019 (Maryland): WordPress committees/index.html."""
    return parse_generic_wp(ARCHIVE_BASE / '2019' / 'committees' / 'index.html')


def parse_2020() -> List[Dict]:
    """TQC 2020 (Riga, virtual): WordPress people/index.html."""
    return parse_generic_wp(ARCHIVE_BASE / '2020' / 'people' / 'index.html')


def parse_2021() -> List[Dict]:
    """TQC 2021 (Riga, virtual): WordPress people/index.html.

    Section headings live inside <p><strong>...</strong></p>, not real <h2>.
    """
    return parse_generic_wp(ARCHIVE_BASE / '2021' / 'people' / 'index.html')


def parse_2022() -> List[Dict]:
    """TQC 2022 (Illinois): WordPress people/index.html. Headings inside <p><strong>...</strong></p>."""
    return parse_generic_wp(ARCHIVE_BASE / '2022' / 'people' / 'index.html')


def parse_2023() -> List[Dict]:
    """TQC 2023 (Aveiro): combined archive at ~/Web/tqc.iaqi.org/2025/tqc2023/index.html."""
    return parse_generic_wp(ARCHIVE_BASE / '2025' / 'tqc2023' / 'index.html')


def parse_2024() -> List[Dict]:
    """TQC 2024 (Okinawa): combined archive at ~/Web/tqc.iaqi.org/2025/tqc-2024/index.html."""
    return parse_generic_wp(ARCHIVE_BASE / '2025' / 'tqc-2024' / 'index.html')


def parse_2025() -> List[Dict]:
    """TQC 2025 (Bengaluru): WordPress people/index.html with sub-organiser sections."""
    return parse_generic_wp(ARCHIVE_BASE / '2025' / 'people' / 'index.html')


PARSERS = {
    2014: parse_2014,
    2015: parse_2015,
    2017: parse_2017,
    2019: parse_2019,
    2020: parse_2020,
    2021: parse_2021,
    2022: parse_2022,
    2023: parse_2023,
    2024: parse_2024,
    2025: parse_2025,
}


# ============================================================
# CSV output
# ============================================================

def save_csv(year: int, members: List[Dict], output_dir: Path, force: bool = False) -> Optional[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / f'tqc_{year}_committees.csv'
    if output_file.exists() and not force:
        print(f'  Skipping {output_file} (already exists, use --force to overwrite)')
        return None

    fieldnames = ['venue', 'year', 'committee_type', 'position', 'full_name', 'affiliation', 'role_title']
    with open(output_file, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for m in members:
            row = {'venue': 'TQC', 'year': year}
            row.update(m)
            writer.writerow(row)
    return output_file


def scrape_year(year: int, output_dir: Path, force: bool = False) -> bool:
    if year not in PARSERS:
        print(f'  No parser for TQC {year}')
        return False

    print(f'Scraping TQC {year}...')
    try:
        members = PARSERS[year]()
    except Exception as exc:
        import traceback
        print(f'  ERROR scraping TQC {year}: {exc}')
        traceback.print_exc()
        return False

    if not members:
        print(f'  WARNING: No members found for TQC {year}')
        return False

    seen = set()
    unique = []
    for m in members:
        key = (m['full_name'].lower(), m['committee_type'], m['position'])
        if key not in seen:
            seen.add(key)
            unique.append(m)

    output_file = save_csv(year, unique, output_dir, force)
    if output_file:
        print(f'  Saved {len(unique)} members to {output_file}')
    return True


def main():
    parser = argparse.ArgumentParser(description='Scrape TQC historical committee data')
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
