#!/usr/bin/env python3
"""Scrape QIP committee data for all historical years from local archive.

Usage:
    python scrape_qip_historical.py [--year YEAR] [--all] [--output-dir DIR]

Outputs CSV files to scraped_data/ (or specified output dir).
"""

import argparse
import csv
import re
import sys
from pathlib import Path
from typing import List, Dict, Optional, Tuple

from bs4 import BeautifulSoup

ARCHIVE_BASE = Path.home() / 'Web' / 'qip.iaqi.org'
OUTPUT_DIR = Path(__file__).parent / 'scraped_data'

# Years available in archive (not yet scraped)
MISSING_YEARS = [
    1999, 2000, 2001, 2002,
    2008, 2009,
    2011, 2012, 2013, 2014, 2015, 2016, 2017, 2018,
    2021, 2023, 2024,
]


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
    """Normalize name: remove extra spaces, handle ALLCAPS family names."""
    name = ' '.join(name.split())
    # Convert "FAMILY Given" -> "Given FAMILY" then title-case
    # e.g. "AMBAINIS Andris" -> proper form
    # We'll just normalise spacing; don't reorder
    return name


def parse_name_affiliation(text: str) -> Tuple[str, Optional[str]]:
    """Parse 'Name (Affiliation)' or 'Name, Affiliation' into (name, affiliation)."""
    text = text.strip()
    # Try 'Name (Affiliation)' format first
    m = re.match(r'^(.*?)\s*\(([^)]+)\)\s*$', text)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    # Try 'Name, Affiliation' format
    if ',' in text:
        parts = text.split(',', 1)
        return parts[0].strip(), parts[1].strip()
    return text, None


def detect_position(text: str) -> str:
    """Detect chair/co-chair from text."""
    lower = text.lower()
    if 'co-chair' in lower or 'co chair' in lower:
        return 'co_chair'
    if 'chair' in lower:
        return 'chair'
    return 'member'


def split_flat_names(text: str) -> List[str]:
    """Split flat text like 'Name (Affil) Name (Affil)...' into individual entries.

    Handles both 'Name (Affil)Name' (no space) and 'Name (Affil) Name' (with space).
    """
    # Split at ')' followed by optional whitespace and then an uppercase letter
    parts = re.split(r'\)\s*(?=[A-Z\u00C0-\u024F])', text)
    result = []
    for i, part in enumerate(parts):
        part = part.strip()
        if i < len(parts) - 1:
            part = part + ')'  # restore the ) we split on
        if part:
            result.append(part)
    return result


def parse_lines_committee(lines: List[str], committee_type: str, position: str = 'member') -> List[Dict]:
    """Parse a list of 'Name (Affiliation)' or 'Name, Affiliation' lines."""
    members = []
    for line in lines:
        line = line.strip()
        if not line or len(line) < 3:
            continue

        # Detect chair/co-chair indicators
        pos = detect_position(line)
        role_title = None

        # Remove chair/co-chair markers from the text for name parsing
        clean = re.sub(r'\s*\([Cc]hair\)\s*$', '', line)
        clean = re.sub(r'\s*\([Cc]o-[Cc]hair\)\s*$', '', clean)
        clean = re.sub(r'\s*\([Cc]o\s+[Cc]hair\)\s*$', '', clean)

        # Handle "Name (Role, Affiliation)" or "Name (Affiliation, Role)"
        # e.g. "Richard Cleve (Programme Chair, U Waterloo)"
        # or "Andris Ambainis (University of Latvia, Chair)"
        m = re.match(r'^(.*?)\s*\(([^)]+)\)\s*$', clean)
        if m:
            name_part = m.group(1).strip()
            paren_content = m.group(2).strip()

            # Check if the paren content contains a role (check Programme Chair first)
            if re.search(r'[Pp]rogramm?e\s+[Cc]hair', paren_content):
                pos = 'chair'
                role_title = 'Program Chair'
                affil = re.sub(r'[Pp]rogramm?e\s+[Cc]hair,?\s*', '', paren_content).strip()
                members.append(make_member(committee_type, pos, name_part, affil or None, role_title))
            elif re.search(r'[Cc]hair', paren_content):
                if pos == 'member':
                    pos = detect_position(paren_content)
                # Remove the chair part from affiliation
                affil = re.sub(r',?\s*[Cc]o-[Cc]hair', '', paren_content)
                affil = re.sub(r',?\s*[Cc]hair', '', affil).strip().strip(',').strip()
                if affil:
                    members.append(make_member(committee_type, pos, name_part, affil, role_title))
                else:
                    members.append(make_member(committee_type, pos, name_part, None, role_title))
            else:
                members.append(make_member(committee_type, pos, name_part, paren_content, role_title))
        else:
            # No parenthetical - might be "Name, Affiliation" or just "Name"
            if ',' in clean:
                parts = clean.split(',', 1)
                name_part = parts[0].strip()
                affil = parts[1].strip()
                # Check affiliation for chair info
                if re.search(r'[Cc]hair', affil):
                    if pos == 'member':
                        pos = detect_position(affil)
                    affil = re.sub(r',?\s*[Pp]rogram\s+[Cc]hair', '', affil).strip().strip(',').strip()
                members.append(make_member(committee_type, pos, name_part, affil or None, role_title))
            else:
                members.append(make_member(committee_type, 'member' if pos == 'member' else pos, clean, None, role_title))

    return [m for m in members if m['full_name']]


# ============================================================
# Year-specific parsers
# ============================================================

def join_wrapped_lines(raw_lines: List[str]) -> List[str]:
    """Join lines that are word-wrapped continuations (indented + lowercase start)."""
    result = []
    for raw in raw_lines:
        stripped = raw.strip()
        if raw and raw[0] == ' ' and stripped and stripped[0].islower() and result:
            # Continuation line (indented, starts lowercase) - append to previous
            result[-1] = result[-1] + ' ' + stripped
        else:
            result.append(stripped)
    return [l for l in result if l]


def parse_1999() -> List[Dict]:
    """QIP 1999 (AQIP'99) - theme.htm"""
    with open(ARCHIVE_BASE / '1999' / 'theme.htm', encoding='utf-8', errors='replace') as f:
        raw = f.read()
    soup = BeautifulSoup(raw, 'html.parser')
    text = soup.get_text()

    members = []
    raw_lines = text.split('\n')

    # Parse PC section from text (names in two-column table, one per line after stripping)
    pc_start = next((i for i, l in enumerate(raw_lines) if l.strip() == 'Program Committee'), None)
    oc_start = next((i for i, l in enumerate(raw_lines) if l.strip() == 'Organizing Committee'), None)

    if pc_start is not None and oc_start is not None:
        pc_lines = [l.strip() for l in raw_lines[pc_start + 1:oc_start] if l.strip()]
        members.extend(parse_lines_committee(pc_lines, 'program'))

    # For OC, parse HTML directly to handle <br>-separated entries
    oc_section = soup.find(string=re.compile(r'Organizing Committee'))
    if oc_section:
        parent = oc_section.find_parent()
        # Find the <p> tag after the OC header
        next_p = parent.find_next_sibling('p')
        if next_p:
            # Get text split by <br> tags
            html_str = str(next_p)
            parts = re.split(r'<br\s*/?>', html_str)
            for part in parts:
                clean = BeautifulSoup(part, 'html.parser').get_text(strip=True)
                clean = re.sub(r'\s+', ' ', clean).strip()
                if clean and 'contact' not in clean.lower() and '@' not in clean:
                    members.extend(parse_lines_committee([clean], 'local_organizing'))

    return members


def parse_2000() -> List[Dict]:
    """QIP 2000 - index.html: two organizers listed."""
    soup = read_html(ARCHIVE_BASE / '2000' / 'index.html')
    text = soup.get_text()

    members = []
    lines = [l.strip() for l in text.split('\n')]

    org_start = next((i for i, l in enumerate(lines) if 'Organizers' in l), None)
    if org_start is not None:
        for line in lines[org_start + 1:org_start + 10]:
            line = line.strip()
            # Stop at blank lines or long descriptive text
            if not line or len(line) > 60:
                continue
            # Only lines that look like "Name (Affil)"
            if re.match(r'^[A-Z].*\(.*\)', line):
                members.extend(parse_lines_committee([line], 'local_organizing'))

    return members


def parse_2001() -> List[Dict]:
    """QIP 2001 - index.html: three CWI organizers."""
    # Organizers: Harry Buhrman, Hein Röhrig, Ronald de Wolf (all CWI)
    return [
        make_member('local_organizing', 'member', 'Harry Buhrman', 'CWI'),
        make_member('local_organizing', 'member', 'Hein Röhrig', 'CWI'),
        make_member('local_organizing', 'member', 'Ronald de Wolf', 'CWI'),
    ]


def parse_2002() -> List[Dict]:
    """QIP 2002 - index.html: two IBM organizers."""
    return [
        make_member('local_organizing', 'chair', 'Charles Bennett', 'IBM Watson Research Center'),
        make_member('local_organizing', 'chair', 'David DiVincenzo', 'IBM Watson Research Center'),
    ]


def parse_2008() -> List[Dict]:
    """QIP 2008 - index.html (latin-1 encoding, <li>-based committee lists)"""
    with open(ARCHIVE_BASE / '2008' / 'index.html', encoding='latin-1') as f:
        content = f.read()
    soup = BeautifulSoup(content, 'html.parser')

    members = []
    section_map = {
        'Program committee': 'program',
        'Local organizers': 'local_organizing',
        'Steering Committee': 'steering',
    }

    for bold_tag in soup.find_all('b'):
        header_text = bold_tag.get_text(strip=True)
        if header_text not in section_map:
            continue
        ctype = section_map[header_text]

        # Find the <ul> that follows
        ul = bold_tag.find_next('ul')
        if not ul:
            continue

        for li in ul.find_all('li'):
            # Get full text of li, joining wrapped lines
            text = ' '.join(li.get_text().split())
            if text:
                members.extend(parse_lines_committee([text], ctype))

    return members


def parse_2009() -> List[Dict]:
    """QIP 2009 - organizing-committees.html"""
    soup = read_html(ARCHIVE_BASE / '2009' / 'organizing-committees.html')
    text = soup.get_text()
    lines = [l.strip() for l in text.split('\n')]

    members = []
    section_map = {
        'Local organizing committee': 'local_organizing',
        'Steering committee': 'steering',
        'Program committee': 'program',
    }

    current_type = None
    current_lines = []

    for line in lines:
        # Check for section headers (case-insensitive match)
        matched = False
        for header, ctype in section_map.items():
            if line.strip() == header:
                if current_type and current_lines:
                    members.extend(parse_lines_committee(current_lines, current_type))
                current_type = ctype
                current_lines = []
                matched = True
                break

        if not matched and current_type and line:
            current_lines.append(line)

    if current_type and current_lines:
        members.extend(parse_lines_committee(current_lines, current_type))

    return members


def parse_allcaps_name(name: str) -> str:
    """Convert 'AMBAINIS Andris' -> 'Andris Ambainis' or normalize."""
    # Pattern: "ALLCAPS given" or "ALLCAPS Chi-Chih given"
    # For now just normalize whitespace
    return ' '.join(name.split())


def parse_2011() -> List[Dict]:
    """QIP 2011 - committees/index.html
    Format: "FAMILY_NAME Given (Affiliation) (chair)"
    """
    soup = read_html(ARCHIVE_BASE / '2011' / 'committees' / 'index.html')
    text = soup.get_text()
    lines = [l.strip() for l in text.split('\n')]

    members = []
    section_map = {
        'Programme Committee': 'program',
        'Steering Committee': 'steering',
        'Local Organisers': 'local_organizing',
    }

    current_type = None
    current_lines = []

    for line in lines:
        matched = False
        for header, ctype in section_map.items():
            if line == header:
                if current_type and current_lines:
                    members.extend(_parse_2011_lines(current_lines, current_type))
                current_type = ctype
                current_lines = []
                matched = True
                break
        if not matched and current_type and line and 'QIP2011' not in line and 'Copyright' not in line:
            current_lines.append(line)

    if current_type and current_lines:
        members.extend(_parse_2011_lines(current_lines, current_type))

    return members


def normalize_2011_name(raw_name: str) -> str:
    """Normalize 2011-style names where family name is in ALL CAPS.

    E.g. 'Andris AMBAINIS' -> 'Andris Ambainis'
         'Wim van DAM' -> 'Wim van Dam'
         'KWEK Leong Chuan' -> 'Kwek Leong Chuan'
    """
    parts = raw_name.split()
    normalized = []
    for part in parts:
        # All-caps part with >1 char that isn't a particle -> title-case
        if part.isupper() and len(part) > 1 and part not in ('CQT', 'NUS', 'NII', 'MIT', 'IBM', 'MPQ'):
            normalized.append(part.capitalize())
        else:
            normalized.append(part)
    return ' '.join(normalized)


def _parse_2011_lines(lines: List[str], committee_type: str) -> List[Dict]:
    """Parse lines like 'Given FAMILY (Affil) (chair)' or 'FAMILY Given (Affil) (chair)'."""
    members = []
    for line in lines:
        line = line.strip()
        if not line or len(line) < 3:
            continue

        pos = 'member'
        role_title = None

        # Remove (chair) marker
        if re.search(r'\(chair\)', line, re.IGNORECASE):
            pos = 'chair'
            line = re.sub(r'\s*\(chair\)\s*$', '', line, flags=re.IGNORECASE).strip()

        # Now parse "Name (Affiliation)"
        m = re.match(r'^(.*?)\s*\(([^)]+)\)\s*$', line)
        if m:
            raw_name = m.group(1).strip()
            affil = m.group(2).strip()
            name = normalize_2011_name(raw_name)
            members.append(make_member(committee_type, pos, name, affil, role_title))
        elif line:
            members.append(make_member(committee_type, pos, normalize_2011_name(line), None, role_title))

    return [m for m in members if m['full_name']]


def parse_2012() -> List[Dict]:
    """QIP 2012 - committee_e.php.html"""
    soup = read_html(ARCHIVE_BASE / '2012' / 'committee_e.php.html')
    text = soup.get_text()
    lines = [l.strip() for l in text.split('\n')]

    members = []
    section_map = {
        'Programme Committee': 'program',
        'Steering Committee': 'steering',
        'Local Organizers': 'local_organizing',
    }

    current_type = None
    current_lines = []

    for line in lines:
        matched = False
        for header, ctype in section_map.items():
            if line == header:
                if current_type and current_lines:
                    members.extend(parse_lines_committee(current_lines, current_type))
                current_type = ctype
                current_lines = []
                matched = True
                break
        if not matched and current_type and line:
            # Stop at QIP2012 footer
            if line in ('QIP2012',):
                break
            current_lines.append(line)

    if current_type and current_lines:
        members.extend(parse_lines_committee(current_lines, current_type))

    return members


def parse_2013() -> List[Dict]:
    """QIP 2013 - index.html@p=8.html"""
    soup = read_html(ARCHIVE_BASE / '2013' / 'index.html@p=8.html')
    text = soup.get_text()
    lines = [l.strip() for l in text.split('\n')]

    members = []
    section_map = {
        'Programme Committee': 'program',
        'Steering Committee': 'steering',
        'General Chair': 'local_organizing',
        'Local Organizing Committee': 'local_organizing',
    }

    current_type = None
    current_lines = []

    for line in lines:
        matched = False
        for header, ctype in section_map.items():
            if line == header:
                if current_type and current_lines:
                    members.extend(parse_lines_committee(current_lines, current_type))
                current_type = ctype
                current_lines = []
                matched = True
                break
        if not matched and current_type and line:
            if line in ('Pdf files of', 'Supported by', 'Program Booklet: Download Here', 'Poster'):
                break
            current_lines.append(line)

    if current_type and current_lines:
        members.extend(parse_lines_committee(current_lines, current_type))

    # Fix duplicates: General Chair "Andrew Yao" also in Steering Committee
    return members


def parse_2014() -> List[Dict]:
    """QIP 2014 - cgi-bin/committees.pl.html
    Format: "- Name (Affiliation, Country)" or "- Name (Affiliation) - Program Chair"
    """
    soup = read_html(ARCHIVE_BASE / '2014' / 'cgi-bin' / 'committees.pl.html')
    text = soup.get_text()
    lines = [l.strip() for l in text.split('\n')]

    members = []
    section_map = {
        'Programme Committee': 'program',
        'Steering Committee': 'steering',
        'General Chairs': 'local_organizing',
        'Local Organizing Committee': 'local_organizing',
    }

    current_type = None
    current_lines = []

    for line in lines:
        matched = False
        for header, ctype in section_map.items():
            if line == header:
                if current_type and current_lines:
                    members.extend(_parse_2014_lines(current_lines, current_type))
                current_type = ctype
                current_lines = []
                matched = True
                break
        if not matched and current_type and line:
            if 'Supported by' in line or 'Conference Data' in line or 'List of participants' in line:
                break
            current_lines.append(line)

    if current_type and current_lines:
        members.extend(_parse_2014_lines(current_lines, current_type))

    return members


def _parse_2014_lines(lines: List[str], committee_type: str) -> List[Dict]:
    """Parse lines like '- Name  (Affiliation, Country)' or '- Name (Affil) - Program Chair'"""
    members = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        # Remove leading dash
        line = re.sub(r'^-\s*', '', line)

        pos = 'member'
        role_title = None

        # Check for "- Program Chair" suffix
        if re.search(r'-\s*[Pp]rogram\s+[Cc]hair', line):
            pos = 'chair'
            role_title = 'Program Chair'
            line = re.sub(r'\s*-\s*[Pp]rogram\s+[Cc]hair', '', line).strip()

        # Parse "Name  (Affiliation, Country)"
        m = re.match(r'^(.*?)\s*\(([^)]+)\)\s*$', line)
        if m:
            name = m.group(1).strip()
            # Affiliation may include ", Country" - keep it all
            affil = m.group(2).strip()
            members.append(make_member(committee_type, pos, name, affil, role_title))
        elif line:
            members.append(make_member(committee_type, pos, line, None, role_title))

    return [m for m in members if m['full_name']]


def parse_2015() -> List[Dict]:
    """QIP 2015 - Committees.php.html"""
    soup = read_html(ARCHIVE_BASE / '2015' / 'Committees.php.html')
    text = soup.get_text()
    lines = [l.strip() for l in text.split('\n') if l.strip()]

    members = []
    section_map = {
        'Programme Committee': 'program',
        'Steering Committee': 'steering',
        'General Conference Chair/Co-Chairs': 'local_organizing',
        'Local Organisers': 'local_organizing',
    }

    current_type = None
    current_lines = []
    in_content = False  # Only process after the "Committees" heading

    for line in lines:
        if not in_content:
            if line == 'Committees':
                in_content = True
            continue

        matched = False
        for header, ctype in section_map.items():
            if line == header:
                if current_type and current_lines:
                    members.extend(parse_lines_committee(current_lines, current_type))
                current_type = ctype
                current_lines = []
                matched = True
                break

        if not matched and current_type and line:
            # Stop at footer content
            if line.startswith('© ') or line == 'Pdf files of' or 'Supported by' in line:
                break
            current_lines.append(line)

    if current_type and current_lines:
        members.extend(parse_lines_committee(current_lines, current_type))

    return members


def parse_2016() -> List[Dict]:
    """QIP 2016 - committees.html"""
    soup = read_html(ARCHIVE_BASE / '2016' / 'committees.html')
    text = soup.get_text()
    lines = [l.strip() for l in text.split('\n')]

    members = []
    section_map = {
        'Programme Committee': 'program',
        'Steering Committee': 'steering',
        'Organizing Committee': 'local_organizing',
        'Organizing Team': 'local_organizing',
    }

    nav_items = {
        'HOME', 'COMMITTEES', 'CALL FOR SUBMISSIONS', 'REGISTRATION',
        'INVITED SPEAKERS', 'ACCEPTED TALKS', 'ACCEPTED POSTERS',
        'TUTORIAL LECTURERS', 'TUTORIAL PROGRAM', 'SCIENTIFIC PROGRAM',
        'RUMP SESSION', 'PHOTO GALLERY', 'PARTICIPANTS', 'QIP BLOGS',
        'CONFERENCE VENUES', 'ACCOMMODATION', 'TRAVEL AND VISA',
        'LOCAL INFORMATION', 'DEPARTURE INFORMATION',
        'LIST OF QIP CONFERENCES', 'QIP CHARTER', 'CONTACT US',
    }

    current_type = None
    current_lines = []

    for line in lines:
        if line in nav_items:
            continue
        matched = False
        for header, ctype in section_map.items():
            if line == header:
                if current_type and current_lines:
                    members.extend(parse_lines_committee(current_lines, current_type))
                current_type = ctype
                current_lines = []
                matched = True
                break
        if not matched and current_type and line:
            # Skip EasyChair (conference management system) and similar non-person entries
            if 'EasyChair' in line or 'LIQUi' in line:
                continue
            current_lines.append(line)

    if current_type and current_lines:
        members.extend(parse_lines_committee(current_lines, current_type))

    return members


def parse_2017() -> List[Dict]:
    """QIP 2017 - index.html (WordPress/Microsoft Research site)"""
    soup = read_html(ARCHIVE_BASE / '2017' / 'index.html')
    text = soup.get_text()
    lines = [l.strip() for l in text.split('\n')]

    members = []
    section_map = {
        'Program Committee': 'program',
        'Steering Committee': 'steering',
        'Organizing Committee': 'local_organizing',
    }

    current_type = None
    current_lines = []

    # Find the Committees section first
    committees_idx = next((i for i, l in enumerate(lines) if l == 'Committees'), None)
    if committees_idx is None:
        return members

    for line in lines[committees_idx:]:
        matched = False
        for header, ctype in section_map.items():
            if line == header:
                if current_type and current_lines:
                    members.extend(parse_lines_committee(current_lines, current_type))
                current_type = ctype
                current_lines = []
                matched = True
                break
        if not matched and current_type and line:
            # Stop at next major section (Schedule, Videos, etc.)
            if line in ('Schedule & Videos', 'Accepted posters', 'Sponsors'):
                break
            current_lines.append(line)

    if current_type and current_lines:
        members.extend(parse_lines_committee(current_lines, current_type))

    return members


def parse_2018() -> List[Dict]:
    """QIP 2018 - aboutqip/index.html (all committees in flat text)"""
    soup = read_html(ARCHIVE_BASE / '2018' / 'qutech.nl' / 'qip2018' / 'aboutqip' / 'index.html')
    text = soup.get_text()

    members = []

    # Find the committees section - it starts with "Committees"
    idx = text.find('Committees\n')
    if idx < 0:
        idx = text.find('CommitteesOrganizing committee')
    if idx < 0:
        return members

    committees_text = text[idx:]

    # Extract each section
    sections = [
        ('Organizing committee', 'local_organizing'),
        ('Program committee', 'program'),
        ('Steering committee', 'steering'),
    ]

    for i, (header, ctype) in enumerate(sections):
        start = committees_text.find(header)
        if start < 0:
            continue
        start += len(header)

        # Find end: start of next section
        end = len(committees_text)
        for j in range(i + 1, len(sections)):
            next_header = sections[j][0]
            next_pos = committees_text.find(next_header, start)
            if next_pos >= 0:
                end = next_pos
                break

        section_text = committees_text[start:end].strip()

        # Parse flat text: "Name (Affiliation) Name (Affiliation)..."
        entries = split_flat_names(section_text)
        for entry in entries:
            entry = entry.strip()
            if not entry or len(entry) < 3:
                continue

            pos = detect_position(entry)
            role_title = None

            # Remove ", chair" or "(chair)" markers
            clean = re.sub(r',\s*chair$', '', entry, flags=re.IGNORECASE).strip()
            clean = re.sub(r'\s*\(chair\)\s*$', '', clean, flags=re.IGNORECASE).strip()
            clean = re.sub(r',\s*co-chair$', '', clean, flags=re.IGNORECASE).strip()

            m = re.match(r'^(.*?)\s*\(([^)]+)\)\s*$', clean)
            if m:
                name = m.group(1).strip()
                affil = m.group(2).strip()
                # Remove "chair" from affiliation if it ended up there
                affil_clean = re.sub(r',?\s*(co-)?chair\s*$', '', affil, flags=re.IGNORECASE).strip()
                if pos == 'member' and affil_clean != affil:
                    pos = 'chair' if 'co' not in affil.lower() else 'co_chair'
                members.append(make_member(ctype, pos, name, affil_clean or None, role_title))
            elif clean:
                members.append(make_member(ctype, pos, clean, None, role_title))

    return members


def parse_2021() -> List[Dict]:
    """QIP 2021 - qip2021/program/committees/index.html
    HTML structure: <b>Name</b> | Affiliation, with role notes like "(co-chair)"
    """
    soup = read_html(ARCHIVE_BASE / '2021' / 'qip2021' / 'program' / 'committees' / 'index.html')
    members = []

    section_map = {
        'Local Organizing Committee': 'local_organizing',
        'Program Committee': 'program',
        'Steering Committee': 'steering',
    }

    for h4 in soup.find_all('h4'):
        heading = h4.get_text(strip=True)
        ctype = None
        for key, val in section_map.items():
            if key in heading:
                ctype = val
                break
        if not ctype:
            continue

        # Find all <b> tags in the next sibling div
        container = h4.find_next_sibling()
        if not container:
            continue

        for b_tag in container.find_all('b'):
            name = b_tag.get_text(strip=True)
            if not name or len(name) < 2:
                continue

            # Get the affiliation from the text that follows the <b> tag
            affil = ''
            next_sib = b_tag.next_sibling
            if next_sib and hasattr(next_sib, '__str__'):
                affil_text = str(next_sib).strip()
                affil_text = re.sub(r'^[|\s]+', '', affil_text).strip()
                # Remove HTML tags if any
                affil_text = BeautifulSoup(affil_text, 'html.parser').get_text(strip=True)
                affil = affil_text

            # Detect position from name or affiliation
            pos = 'member'
            role_title = None
            combined = f'{name} {affil}'.lower()

            # Role notes appear after affiliation like "(QIP 2021 Chair)"
            m_role = re.search(r'\(([^)]*(?:chair|co-chair)[^)]*)\)', combined)
            if m_role:
                role_text = m_role.group(1)
                if 'co-chair' in role_text.lower():
                    pos = 'co_chair'
                else:
                    pos = 'chair'
                # Clean the role text from affiliation
                affil = re.sub(r'\s*\([^)]*(?:chair|co-chair)[^)]*\)', '', affil, flags=re.IGNORECASE).strip()

            members.append(make_member(ctype, pos, name, affil or None, role_title))

    return members


def parse_2023() -> List[Dict]:
    """QIP 2023 - three Indico pages"""
    base = ARCHIVE_BASE / '2023' / 'event' / '13076' / 'page'
    members = []

    # Program committee page
    pc_soup = read_html(base / '3880-program-committee.html')
    # Steering committee page
    sc_soup = read_html(base / '3885-steering-committee.html')
    # Local organizing committee page
    loc_soup = read_html(base / '3879-local-organising-committee.html')

    # --- Program Committee ---
    for div in pc_soup.find_all('div'):
        text = div.get_text(strip=True)
        if 'Gorjan Alagic' in text and len(text) < 8000:
            idx = text.find('Program committee')
            if idx >= 0:
                pc_text = text[idx + len('Program committee'):]
                # Some entries have inline role markers after the closing paren:
                # "Name (Affiliation)   co-chairNextName (NextAffil)"
                # Strategy: tag each entry with its role marker before splitting.
                # Replace ")\s*(co-chair|chair)\s*" with ")__CO_CHAIR__" or ")__CHAIR__"
                # The role marker appears AFTER the person it describes:
                # "Toby Cubitt (University College London)   co-chairAndrew Doherty"
                # means Toby Cubitt is co-chair.
                # Tag the closing paren of the person with the role:
                # "Name (Affil)   co-chair" -> "Name (Affil__CO_CHAIR)"
                pc_tagged = re.sub(
                    r'\)\s+co-chair\s*', '__CO_CHAIR__)', pc_text, flags=re.IGNORECASE
                )
                pc_tagged = re.sub(
                    r'\)\s+chair\s*', '__CHAIR__)', pc_tagged, flags=re.IGNORECASE
                )
                for entry in split_flat_names(pc_tagged):
                    entry = entry.strip()
                    if not entry or len(entry) < 3:
                        continue
                    pos = 'member'
                    # Check for role tags inside the affiliation
                    m = re.match(r'^(.*?)\s*\(([^)]+)\)\s*$', entry)
                    if m:
                        name = m.group(1).strip()
                        affil_raw = m.group(2).strip()
                        if '__CO_CHAIR__' in affil_raw:
                            pos = 'co_chair'
                            affil = affil_raw.replace('__CO_CHAIR__', '').strip()
                        elif '__CHAIR__' in affil_raw:
                            pos = 'chair'
                            affil = affil_raw.replace('__CHAIR__', '').strip()
                        else:
                            affil = affil_raw
                        members.append(make_member('program', pos, name, affil or None))
                    elif entry and re.match(r'^[A-Z]', entry):
                        members.append(make_member('program', pos, entry, None))
            break

    # --- Steering Committee ---
    sc_text = sc_soup.get_text()
    idx = sc_text.rfind('Steering committee\n')
    if idx < 0:
        idx = sc_text.rfind('Steering committee')
    if idx >= 0:
        sc_section = sc_text[idx + len('Steering committee'):].strip()
        # Take until "Powered by" or similar footer
        sc_section = re.split(r'Powered by', sc_section)[0].strip()
        entries = split_flat_names(sc_section)
        for entry in entries:
            entry = entry.strip()
            if not entry or len(entry) < 3:
                continue
            m = re.match(r'^(.*?)\s*\(([^)]+)\)\s*$', entry)
            if m:
                members.append(make_member('steering', 'member', m.group(1).strip(), m.group(2).strip()))
            elif entry:
                members.append(make_member('steering', 'member', entry, None))

    # --- Local Organizing Committee ---
    for div in loc_soup.find_all('div'):
        text = div.get_text(strip=True)
        if 'Jacob Bridgeman' in text and len(text) < 5000:
            idx = text.find('Local organising committee')
            if idx >= 0:
                loc_text = text[idx + len('Local organising committee'):]
                members.extend(_parse_2023_loc(loc_text))
            break

    return members


def _parse_2023_loc(text: str) -> List[Dict]:
    """Parse the 2023 local organizing committee flat text."""
    members = []

    # Chairs section: "Chairs:Jacob Bridgeman (co-chair)Frank Verstraete (chair)"
    chairs_match = re.search(r'Chairs:(.*?)(?:Finances|Local organizing team)', text, re.DOTALL)
    if chairs_match:
        chairs_text = chairs_match.group(1)
        entries = split_flat_names(chairs_text)
        for entry in entries:
            entry = entry.strip()
            if not entry:
                continue
            pos = detect_position(entry)
            clean = re.sub(r'\s*\((co-)?chair\)\s*$', '', entry, flags=re.IGNORECASE).strip()
            m = re.match(r'^(.*?)\s*\(([^)]+)\)\s*$', clean)
            if m:
                members.append(make_member('local_organizing', pos, m.group(1).strip(), m.group(2).strip()))
            elif clean:
                members.append(make_member('local_organizing', pos, clean, None))

    # Finances & Logistics section
    fin_match = re.search(r'Finances\s*&\s*Logistics:(.*?)(?:Local organizing team|$)', text, re.DOTALL)
    if fin_match:
        fin_text = fin_match.group(1).strip()
        for name in fin_text.split('\n'):
            name = name.strip()
            if name and len(name) > 2:
                members.append(make_member('local_organizing', 'member', name, None))

    # Local organizing team: names grouped under institution headers
    team_match = re.search(r'Local organizing team:(.*?)$', text, re.DOTALL)
    if team_match:
        team_text = team_match.group(1).strip()
        # Known institution names (not person names)
        institutions = {'Université libre de Bruxelles', 'IMEC', 'Universiteit Gent'}
        current_affil = None
        for line in team_text.split('\n'):
            line = line.strip()
            if not line:
                continue
            if line in institutions:
                current_affil = line
            elif len(line) > 2:
                members.append(make_member('local_organizing', 'member', line, current_affil))

    return members


def parse_2024() -> List[Dict]:
    """QIP 2024 - CONFEX platform (mypage.aspx pages)"""
    base = ARCHIVE_BASE / '2024' / 'site'
    members = []

    pages = [
        ('mypage.aspx?pid=254&lang=en&sid=1522.html', 'program'),
        ('mypage.aspx?pid=238&lang=en&sid=1522.html', 'steering'),
        ('mypage.aspx?pid=239&lang=en&sid=1522.html', 'local_organizing'),
    ]

    for fname, ctype in pages:
        soup = read_html(base / fname)
        text = soup.get_text()
        lines = [l.strip() for l in text.split('\n') if l.strip()]

        # Find the long data line (>200 chars with multiple names)
        data_line = None
        for line in lines:
            if len(line) > 200 and ('(' in line) and (')' in line):
                # Check it's in the right section context
                if ctype == 'local_organizing' and 'Chair' in line:
                    data_line = line
                    break
                elif ctype in ('program', 'steering') and re.search(r'[A-Z][a-z]+\s+[A-Z]', line):
                    data_line = line
                    break

        if not data_line:
            continue

        if ctype == 'local_organizing':
            members.extend(_parse_2024_oc(data_line))
        else:
            members.extend(_parse_2024_flat(data_line, ctype))

    return members


def _parse_2024_flat(text: str, committee_type: str) -> List[Dict]:
    """Parse flat text 'Name  (Affil)  Co-chairName  (Affil)  Chair...'"""
    members = []
    entries = split_flat_names(text)

    for entry in entries:
        entry = entry.strip()
        if not entry or len(entry) < 3:
            continue

        pos = 'member'
        # Check for "  Co-chair" or "  Chair" suffix (with leading spaces)
        role_match = re.search(r'\s{2,}(Co-chair|Chair)\s*$', entry, re.IGNORECASE)
        if role_match:
            role_text = role_match.group(1)
            if 'co' in role_text.lower():
                pos = 'co_chair'
            else:
                pos = 'chair'
            entry = entry[:role_match.start()].strip()

        m = re.match(r'^(.*?)\s{2,}\(([^)]+)\)\s*$', entry)
        if not m:
            m = re.match(r'^(.*?)\s*\(([^)]+)\)\s*$', entry)
        if m:
            name = m.group(1).strip()
            affil = m.group(2).strip()
            # Remove trailing Chinese characters from name (e.g., "Min-Hsiu Hsieh 謝明修")
            name_clean = re.sub(r'\s+[\u4e00-\u9fff\u3400-\u4dbf]+.*$', '', name).strip()
            members.append(make_member(committee_type, pos, name_clean, affil))
        elif entry:
            name_clean = re.sub(r'\s+[\u4e00-\u9fff\u3400-\u4dbf]+.*$', '', entry).strip()
            if name_clean:
                members.append(make_member(committee_type, pos, name_clean, None))

    return members


def _parse_2024_oc(text: str) -> List[Dict]:
    """Parse 2024 local organizing committee structured text.

    Format: "ChairsChair: Name 中文 (Affil)Co-Chair: Name 中文 (Affil)MembersName 中文 (Affil)..."
    """
    members = []

    # Split into entries by ) followed by uppercase
    entries = split_flat_names(text)

    for entry in entries:
        entry = entry.strip()
        if not entry:
            continue

        pos = 'member'

        # Clean up section markers that got concatenated with names
        # e.g. "ChairsChair: ..." or "MembersChing-Ray Chang..."
        entry = re.sub(r'^Chairs', '', entry).strip()
        entry = re.sub(r'^Members', '', entry).strip()

        if entry.startswith('Chair:'):
            pos = 'chair'
            entry = entry[6:].strip()
        elif re.match(r'^Co-?Chair:', entry, re.IGNORECASE):
            pos = 'co_chair'
            entry = re.sub(r'^Co-?Chair:\s*', '', entry, flags=re.IGNORECASE)

        m = re.match(r'^(.*?)\s*\(([^)]+)\)\s*$', entry)
        if m:
            name = m.group(1).strip()
            affil = m.group(2).strip()
            # Remove Chinese characters from name
            name = re.sub(r'\s+[\u4e00-\u9fff\u3400-\u4dbf]+.*$', '', name).strip()
            if name and len(name) > 2:
                members.append(make_member('local_organizing', pos, name, affil))
        elif entry:
            name = re.sub(r'\s+[\u4e00-\u9fff\u3400-\u4dbf]+.*$', '', entry).strip()
            if name and len(name) > 2:
                members.append(make_member('local_organizing', pos, name, None))

    return members


# ============================================================
# Dispatch table
# ============================================================

PARSERS = {
    1999: parse_1999,
    2000: parse_2000,
    2001: parse_2001,
    2002: parse_2002,
    2008: parse_2008,
    2009: parse_2009,
    2011: parse_2011,
    2012: parse_2012,
    2013: parse_2013,
    2014: parse_2014,
    2015: parse_2015,
    2016: parse_2016,
    2017: parse_2017,
    2018: parse_2018,
    2021: parse_2021,
    2023: parse_2023,
    2024: parse_2024,
}


def save_csv(year: int, members: List[Dict], output_dir: Path, force: bool = False) -> Optional[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / f'qip_{year}_committees.csv'

    if output_file.exists() and not force:
        print(f'  Skipping {output_file} (already exists, use --force to overwrite)')
        return None

    fieldnames = ['venue', 'year', 'committee_type', 'position', 'full_name', 'affiliation', 'role_title']

    with open(output_file, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for member in members:
            row = {'venue': 'QIP', 'year': year}
            row.update(member)
            writer.writerow(row)

    return output_file


def scrape_year(year: int, output_dir: Path, force: bool = False) -> bool:
    if year not in PARSERS:
        print(f'  No parser for QIP {year}')
        return False

    print(f'Scraping QIP {year}...')
    try:
        members = PARSERS[year]()
        if not members:
            print(f'  WARNING: No members found for QIP {year}')
            return False

        # Deduplicate
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

    except Exception as e:
        print(f'  ERROR scraping QIP {year}: {e}')
        import traceback
        traceback.print_exc()
        return False


def main():
    parser = argparse.ArgumentParser(description='Scrape QIP historical committee data')
    parser.add_argument('--year', type=int, help='Specific year to scrape')
    parser.add_argument('--all', action='store_true', help='Scrape all missing years')
    parser.add_argument('--output-dir', type=str, default=str(OUTPUT_DIR),
                        help=f'Output directory (default: {OUTPUT_DIR})')
    parser.add_argument('--force', action='store_true', help='Overwrite existing files')
    args = parser.parse_args()

    output_dir = Path(args.output_dir)

    if args.year:
        scrape_year(args.year, output_dir, args.force)
    elif args.all:
        success = 0
        for year in sorted(PARSERS.keys()):
            if scrape_year(year, output_dir, args.force):
                success += 1
        print(f'\nDone: {success}/{len(PARSERS)} years scraped successfully.')
    else:
        parser.print_help()
        print(f'\nAvailable years: {sorted(PARSERS.keys())}')


if __name__ == '__main__':
    main()
