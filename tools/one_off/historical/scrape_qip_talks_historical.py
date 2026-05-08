#!/usr/bin/env python3
"""Scrape QIP historical talk data from local archive.

Usage:
    python scrape_qip_talks_historical.py [--year YEAR] [--all] [--output-dir DIR]

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

CSV_FIELDS = [
    'venue', 'year', 'paper_type', 'title', 'speaker', 'authors',
    'affiliations', 'abstract', 'arxiv_ids', 'presentation_url', 'video_url',
    'session_name', 'award', 'notes', 'scheduled_date', 'scheduled_time',
    'duration_minutes',
]


def make_talk(**kwargs) -> Dict:
    """Return a dict with all CSV fields defaulting to empty string."""
    talk = {f: '' for f in CSV_FIELDS}
    talk['venue'] = 'QIP'
    talk.update(kwargs)
    return talk


def read_html(path: Path, encoding: str = 'utf-8') -> BeautifulSoup:
    with open(path, encoding=encoding, errors='replace') as f:
        return BeautifulSoup(f.read(), 'html.parser')


def extract_arxiv_id(text: str) -> Optional[str]:
    """Extract arXiv ID from a URL like arxiv.org/abs/1234.5678 or text like arXiv:1234."""
    m = re.search(r'arxiv\.org/abs/([^\s"\'<>&]+)', text, re.IGNORECASE)
    if m:
        return m.group(1).strip().rstrip('.')
    m = re.search(r'arXiv[:\s]+([0-9]{4}\.[0-9]{3,5}(?:v\d+)?)', text, re.IGNORECASE)
    if m:
        return m.group(1)
    return None


def extract_arxiv_ids_from_tag(tag) -> str:
    """Extract all arXiv IDs from a BeautifulSoup tag's links and text."""
    ids = []
    for a in tag.find_all('a', href=True):
        aid = extract_arxiv_id(a['href'])
        if aid:
            ids.append(aid)
    # Also check text for inline arXiv: patterns
    text = tag.get_text()
    for m in re.finditer(r'arXiv[:\s]+([0-9]{4}\.[0-9]{3,5}(?:v\d+)?)', text, re.IGNORECASE):
        aid = m.group(1)
        if aid not in ids:
            ids.append(aid)
    return ';'.join(ids)


def parse_time_range(text: str) -> Tuple[str, int]:
    """Parse '09:30-10:20' or '9.30 - 10.20' -> ('09:30', 50 minutes)."""
    text = text.strip()
    # Normalize separators
    text = text.replace('.', ':')
    m = re.search(r'(\d{1,2}):(\d{2})\s*[-–]\s*(\d{1,2}):(\d{2})', text)
    if m:
        h1, m1, h2, m2 = int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))
        start = f'{h1:02d}:{m1:02d}'
        duration = (h2 * 60 + m2) - (h1 * 60 + m1)
        return start, duration
    # Single time only
    m = re.search(r'(\d{1,2}):(\d{2})', text)
    if m:
        return f'{int(m.group(1)):02d}:{m.group(2)}', 0
    return '', 0


def classify_type(text: str, duration: int = 0) -> str:
    """Map keyword or duration to paper_type."""
    lower = text.lower()
    if 'tutorial' in lower:
        return 'tutorial'
    if 'public lecture' in lower or 'public talk' in lower:
        return 'public_lecture'
    if 'plenary' in lower or 'plenary lecture' in lower:
        return 'plenary'
    if 'invited' in lower or 'featured' in lower:
        return 'invited'
    if 'poster' in lower:
        return 'poster'
    if duration >= 45:
        return 'invited'
    return 'regular'


def join_authors(names: List[str]) -> str:
    return ';'.join(n.strip() for n in names if n.strip())


def save_csv(talks: List[Dict], year: int, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f'qip_{year}_talks.csv'
    with open(path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(talks)
    print(f'Wrote {len(talks)} talks to {path}')


# ============================================================
# Year-specific parsers
# ============================================================


def parse_2002() -> List[Dict]:
    """QIP 2002 — Schedule.html
    Pattern: <p><b>TIME</b> <i>Name, Affil</i>: <b><a href="...">Title</a></b>
    Below a grid overview, in session blocks under <h3> day headers.
    """
    soup = read_html(ARCHIVE_BASE / '2002' / 'Schedule.html')
    talks = []

    # Day date map from Schedule.html context
    day_dates = {
        'monday': '2002-01-14',
        'tuesday': '2002-01-15',
        'wednesday': '2002-01-16',
        'thursday': '2002-01-17',
    }
    current_date = ''

    for tag in soup.find_all(['h3', 'p']):
        if tag.name == 'h3':
            text = tag.get_text(strip=True).lower()
            for day, date in day_dates.items():
                if day in text:
                    current_date = date
                    break
            continue

        # Look for <p> with <b>TIME</b> <i>Name</i>: <b><a>Title</a></b>
        b_tags = tag.find_all('b')
        if not b_tags:
            continue
        first_b = b_tags[0].get_text(strip=True)
        # Check if first <b> looks like a time
        time_match = re.match(r'^(\d{1,2}:\d{2})$', first_b)
        if not time_match:
            continue

        time_str = f'{int(first_b.split(":")[0]):02d}:{first_b.split(":")[1]}'
        i_tag = tag.find('i')
        speaker = ''
        affil = ''
        if i_tag:
            name_affil = i_tag.get_text(strip=True)
            # Format: "Name, Affil" or "Name Affil"
            parts = name_affil.split(',', 1)
            speaker = parts[0].strip()
            affil = parts[1].strip() if len(parts) > 1 else ''

        # Title from last <b><a> or last <b>
        title = ''
        for b in reversed(b_tags):
            a = b.find('a')
            if a:
                title = a.get_text(strip=True)
                if title and title not in ('TBA',):
                    break
            elif b.get_text(strip=True) != first_b:
                title = b.get_text(strip=True)
                break

        if not speaker and not title:
            continue

        talks.append(make_talk(
            year='2002',
            paper_type='invited',  # QIP 2002 was all invited talks
            title=title,
            speaker=speaker,
            authors=speaker,
            affiliations=affil,
            scheduled_date=current_date,
            scheduled_time=time_str,
        ))

    return talks


def parse_2004() -> List[Dict]:
    """QIP 2004 — schedule.html + abstracts.html.
    schedule.html: time in first <td>, anchor link to abstracts.html#Name.
    abstracts.html: <a name="Cleve"> with title and abstract.
    """
    base = ARCHIVE_BASE / '2004'
    sched_soup = read_html(base / 'schedule.html', encoding='iso-8859-1')
    abs_soup = read_html(base / 'abstracts.html', encoding='iso-8859-1')

    # Build abstracts dict keyed by anchor name
    # Pattern: <font size="4"><a name="Cleve">Richard Cleve:</a></font>
    # Then title, then abstract text
    abs_data = {}
    for a in abs_soup.find_all('a', attrs={'name': True}):
        anchor = a['name']
        if not anchor or anchor == 'invited':
            continue
        # Get name from link text
        name_text = a.get_text(strip=True).rstrip(':')
        # Title follows immediately — next non-empty text or <b>/<em> sibling
        # Look at parent's next siblings for title
        parent = a.find_parent()
        title = ''
        abstract = ''
        # Collect text from following siblings up to next <font size="4">
        siblings = list(parent.next_siblings)
        collecting = True
        for sib in siblings:
            if hasattr(sib, 'name'):
                if sib.name in ('font',) and sib.get('size') == '4':
                    break
                if sib.name == 'h2':
                    break
                text = sib.get_text(' ', strip=True)
                if text:
                    if not title:
                        title = text
                    else:
                        abstract += ' ' + text
            else:
                text = str(sib).strip()
                if text:
                    if not title:
                        title = text
                    else:
                        abstract += ' ' + text

        abs_data[anchor] = {
            'name': name_text,
            'title': title.strip(),
            'abstract': abstract.strip(),
        }

    # Parse schedule
    talks = []
    day_dates = {
        'thursday': '2004-01-15',
        'friday': '2004-01-16',
        'saturday': '2004-01-17',
        'sunday': '2004-01-18',
        'monday': '2004-01-19',
    }
    current_date = ''
    invited_duration = 50  # "45 minutes long, plus 5 minutes for questions"
    contrib_duration = 15  # "12 minutes long, plus 3 minutes for questions"

    for tag in sched_soup.find_all(['b', 'tr']):
        if tag.name == 'b':
            text = tag.get_text(strip=True).lower()
            for day, date in day_dates.items():
                if day in text:
                    current_date = date
                    break
            continue

        # It's a <tr>
        tds = tag.find_all('td', recursive=False)
        if len(tds) < 2:
            continue
        time_text = tds[0].get_text(strip=True)
        content_td = tds[1]

        # Parse time range
        sched_time, duration = parse_time_range(time_text)
        if not sched_time:
            continue

        # Look for anchor link to abstracts.html#Name
        a_tag = content_td.find('a', href=re.compile(r'abstracts\.html#'))
        if not a_tag:
            # Check for plain title (like "Introduction")
            title_text = content_td.get_text(strip=True)
            if title_text and 'break' not in title_text.lower() and 'lunch' not in title_text.lower():
                pass  # skip non-talk rows
            continue

        href = a_tag.get('href', '')
        anchor = href.split('#')[-1] if '#' in href else ''
        if not anchor or anchor not in abs_data:
            # Try using the link text as speaker name
            speaker_name = a_tag.get_text(strip=True)
            title = content_td.get_text(strip=True)
            if duration == 0:
                duration = invited_duration if 'invited' in title.lower() else contrib_duration
            paper_type = classify_type('invited' if duration >= 45 else 'regular', duration)
            talks.append(make_talk(
                year='2004',
                paper_type=paper_type,
                title=title,
                speaker=speaker_name,
                authors=speaker_name,
                scheduled_date=current_date,
                scheduled_time=sched_time,
                duration_minutes=str(duration) if duration else '',
            ))
            continue

        info = abs_data[anchor]
        if duration == 0:
            duration = invited_duration if 'invited' in abs_soup.get_text()[abs_soup.get_text().find(anchor)-200:abs_soup.get_text().find(anchor)].lower() else contrib_duration
        paper_type = classify_type('invited' if duration >= 45 else 'regular', duration)

        talks.append(make_talk(
            year='2004',
            paper_type=paper_type,
            title=info['title'],
            speaker=info['name'],
            authors=info['name'],
            abstract=info['abstract'],
            scheduled_date=current_date,
            scheduled_time=sched_time,
            duration_minutes=str(duration),
        ))

    return talks


def _parse_2004_abstracts_section(abs_soup) -> Dict[str, Dict]:
    """Build dict from abstracts.html keyed by <a name="...">."""
    abs_data = {}
    # Find all named anchors in font tags
    for font in abs_soup.find_all('font', size='4'):
        a = font.find('a', attrs={'name': True})
        if not a:
            continue
        anchor = a['name']
        if not anchor or anchor in ('invited', 'contributed'):
            continue
        name_text = a.get_text(strip=True).rstrip(':')

        # Collect title and abstract from siblings following this font tag
        title = ''
        abstract_parts = []
        nxt = font.find_next_sibling()
        seen_next_section = False
        while nxt and not seen_next_section:
            if hasattr(nxt, 'name'):
                if nxt.name == 'font' and nxt.get('size') == '4':
                    break
                if nxt.name in ('h2', 'h3', 'hr'):
                    break
                text = nxt.get_text(' ', strip=True)
                if text:
                    if not title:
                        title = text
                    else:
                        abstract_parts.append(text)
            else:
                text = str(nxt).strip()
                if text and text not in ('<br>', '<br/>', '&nbsp;'):
                    if not title:
                        title = text
            nxt = nxt.find_next_sibling()

        abs_data[anchor] = {
            'name': name_text,
            'title': title.strip(),
            'abstract': ' '.join(abstract_parts).strip(),
        }
    return abs_data


def parse_2004_v2() -> List[Dict]:
    """QIP 2004 — improved parser using section-based approach."""
    base = ARCHIVE_BASE / '2004'
    sched_soup = read_html(base / 'schedule.html', encoding='iso-8859-1')
    abs_soup = read_html(base / 'abstracts.html', encoding='iso-8859-1')

    abs_data = _parse_2004_abstracts_section(abs_soup)

    # Determine which anchors are invited (in "Invited Talks" section)
    invited_anchors = set()
    text = abs_soup.get_text()
    invited_start = text.lower().find('invited talk')
    contrib_start = text.lower().find('contributed talk')
    if invited_start >= 0:
        for anchor in abs_data:
            # Find position of anchor in abs soup
            a_tag = abs_soup.find('a', attrs={'name': anchor})
            if a_tag:
                pos = text.find(abs_data[anchor]['name'])
                if contrib_start < 0 or (pos >= invited_start and (contrib_start < 0 or pos < contrib_start)):
                    invited_anchors.add(anchor)

    talks = []
    day_dates = {
        'thursday': '2004-01-15',
        'friday': '2004-01-16',
        'saturday': '2004-01-17',
        'sunday': '2004-01-18',
        'monday': '2004-01-19',
    }
    current_date = ''

    # Walk through schedule rows
    for tag in sched_soup.descendants:
        if not hasattr(tag, 'name'):
            continue
        # Day headers (in <b><i> or plain text in <td colspan="2">)
        if tag.name in ('b', 'i') and tag.parent and tag.parent.name == 'td':
            text = tag.get_text(strip=True).lower()
            for day, date in day_dates.items():
                if day in text:
                    current_date = date
                    break

    # Simpler: parse all <tr> in main table
    current_date = ''
    for tr in sched_soup.find_all('tr'):
        tds = tr.find_all('td')
        if not tds:
            continue

        # Check for day header
        if len(tds) >= 2:
            b_tag = tds[0].find('b') or tds[0].find('i')
            if b_tag:
                btext = b_tag.get_text(strip=True).lower()
                for day, date in day_dates.items():
                    if day in btext:
                        current_date = date
                        break

        # Look for time + anchor
        if len(tds) < 2:
            continue
        time_text = tds[0].get_text(strip=True)
        sched_time, duration = parse_time_range(time_text)
        if not sched_time:
            continue

        content_td = tds[1]
        a_tag = content_td.find('a', href=re.compile(r'abstracts\.html#'))
        if not a_tag:
            continue

        href = a_tag.get('href', '')
        anchor = re.search(r'#(\w+)', href)
        if not anchor:
            continue
        anchor = anchor.group(1)

        info = abs_data.get(anchor)
        if not info:
            # Use link text as fallback
            info = {'name': a_tag.get_text(strip=True), 'title': '', 'abstract': ''}

        # Also get title from inline quote in schedule if present
        # e.g. Cleve "Consequences and limits..."
        cell_text = content_td.get_text(' ', strip=True)
        inline_title_m = re.search(r'["\u201c](.+?)["\u201d]', cell_text)
        if inline_title_m and not info.get('title'):
            info['title'] = inline_title_m.group(1).strip()

        paper_type = 'invited' if (duration >= 40 or anchor in invited_anchors) else 'regular'
        if paper_type == 'regular' and duration == 0:
            duration = 15

        talks.append(make_talk(
            year='2004',
            paper_type=paper_type,
            title=info.get('title', ''),
            speaker=info['name'],
            authors=info['name'],
            abstract=info.get('abstract', ''),
            scheduled_date=current_date,
            scheduled_time=sched_time,
            duration_minutes=str(duration) if duration else '',
        ))

    return talks


def parse_2006() -> List[Dict]:
    """QIP 2006 — schedule.html (legacy HTML with unclosed tags, parsed via regex).

    Highlighted rows: <tr bgcolor=LemonChiffon> — one per talk.
    First <td>: time range (e.g. 9:30-10:20).
    Second <td>: <b>Title</b><br> by Speaker (Affil), joint work with ...
    Day headers: <td colspan=2 bgcolor=orange> containing 'Monday 16th' etc.
    Duration >= 45 min → invited, otherwise → regular.
    """
    html = (ARCHIVE_BASE / '2006' / 'schedule.html').read_text(encoding='utf-8', errors='replace')

    day_dates = {
        'monday 16':    '2006-01-16',
        'tuesday 17':   '2006-01-17',
        'wednesday 18': '2006-01-18',
        'thursday 19':  '2006-01-19',
        'friday 20':    '2006-01-20',
    }

    # Split on LemonChiffon rows; track current day from orange headers before each block
    talks = []
    all_blocks = list(re.finditer(
        r'<tr\s+bgcolor=LemonChiffon[^>]*>(.*?)(?=<tr|</table>)',
        html, re.DOTALL | re.IGNORECASE
    ))

    for block in all_blocks:
        raw = block.group(0)

        # Determine current day from last orange header before this block
        preceding = html[:block.start()].lower()
        current_date = ''
        for day_key, date in day_dates.items():
            if day_key in preceding:
                current_date = date   # last match wins

        # Extract time range
        time_m = re.search(r'(\d{1,2}:\d{2})\s*-\s*(\d{1,2}:\d{2})', raw)
        if not time_m:
            continue
        sched_time, duration = parse_time_range(time_m.group(0))
        if duration <= 0:
            continue

        # Extract title from <b>..title..</b>
        title_m = re.search(r'<b[^>]*>\s*(?:<a[^>]*>)?\s*(.*?)\s*(?:</a>)?\s*</b>',
                            raw, re.DOTALL | re.IGNORECASE)
        if not title_m:
            continue
        title = re.sub(r'\s+', ' ', title_m.group(1)).strip()
        if not title or len(title) < 4:
            continue

        # Strip HTML tags from title
        title = re.sub(r'<[^>]+>', '', title).strip()

        # Extract "by Speaker (Affil), joint work with ..."
        by_m = re.search(
            r'\bby\s+([^(\n<]+?)(?:\s*\(([^)]*)\))?(?:[,\s]+joint work with\s+([^\n<]+))?(?:\n|$)',
            raw, re.IGNORECASE
        )
        speaker = ''
        affil = ''
        joint_authors = ''
        if by_m:
            speaker = re.sub(r'\s+', ' ', by_m.group(1)).strip().rstrip(',')
            affil = by_m.group(2).strip() if by_m.group(2) else ''
            joint_authors = re.sub(r'\s+', ' ', by_m.group(3)).strip() if by_m.group(3) else ''

        # Build authors list: speaker first, then joint authors
        if joint_authors:
            author_list = [speaker] + [a.strip() for a in re.split(r',\s*', joint_authors) if a.strip()]
        else:
            author_list = [speaker] if speaker else []

        paper_type = 'invited' if duration >= 45 else 'regular'

        talks.append(make_talk(
            year='2006',
            paper_type=paper_type,
            title=title,
            speaker=speaker,
            authors=';'.join(author_list),
            affiliations=affil,
            scheduled_date=current_date,
            scheduled_time=sched_time,
            duration_minutes=str(duration),
        ))

    return talks


def parse_2007() -> List[Dict]:
    """QIP 2007 — program.htm.

    The program page has three sections after the timetable grid:
      <h2>Invited talks</h2>       → paper_type=invited, duration=50
      <h2>30 minute oral presentations</h2> → paper_type=regular, duration=30
      <h2>15 minute oral presentations</h2> → paper_type=regular, duration=15
    Each section has a <table> with rows: Title | Speaker (some rows interleaved
    with blank rows).

    Schedule dates/times come from the timetable grid by matching on speaker
    last name. QIP 2007 ran Tue 30 Jan – Sat 3 Feb 2007 in Brisbane.
    """
    soup = read_html(ARCHIVE_BASE / '2007' / 'program.htm', encoding='utf-8')

    day_col_dates = ['2007-01-30', '2007-01-31', '2007-02-01', '2007-02-02', '2007-02-03']

    # --- Build schedule lookup from timetable grid ---
    # Row 0 = day headers (Tuesday … Saturday), subsequent rows = time + speakers
    schedule: dict[str, tuple[str, str, int]] = {}  # last_name_lower -> (date, time, duration)

    h2_draft = soup.find('h2', string=lambda t: t and 'Draft' in t)
    grid_table = h2_draft.find_next('table') if h2_draft else None
    if grid_table:
        rows = grid_table.find_all('tr')
        # Compute durations from consecutive row times
        row_times: list[tuple[int, list[str]]] = []  # (minutes_since_midnight, [col_texts])
        for tr in rows:
            cells = [td.get_text(' ', strip=True) for td in tr.find_all('td')]
            if not cells:
                continue
            tm = re.match(r'(\d{1,2}):(\d{2})(am|pm)', cells[0].replace(' ', '').lower())
            if not tm:
                continue
            h, m_, ampm = int(tm.group(1)), int(tm.group(2)), tm.group(3)
            if ampm == 'pm' and h != 12:
                h += 12
            if ampm == 'am' and h == 12:
                h = 0
            row_times.append((h * 60 + m_, cells))

        for i, (start_mins, cells) in enumerate(row_times):
            end_mins = row_times[i + 1][0] if i + 1 < len(row_times) else start_mins
            duration = end_mins - start_mins
            hh, mm = divmod(start_mins, 60)
            time_str = f'{hh:02d}:{mm:02d}'
            for col_idx, cell_text in enumerate(cells[1:6], start=0):  # skip time column
                cell_text = cell_text.strip()
                if not cell_text or cell_text.upper() in ('MORNING TEA', 'AFTERNOON TEA',
                                                           'LUNCH', 'POSTERS', 'DINNER',
                                                           'FREE TIME', 'BUSINESS MEETING'):
                    continue
                # Extract last name (strip "(invited)" annotation)
                name = re.sub(r'\(.*?\)', '', cell_text).strip()
                last = name.split()[-1].lower() if name.split() else ''
                if last and col_idx < len(day_col_dates):
                    schedule[last] = (day_col_dates[col_idx], time_str, duration)

    # --- Parse the three talk sections ---
    section_config = [
        ('Invited talks',                'invited', 50, 'name_title'),
        ('30 minute oral presentations', 'regular', 30, 'title_name'),
        ('15 minute oral presentations', 'regular', 15, 'title_name'),
    ]

    talks = []
    for heading, paper_type, default_duration, col_order in section_config:
        h2 = soup.find('h2', string=lambda t: t and heading.lower() in t.lower())
        if not h2:
            continue
        tbl = h2.find_next_sibling('table')
        if not tbl:
            tbl = h2.find_next('table')
        if not tbl:
            continue

        for tr in tbl.find_all('tr'):
            cells = [td.get_text(' ', strip=True) for td in tr.find_all('td')]
            if len(cells) < 2:
                continue
            if col_order == 'name_title':
                speaker, title = cells[0].strip(), cells[1].strip()
            else:
                title, speaker = cells[0].strip(), cells[1].strip()

            if not title or len(title) < 4:
                continue

            # Look up schedule by last name
            last = speaker.split()[-1].lower() if speaker.split() else ''
            sched = schedule.get(last, ('', '', 0))
            date, time_str, grid_duration = sched

            talks.append(make_talk(
                year='2007',
                paper_type=paper_type,
                title=title,
                speaker=speaker,
                authors=speaker,
                scheduled_date=date,
                scheduled_time=time_str,
                duration_minutes=str(default_duration),
            ))

    return talks


def parse_2008() -> List[Dict]:
    """QIP 2008 — Program.html.
    Structure: <h3> section headers, <ul>/<ol> with <li> per talk.
    Invited talks: <h3>Invited talks</h3> -> <ul><li>Name, Affil
    Contributed: <h4>There will be ten 30-minute talks</h4> / <h4>twenty 20-minute talks</h4>
    Posters: <h3>Posters</h3> -> <ol><li>Author. <em>Title</em>
    """
    soup = read_html(ARCHIVE_BASE / '2008' / 'Program.html', encoding='iso-8859-1')
    talks = []

    current_section = ''
    current_duration = 0
    current_type = 'regular'

    for tag in soup.find_all(['h3', 'h4', 'li']):
        if tag.name in ('h3', 'h4'):
            text = tag.get_text(strip=True).lower()
            if 'invited' in text:
                current_section = 'invited'
                current_type = 'invited'
                current_duration = 50
            elif 'ten 30-minute' in text or '30-minute' in text:
                current_section = 'contributed'
                current_type = 'regular'
                current_duration = 30
            elif 'twenty 20-minute' in text or '20-minute' in text:
                current_section = 'contributed'
                current_type = 'regular'
                current_duration = 20
            elif 'poster' in text:
                current_section = 'posters'
                current_type = 'poster'
                current_duration = 0
            elif 'contributed' in text:
                current_section = 'contributed'
                current_type = 'regular'
                current_duration = 25
            continue

        if tag.name == 'li' and current_section:
            # The page uses unclosed <li> tags, so BeautifulSoup nests every
            # subsequent sibling inside the first one. Skip wrapper <li>s that
            # contain section headers (h3/h4) — they are not talks themselves,
            # just containers for the <h4> + nested <ol>.
            if tag.find(['h3', 'h4']):
                continue

            # For invited: <li><a href="...">Name</a>, Affil
            # For contributed/posters: <li>Author One and Author Two. <em>Title</em>
            em = tag.find('em')
            title = em.get_text(strip=True) if em else ''

            if current_section == 'invited':
                # Walk only this <li>'s direct contents — stop at the first
                # BS4-nested <li>, which is actually the next invited entry
                # (the page leaves <li> tags unclosed).
                own_parts = []
                a_tag = None
                for child in tag.contents:
                    if getattr(child, 'name', None) == 'li':
                        break
                    if a_tag is None and getattr(child, 'name', None) == 'a':
                        a_tag = child
                    if hasattr(child, 'get_text'):
                        own_parts.append(child.get_text(' ', strip=True))
                    else:
                        own_parts.append(str(child).strip())
                own_text = re.sub(r'\s+', ' ', ' '.join(p for p in own_parts if p)).strip()

                if a_tag:
                    speaker = a_tag.get_text(strip=True)
                    affil = own_text[len(speaker):].strip().lstrip(',').strip()
                elif ',' in own_text:
                    # No link — assume "Name, Affiliation, ..." and split on first comma.
                    speaker, affil = own_text.split(',', 1)
                    speaker = speaker.strip()
                    affil = affil.strip()
                else:
                    speaker = own_text
                    affil = ''

                talks.append(make_talk(
                    year='2008',
                    paper_type='invited',
                    title=title,
                    speaker=speaker,
                    authors=speaker,
                    affiliations=affil,
                    duration_minutes=str(current_duration),
                ))
            else:
                # Contributed/posters: author list before first <em>.
                # `tag.find('em')` returns the first <em> in DFS order — for an
                # unclosed-li chain that's the current talk's own title, so the
                # text before it is exactly this talk's authors.
                full_text = tag.get_text(' ', strip=True)
                if em:
                    authors_text = full_text[:full_text.find(title)].strip().rstrip('.')
                else:
                    authors_text = full_text

                # Author list format: "A, B, C and D" (no Oxford comma).
                # Split on " and " then split each chunk on commas to handle
                # both "A and B" and "A, B, C and D" correctly.
                authors_text = re.sub(r'\s+', ' ', authors_text)
                author_list = []
                for chunk in re.split(r'\s+and\s+', authors_text):
                    author_list.extend(a.strip() for a in chunk.split(',') if a.strip())

                # Speaker is first author
                speaker = author_list[0].strip() if author_list else ''

                talks.append(make_talk(
                    year='2008',
                    paper_type=current_type,
                    title=title,
                    speaker=speaker,
                    authors=join_authors(author_list),
                    duration_minutes=str(current_duration) if current_duration else '',
                ))

    return talks


def parse_2009() -> List[Dict]:
    """QIP 2009 — talks.html.
    Invited: <h2><b>Invited Talks</b></h2> -> <ul><li>Name (Affil)<br><em>Title</em><br>Abstract
    Contributed: <p class="style4">TEN 30-MINUTE TALKS</p> -> <p>Author. <em>Title</em>
    """
    soup = read_html(ARCHIVE_BASE / '2009' / 'talks.html', encoding='iso-8859-1')
    talks = []

    current_section = ''
    current_duration = 0

    for tag in soup.find_all(['h2', 'p', 'li']):
        if tag.name == 'h2':
            text = tag.get_text(strip=True).lower()
            if 'invited' in text:
                current_section = 'invited'
                current_duration = 50
            elif 'contributed' in text:
                current_section = 'contributed'
            continue

        if tag.name == 'p' and tag.get('class') == ['style4']:
            text = tag.get_text(strip=True).upper()
            m = re.search(r'(\w+)\s+(\d+)-MINUTE', text)
            if m:
                current_section = 'contributed'
                current_duration = int(m.group(2))
            continue

        if tag.name == 'li' and current_section == 'invited':
            # Format: Name (Affil)<br><em>Title</em><br>Abstract...
            # Get all text children split by <br>
            parts = []
            for child in tag.children:
                if hasattr(child, 'name'):
                    if child.name == 'br':
                        parts.append('\n')
                    elif child.name == 'em':
                        parts.append('TITLE:' + child.get_text(strip=True))
                    else:
                        parts.append(child.get_text(' ', strip=True))
                else:
                    parts.append(str(child))

            full = ''.join(parts)
            lines = [l.strip() for l in full.split('\n') if l.strip()]

            speaker = ''
            affil = ''
            title = ''
            abstract_parts = []

            for i, line in enumerate(lines):
                if line.startswith('TITLE:'):
                    title = line[6:].strip()
                elif not speaker:
                    # First non-empty line is speaker (Name (Affil) format)
                    m = re.match(r'^(.*?)\s*\(([^)]+)\)\s*$', line)
                    if m:
                        speaker = m.group(1).strip()
                        affil = m.group(2).strip()
                    else:
                        speaker = line
                elif title:
                    abstract_parts.append(line)

            # Also extract co-author info from "Joint work with..."
            full_text = tag.get_text(' ', strip=True)
            notes = ''
            joint_m = re.search(r'[Jj]oint work with (.+?)[\.\n]', full_text)
            if joint_m:
                notes = 'Joint work with ' + joint_m.group(1)

            talks.append(make_talk(
                year='2009',
                paper_type='invited',
                title=title,
                speaker=speaker,
                authors=speaker,
                affiliations=affil,
                abstract=' '.join(abstract_parts),
                notes=notes,
                duration_minutes=str(current_duration),
            ))

        elif tag.name == 'p' and current_section == 'contributed' and tag.get('class') != ['style4']:
            # Format: "Author Name(s). <em>Title of Paper</em>"
            em = tag.find('em')
            if not em:
                continue
            title = em.get_text(strip=True)
            full_text = tag.get_text(' ', strip=True)
            # Authors: text before title
            authors_text = full_text[:full_text.find(title)].strip().rstrip('.')
            if not authors_text:
                continue

            # Parse author list
            author_list = _split_author_list(authors_text)
            speaker = author_list[0] if author_list else ''

            talks.append(make_talk(
                year='2009',
                paper_type='regular',
                title=title,
                speaker=speaker,
                authors=join_authors(author_list),
                duration_minutes=str(current_duration),
            ))

    return talks


def _split_author_list(text: str) -> List[str]:
    """Split 'A, B and C' or 'A and B' into individual names."""
    text = text.strip().rstrip('.')
    # Split on ' and '
    parts = re.split(r'\s+and\s+', text)
    result = []
    for part in parts:
        # Further split on commas for "A, B, C and D" style multi-author lists
        sub = [s.strip() for s in part.split(',') if s.strip()]
        result.extend(sub)
    return [r for r in result if r]


def _parse_timetable_rows(soup, year: int, file_hint: str = '') -> List[Dict]:
    """Parse QIP 2010/2011-style timetable tables.

    Structure:
    - Day headers in <h3 class="heading"> or <b>Day text</b>
    - Table rows <tr class="odd/even"> or plain <tr>
    - First <td>: time range (e.g. "10.55 - 11.25")
    - Second <td>: content with <u> speaker, <em> title, watch/arXiv links
    For 2011: speaker in <b>...</b> with (plenary/featured) markers, <u> = presenter
    """
    talks = []

    # Collect day headers and their positions
    # We'll track current_date by finding day headings
    day_map_2010 = {
        'sunday': '2010-01-17',
        'monday': '2010-01-18',
        'tuesday': '2010-01-19',
        'wednesday': '2010-01-20',
        'thursday': '2010-01-21',
        'friday': '2010-01-22',
    }
    day_map_2011 = {
        'sunday': '2011-01-09',
        'monday': '2011-01-10',
        'tuesday': '2011-01-11',
        'wednesday': '2011-01-12',
        'thursday': '2011-01-13',
        'friday': '2011-01-14',
    }
    day_map = day_map_2011 if year == 2011 else day_map_2010

    current_date = ''

    for tag in soup.find_all(['h3', 'b', 'tr']):
        # Day header detection
        if tag.name in ('h3', 'b'):
            text = tag.get_text(strip=True).lower()
            for day, date in day_map.items():
                if day in text and any(str(d) in text for d in range(1, 32)):
                    current_date = date
                    break
            continue

        if tag.name != 'tr':
            continue

        tds = tag.find_all('td', recursive=False)
        if len(tds) < 2:
            continue

        time_td = tds[0]
        content_td = tds[1]

        time_text = time_td.get_text(' ', strip=True)
        sched_time, duration = parse_time_range(time_text)
        if not sched_time:
            continue

        content_text = content_td.get_text(' ', strip=True).strip()
        if not content_text:
            continue

        # Skip breaks, registration, lunch, etc.
        skip_words = ['break', 'registration', 'lunch', 'excursion', 'banquet',
                      'reception', 'opening', 'closing', 'rump', 'poster', 'business',
                      'welcome', 'drinks', 'session chair', 'sponsor']
        content_lower = content_text.lower()
        if any(w in content_lower for w in skip_words):
            # Only skip if it doesn't also look like a real talk (title + authors)
            em_in_content = content_td.find('em') or content_td.find('i')
            if not em_in_content:
                continue

        # Find speaker: <u> takes priority, else <b> first name
        u_tag = content_td.find('u')
        b_tag = content_td.find('b')

        speaker = ''
        all_authors = ''
        if u_tag:
            speaker = u_tag.get_text(strip=True)

        # Get type from content
        type_hint = ''
        if year == 2011:
            # In 2011: (plenary, ...) or (featured) in <b> tag
            if b_tag:
                b_text = b_tag.get_text(' ', strip=True)
                if 'plenary' in b_text.lower():
                    type_hint = 'plenary'
                elif 'featured' in b_text.lower():
                    type_hint = 'invited'
                else:
                    type_hint = 'regular'
        else:
            # 2010: "Invited talk:" prefix or "Invited perspective talk:"
            if 'invited' in content_text.lower()[:50]:
                type_hint = 'invited'
            elif duration >= 45:
                type_hint = 'invited'
            else:
                type_hint = 'regular'

        # Get title from <em> tag
        em_tag = content_td.find('em')
        title = em_tag.get_text(strip=True) if em_tag else ''

        # If no speaker yet, try to extract from content
        if not speaker:
            if year == 2011 and b_tag:
                b_text = b_tag.get_text(' ', strip=True)
                # Remove type markers
                b_text = re.sub(r'\s*\([^)]+\)\s*', ' ', b_text).strip().rstrip(':')
                # First "name" before ':'
                speaker = b_text.split(':')[0].strip()
            elif year == 2010:
                # Try <p class="p"><u>Name</u>
                u2 = content_td.find('u')
                if u2:
                    speaker = u2.get_text(strip=True)

        # Get all authors from b_tag (2011) or content (2010)
        if year == 2011 and b_tag:
            b_text = b_tag.get_text(' ', strip=True)
            # Remove type markers like "(plenary, based on joint work with...)"
            b_text = re.sub(r'\s*\(plenary[^)]*\)', '', b_text, flags=re.IGNORECASE)
            b_text = re.sub(r'\s*\(featured[^)]*\)', '', b_text, flags=re.IGNORECASE)
            b_text = b_text.strip().rstrip(':')
            # Extract co-author info after "based on joint work with"
            joint_m = re.search(r'based on joint work with (.+)', b_text, re.IGNORECASE)
            notes = ''
            if joint_m:
                notes = 'Joint work with ' + joint_m.group(1).strip()
                b_text = b_text[:b_text.lower().find('based on joint work')].strip()

            # Author list: split on comma/and
            author_parts = re.split(r',\s*|\s+and\s+', b_text)
            author_list = [a.strip().rstrip(':') for a in author_parts if a.strip()]
            all_authors = join_authors(author_list)
            if not speaker and author_list:
                # Speaker is the underlined one, or first if none underlined
                u_authors = [a.get_text(strip=True) for a in content_td.find_all('u')]
                speaker = u_authors[0] if u_authors else author_list[0]
        elif year == 2010:
            # Authors may follow speaker in same line, separated by comma
            # Look for text before <em>
            # Get text content of the td, stopping before <em>
            raw_html = str(content_td)
            em_pos = raw_html.find('<em>') if '<em>' in raw_html else len(raw_html)
            pre_em = BeautifulSoup(raw_html[:em_pos], 'html.parser').get_text(' ', strip=True)
            # Remove "Invited talk:" prefix
            pre_em = re.sub(r'^Invited\s+(?:perspective\s+)?talk:\s*', '', pre_em, flags=re.IGNORECASE)
            pre_em = pre_em.strip()
            if pre_em:
                # It's "Speaker and CoAuthor" or "Speaker, CoAuthor, ..."
                author_parts = re.split(r',\s*|\s+and\s+', pre_em)
                author_list = [a.strip() for a in author_parts if a.strip()]
                all_authors = join_authors(author_list)
                if not speaker and author_list:
                    speaker = author_list[0]

        if not speaker and not title:
            continue

        # arXiv IDs
        arxiv_ids = extract_arxiv_ids_from_tag(content_td)

        # Video URL
        video_url = ''
        watch_link = content_td.find('a', string=re.compile(r'[Ww]atch|[Vv]ideo'))
        if watch_link:
            video_url = watch_link.get('href', '')

        # Presentation/lecture URL
        pres_url = ''
        lecture_link = content_td.find('a', string=re.compile(r'[Ll]ecture|[Ss]lides'))
        if lecture_link:
            pres_url = lecture_link.get('href', '')

        paper_type = type_hint if type_hint else classify_type('', duration)

        talks.append(make_talk(
            year=str(year),
            paper_type=paper_type,
            title=title,
            speaker=speaker,
            authors=all_authors or speaker,
            arxiv_ids=arxiv_ids,
            presentation_url=pres_url,
            video_url=video_url,
            scheduled_date=current_date,
            scheduled_time=sched_time,
            duration_minutes=str(duration) if duration else '',
        ))

    return talks


def parse_2010() -> List[Dict]:
    """QIP 2010 — programme.html."""
    soup = read_html(ARCHIVE_BASE / '2010' / 'programme.html')
    return _parse_timetable_rows(soup, 2010)


def parse_2011() -> List[Dict]:
    """QIP 2011 — scientificprogramme/index.html (identical structure to 2010)."""
    soup = read_html(ARCHIVE_BASE / '2011' / 'scientificprogramme' / 'index.html')
    return _parse_timetable_rows(soup, 2011)


def parse_2012() -> List[Dict]:
    """QIP 2012 — scientific_e.php.html.
    Structure: <table border="1">, <h3> day headers.
    Row: first <td>=time, second <td>=content.
    Content: <u> presenter, (Plenary lecture)/(Featured talk)/(contributed talk), <a><i> title.
    """
    soup = read_html(ARCHIVE_BASE / '2012' / 'scientific_e.php.html', encoding='iso-8859-1')
    talks = []

    day_map = {
        'monday': '2011-12-12',
        'tuesday': '2011-12-13',
        'wednesday': '2011-12-14',
        'thursday': '2011-12-15',
        'friday': '2011-12-16',
    }
    current_date = ''

    for tag in soup.find_all(['h3', 'tr']):
        if tag.name == 'h3':
            text = tag.get_text(strip=True).lower()
            for day, date in day_map.items():
                if day in text:
                    current_date = date
                    break
            continue

        tds = tag.find_all('td', recursive=False)
        if len(tds) < 2:
            continue

        time_td = tds[0]
        content_td = tds[1]

        time_text = time_td.get_text(strip=True)
        sched_time, duration = parse_time_range(time_text)
        if not sched_time:
            continue

        content_text = content_td.get_text(' ', strip=True)
        skip_words = ['break', 'registration', 'lunch', 'excursion', 'banquet',
                      'reception', 'opening', 'closing', 'rump session', 'poster',
                      'welcome', 'session chair']
        if any(w in content_text.lower() for w in skip_words) and len(content_text) < 80:
            continue

        # Speaker: <u> tag
        u_tag = content_td.find('u')
        speaker = u_tag.get_text(strip=True) if u_tag else ''

        # All authors: text before the type parenthetical
        # Full text before first '('
        type_m = re.search(r'\((Plenary lecture|Featured talk|contributed talk)\)', content_text, re.IGNORECASE)
        type_hint = ''
        if type_m:
            raw_type = type_m.group(1).lower()
            if 'plenary' in raw_type:
                type_hint = 'plenary'
                if not duration:
                    duration = 55
            elif 'featured' in raw_type:
                type_hint = 'invited'
                if not duration:
                    duration = 30
            else:
                type_hint = 'regular'
                if not duration:
                    duration = 25
            # Authors: everything before the type marker
            authors_text = content_text[:type_m.start()].strip().rstrip(',').rstrip(';')
        else:
            authors_text = content_text.split('\n')[0].strip()
            type_hint = classify_type('', duration)

        # Parse author list (with presenter underlined)
        # Format: "Author One, Author Two and <u>Presenter</u>"
        # Get raw content text without the title/links portion
        # Split by <br> to get first line (authors)
        raw_html = str(content_td)
        br_pos = raw_html.find('<br')
        if br_pos > 0:
            first_line_html = raw_html[:br_pos]
            first_line_text = BeautifulSoup(first_line_html, 'html.parser').get_text(' ', strip=True)
        else:
            first_line_text = authors_text

        # Remove type marker from author line
        first_line_text = re.sub(r'\s*\((?:Plenary lecture|Featured talk|contributed talk)\)\s*',
                                  '', first_line_text, flags=re.IGNORECASE).strip().rstrip(':')

        author_parts = re.split(r',\s*|\s+and\s+', first_line_text)
        author_list = [a.strip() for a in author_parts if a.strip() and len(a.strip()) > 1]
        all_authors = join_authors(author_list)
        if not speaker and author_list:
            speaker = author_list[0]

        # Title: in <a><i> or <i>
        title = ''
        i_tag = content_td.find('i')
        if i_tag:
            title = i_tag.get_text(strip=True)
        if not title:
            a_tag = content_td.find('a', href=re.compile(r'abstract'))
            if a_tag:
                title = a_tag.get_text(strip=True)

        # arXiv
        arxiv_ids = extract_arxiv_ids_from_tag(content_td)

        # Video
        video_url = ''
        watch_link = content_td.find('a', string=re.compile(r'[Ww]atch'))
        if watch_link:
            video_url = watch_link.get('href', '')

        if not speaker and not title:
            continue

        talks.append(make_talk(
            year='2012',
            paper_type=type_hint or 'regular',
            title=title,
            speaker=speaker,
            authors=all_authors or speaker,
            arxiv_ids=arxiv_ids,
            video_url=video_url,
            scheduled_date=current_date,
            scheduled_time=sched_time,
            duration_minutes=str(duration) if duration else '',
        ))

    return talks


def parse_2013() -> List[Dict]:
    """QIP 2013 — program.html.1.html.
    Table-based, similar to 2012. Time in first <td>, content in second <td>.
    Speaker with <span style="text-decoration: underline;"> or <strong><span>.
    Type: "(Plenary Lecture)" in content.
    arXiv IDs from links.
    """
    soup = read_html(ARCHIVE_BASE / '2013' / 'program.html.1.html', encoding='utf-8')
    talks = []

    day_map = {
        'monday': '2013-01-21',
        'tuesday': '2013-01-22',
        'wednesday': '2013-01-23',
        'thursday': '2013-01-24',
        'friday': '2013-01-25',
    }
    current_date = ''

    for tag in soup.find_all(['p', 'tr']):
        if tag.name == 'p':
            text = tag.get_text(strip=True).lower()
            for day, date in day_map.items():
                if day in text and re.search(r'\d', text):
                    current_date = date
                    break
            continue

        tds = tag.find_all('td', recursive=False)
        if len(tds) < 2:
            continue

        time_td = tds[0]
        content_td = tds[1]

        time_text = time_td.get_text(strip=True).replace('\xa0', ' ')
        sched_time, duration = parse_time_range(time_text)
        if not sched_time:
            continue

        content_text = content_td.get_text(' ', strip=True)
        skip_words = ['break', 'registration', 'lunch', 'excursion', 'banquet',
                      'reception', 'opening', 'closing', 'rump', 'poster', 'session chair',
                      'welcome', 'logistic']
        if any(w in content_text.lower() for w in skip_words) and len(content_text) < 100:
            continue

        # Speaker: underlined via CSS inline style
        speaker = ''
        for span in content_td.find_all(['span', 'strong']):
            style = span.get('style', '')
            if 'text-decoration: underline' in style or 'underline' in style:
                speaker = span.get_text(strip=True)
                break

        # Type from parenthetical
        type_hint = 'regular'
        type_m = re.search(r'\(([^)]*(?:Plenary|Featured|Invited|contributed)[^)]*)\)',
                           content_text, re.IGNORECASE)
        if type_m:
            raw = type_m.group(1).lower()
            if 'plenary' in raw:
                type_hint = 'plenary'
            elif 'featured' in raw or 'invited' in raw:
                type_hint = 'invited'
        elif duration >= 45:
            type_hint = 'invited'

        # Title: after ':' or in italic/em
        title = ''
        # Look for text after ':' in the second line of content
        # Or look for <a href="..."><i>Title</i></a> pattern
        raw_html = str(content_td)
        # Find first <br> to separate header line from title
        br_pos = raw_html.find('<br')
        if br_pos > 0:
            title_html = raw_html[br_pos:]
            title_soup = BeautifulSoup(title_html, 'html.parser')
            # Look for title text - often in first meaningful text after <br>
            # Remove links and abstract/lecture/watch anchors
            for a in title_soup.find_all('a'):
                href = a.get('href', '')
                if 'abstract' in href.lower() or 'lecture' in href.lower() or \
                   'watch' in href.lower() or 'video' in href.lower() or \
                   'arxiv' in href.lower():
                    a.decompose()
            # Get first substantial text
            title_text = title_soup.get_text(' ', strip=True)
            # Clean up arXiv: markers
            title_text = re.sub(r'\s*arXiv\s*:.*', '', title_text, flags=re.IGNORECASE)
            title_text = re.sub(r'\s*abstract\s*.*', '', title_text, flags=re.IGNORECASE)
            title = title_text.strip()

        if not title:
            # Try looking for text after ':' in strong/b tags
            for strong in content_td.find_all(['strong', 'b']):
                st = strong.get_text(strip=True)
                if ':' in st:
                    title = st.split(':', 1)[1].strip()
                    if title:
                        break

        # Authors from <strong> first line
        authors_text = ''
        strong_tag = content_td.find('strong')
        if strong_tag:
            authors_raw = strong_tag.get_text(' ', strip=True)
            # Remove type markers
            authors_raw = re.sub(r'\s*\([^)]*\)\s*', ' ', authors_raw).strip().rstrip(':')
            # Split by comma/and
            parts = re.split(r',\s*|\s+and\s+', authors_raw)
            author_list = [p.strip() for p in parts if p.strip() and len(p.strip()) > 2]
            authors_text = join_authors(author_list)
            if not speaker and author_list:
                speaker = author_list[0]

        # arXiv
        arxiv_ids = extract_arxiv_ids_from_tag(content_td)

        # Video URL
        video_url = ''
        for a in content_td.find_all('a'):
            if 'watch' in a.get_text('', strip=True).lower():
                video_url = a.get('href', '')
                break

        # Presentation
        pres_url = ''
        for a in content_td.find_all('a'):
            if 'lecture' in a.get_text('', strip=True).lower():
                pres_url = a.get('href', '')
                break

        if not speaker and not title:
            continue

        talks.append(make_talk(
            year='2013',
            paper_type=type_hint,
            title=title,
            speaker=speaker,
            authors=authors_text or speaker,
            arxiv_ids=arxiv_ids,
            presentation_url=pres_url,
            video_url=video_url,
            scheduled_date=current_date,
            scheduled_time=sched_time,
            duration_minutes=str(duration) if duration else '',
        ))

    return talks


def parse_2014() -> List[Dict]:
    """QIP 2014 — cgi-bin/program.pl.html.
    Numbered list: <p><b>1a. Title</b><br>Author One, Author Two.</p>
    Mergers: <br><br><i>merged with</i> between paragraphs.
    HTML has unclosed <p> tags so we use regex on raw content.
    """
    from html import unescape
    path = ARCHIVE_BASE / '2014' / 'cgi-bin' / 'program.pl.html'
    with open(path, encoding='iso-8859-1', errors='replace') as f:
        raw = f.read()

    talks = []

    # Extract the main content region between the text div boundaries
    # Find all <p><b>NUMBER. Title</b><br>Authors patterns
    # Pattern: <p> then optional whitespace, <b>DIGIT(s)(letter?). Title</b><br>Authors
    # We split the raw HTML into "blocks" using <p> as delimiter
    # Each block is: <b>title</b><br>authors (possibly with merger info)

    # Find all numbered entries using regex on raw HTML
    pattern = re.compile(
        r'<b>\s*(\d+[a-zA-Z]?)\.\s+(.*?)</b>\s*<br[^>]*>\s*(.*?)(?=<p>|<hr|</div|$)',
        re.DOTALL | re.IGNORECASE
    )

    for m in pattern.finditer(raw):
        title_raw = m.group(2).strip()
        authors_raw = m.group(3).strip()

        # Clean title: remove HTML tags and decode entities
        title = unescape(re.sub(r'<[^>]+>', '', title_raw)).strip()

        # Extract merger note from authors section
        notes = ''
        merger_m = re.search(r'<i>\s*(merged with.*?)\s*</i>', authors_raw, re.IGNORECASE)
        if merger_m:
            notes = unescape(merger_m.group(1).strip())
            # Remove merger text from authors
            authors_raw = authors_raw[:merger_m.start()].strip()

        # Clean authors: remove HTML tags, decode entities
        authors_text = unescape(re.sub(r'<[^>]+>', ' ', authors_raw))
        authors_text = re.sub(r'\s+', ' ', authors_text).strip().rstrip('.')

        if not title or not authors_text:
            continue

        author_list = _split_author_list(authors_text)
        speaker = author_list[0] if author_list else ''

        talks.append(make_talk(
            year='2014',
            paper_type='regular',
            title=title,
            speaker=speaker,
            authors=join_authors(author_list),
            notes=notes,
        ))

    return talks


def parse_2015() -> List[Dict]:
    """QIP 2015 — Program.php.html.

    The page has a visual grid table at the top (overview only), followed by
    detailed per-day timetable sections (class="timetable") with full speaker
    names, titles in <i> tags, and links to abstracts, slides, and YouTube.

    Tutorial days: Jan 10-11.  Conference days: Jan 12-16.
    """
    soup = read_html(ARCHIVE_BASE / '2015' / 'Program.php.html')
    talks = []

    day_name_to_date = {
        'saturday': '2015-01-10',
        'sunday':   '2015-01-11',
        'monday':   '2015-01-12',
        'tuesday':  '2015-01-13',
        'wednesday':'2015-01-14',
        'thursday': '2015-01-15',
        'friday':   '2015-01-16',
    }

    skip_content = re.compile(
        r'^(break|lunch|registration|free discussion|poster session|'
        r'business meeting|rump session|conference banquet|group photo|'
        r'free afternoon|closing remark|opening remark|public lecture|'
        r'from \d)',
        re.IGNORECASE,
    )

    current_date = ''

    # Walk the document in order, tracking day headers and processing timetables
    for element in soup.find_all(['p', 'table']):
        if element.name == 'p':
            b = element.find('b')
            if b:
                text = b.get_text(strip=True).lower()
                for day_name, date in day_name_to_date.items():
                    if text.startswith(day_name):
                        current_date = date
                        break
            continue

        # Only process detailed timetable tables (not the overview grid)
        if 'timetable' not in (element.get('class') or []):
            continue

        for tr in element.find_all('tr'):
            cells = tr.find_all('td', recursive=False)
            if len(cells) < 2:
                continue

            time_td, content_td = cells[0], cells[1]
            time_text = time_td.get_text(strip=True)

            # Skip rows without a real time (Session Chair, headers, etc.)
            if not re.search(r'\d', time_text):
                continue

            # strip am/pm suffixes so parse_time_range can compute duration
            time_clean = re.sub(r'(?<=\d)(am|pm)', '', time_text, flags=re.IGNORECASE)
            sched_time, duration = parse_time_range(time_clean)
            # convert start time to 24-hour if the start (not end) time was PM
            if sched_time and re.match(r'\s*\d{1,2}[:.]\d{2}\s*pm', time_text, re.IGNORECASE):
                h, m_ = map(int, sched_time.split(':'))
                if h < 12:
                    sched_time = f'{h + 12:02d}:{m_:02d}'

            content_text = content_td.get_text(' ', strip=True)
            if skip_content.match(content_text):
                continue

            # Parse one or more talks from this content cell
            _parse_qip2015_content_cell(
                content_td, current_date, sched_time, duration, talks
            )

    return talks


def _parse_qip2015_content_cell(
    content_td, date: str, sched_time: str, duration: int, talks: List[Dict]
) -> None:
    """Extract talks from a QIP 2015 timetable content cell.

    Each talk has a <b>Speaker(s)</b> tag followed by an <i>Title</i> tag.
    Underline <u> inside the speaker tag marks the actual presenter.
    A following <b>(Speaker: X)</b> overrides the presenter (e.g. Gosset sub).
    Slides links contain 'slides' in link text; YouTube links contain 'Watch'.
    """
    all_tags = list(content_td.find_all(['b', 'i', 'a']))
    i_positions = [i for i, el in enumerate(all_tags) if el.name == 'i']

    if not i_positions:
        return

    for seq_idx, i_pos in enumerate(i_positions):
        title = all_tags[i_pos].get_text(strip=True)
        if not title:
            continue

        # Find the speaker <b> immediately preceding this <i>
        speaker_b = None
        for j in range(i_pos - 1, -1, -1):
            el = all_tags[j]
            if el.name == 'b':
                if not re.match(r'^\(Speaker:', el.get_text(strip=True), re.IGNORECASE):
                    speaker_b = el
                break

        if not speaker_b:
            continue

        # Elements between this <i> and the next <i> (or end of cell)
        end_pos = i_positions[seq_idx + 1] if seq_idx + 1 < len(i_positions) else len(all_tags)
        following = all_tags[i_pos + 1: end_pos]

        # Check for alternate presenter: <b>(Speaker: <u>Name</u>)</b>
        alt_presenter = ''
        for el in following:
            if el.name == 'b':
                m = re.match(r'^\(Speaker:\s*(.+)\)', el.get_text(strip=True), re.IGNORECASE)
                if m:
                    u = el.find('u')
                    alt_presenter = u.get_text(strip=True) if u else m.group(1).strip()
                break  # Only check the first <b> after the title

        # Collect arxiv IDs, video URL, slides URL from links
        arxiv_ids_list: List[str] = []
        video_url = ''
        slides_url = ''
        for el in following:
            if el.name != 'a':
                continue
            href = el.get('href', '')
            link_text = el.get_text(strip=True).lower()
            if 'arxiv.org/abs/' in href:
                aid = extract_arxiv_id(href)
                if aid and aid not in arxiv_ids_list:
                    arxiv_ids_list.append(aid)
            elif 'youtube.com' in href or 'youtu.be' in href:
                if not video_url:
                    video_url = href
            elif 'slides' in link_text and not slides_url:
                slides_url = href

        # Parse speaker text (use ' ' separator to preserve spaces around <u> tags)
        speaker_text = re.sub(r'\s+', ' ', speaker_b.get_text(' ', strip=True)).rstrip(':').strip()

        paper_type = 'regular'
        m = re.match(r'^\((Tutorial|Plenary|Public Lecture)\)\s*', speaker_text, re.IGNORECASE)
        if m:
            label = m.group(1).lower()
            if 'public' in label:
                continue  # skip public lectures
            paper_type = label  # 'tutorial' or 'plenary'
            speaker_text = speaker_text[m.end():]

        # Extract award — may be in sibling text after the <b> tag, not inside it
        award = ''
        award_m = re.search(r'\(Recipient of[^)]*\)', speaker_text, re.IGNORECASE)
        if award_m:
            award = 'Best Student Paper'
            speaker_text = speaker_text[:award_m.start()].strip().rstrip(',').strip()
        else:
            # Check text nodes between speaker_b and the <i> title tag
            for sib in speaker_b.next_siblings:
                if hasattr(sib, 'name') and sib.name == 'i':
                    break
                sib_text = sib if isinstance(sib, str) else sib.get_text(' ', strip=True)
                if re.search(r'Best Student Paper', str(sib_text), re.IGNORECASE):
                    award = 'Best Student Paper'
                    break

        # Extract affiliation in parens at end of speaker name
        affiliation = ''
        aff_m = re.search(r',?\s*\(([^)]+)\)\s*$', speaker_text)
        if aff_m and not any(
            x in aff_m.group(1) for x in ('Prize', 'Recipient', 'Nobel', 'Speaker')
        ):
            affiliation = aff_m.group(1).strip()
            speaker_text = speaker_text[:aff_m.start()].strip()

        # Presenter: underlined name in speaker tag, or alternate
        u_tag = speaker_b.find('u')
        presenter = u_tag.get_text(strip=True) if u_tag else ''
        if alt_presenter:
            presenter = alt_presenter

        authors = speaker_text
        speaker = presenter or speaker_text.split(',')[0].split(' and ')[0].strip()

        talks.append(make_talk(
            year='2015',
            paper_type=paper_type,
            title=title,
            speaker=speaker,
            authors=authors,
            affiliations=affiliation,
            arxiv_ids=';'.join(arxiv_ids_list),
            presentation_url=slides_url,
            video_url=video_url,
            award=award,
            scheduled_date=date,
            scheduled_time=sched_time,
            duration_minutes=str(duration) if duration else '',
        ))


def parse_2016() -> List[Dict]:
    """QIP 2016 — accepted-talks.html.
    Triple-nested <ul><ul><ul><li> entries.
    Text: "Author One, Author Two and Author Three. Title of Talk"
    Awards in <span style="color: #0000ff;">.
    Mergers in <em>Merger of:</em>.
    """
    soup = read_html(ARCHIVE_BASE / '2016' / 'accepted-talks.html')
    talks = []

    # Find triple-nested list items
    for li in soup.find_all('li'):
        # Check nesting depth (not reliable) - just process all li with real content
        text = li.get_text(' ', strip=True)
        if not text or len(text) < 10:
            continue

        # Skip navigation items
        if li.find_parent('div', class_=re.compile(r'nav|menu')):
            continue

        # Check for award
        award = ''
        award_span = li.find('span', style=re.compile(r'color.*#0000ff|color.*blue', re.IGNORECASE))
        if award_span:
            award = award_span.get_text(strip=True)
            # Remove from text
            text = text.replace(award, '').strip()

        # Check for merger
        notes = ''
        em_tag = li.find('em')
        if em_tag and 'merger' in em_tag.get_text(strip=True).lower():
            notes = em_tag.get_text(strip=True)
            text = text.replace(em_tag.get_text(strip=True), '').strip()

        # Split authors and title
        # Pattern: "Author One, Author Two and Author Three. Title of Talk"
        # Find the first ". " that comes after what looks like an author list
        # Heuristic: split at first ". " that follows a word (not initials)
        parts = re.split(r'\.\s+', text, maxsplit=1)
        if len(parts) < 2:
            # Try splitting on ". " more aggressively
            m = re.search(r'^(.*?[a-z])\.\s+([A-Z].+)$', text, re.DOTALL)
            if m:
                authors_text = m.group(1)
                title = m.group(2)
            else:
                continue
        else:
            authors_text = parts[0]
            title = parts[1]

        # Clean up
        authors_text = re.sub(r'\s+', ' ', authors_text).strip()
        title = re.sub(r'\s+', ' ', title).strip().rstrip('.')

        if not authors_text or not title:
            continue

        # Parse authors
        author_list = _split_author_list(authors_text)
        speaker = author_list[0] if author_list else ''

        talks.append(make_talk(
            year='2016',
            paper_type='regular',
            title=title,
            speaker=speaker,
            authors=join_authors(author_list),
            award=award,
            notes=notes,
        ))

    return talks


def parse_2019() -> List[Dict]:
    """QIP 2019 — program.html.
    Only invited and tutorial talks (contributed are PDF-only).
    Invited: <h2 id="invited"> -> <ul><li> with day, speaker, affil
    Tutorials: <h2 id="tutorials"> -> <ul><li> with day, speaker, title
    """
    soup = read_html(ARCHIVE_BASE / '2019' / 'program.html')
    talks = []

    day_dates = {
        'monday, jan 14': '2019-01-14',
        'tuesday, jan 15': '2019-01-15',
        'wednesday, jan 16': '2019-01-16',
        'thursday, jan 17': '2019-01-17',
        'friday, jan 18': '2019-01-18',
        'saturday, jan 12': '2019-01-12',
        'sunday, jan 13': '2019-01-13',
    }

    def get_date_from_text(text):
        for pattern, date in day_dates.items():
            if pattern in text.lower():
                return date
        return ''

    # Invited talks section
    invited_h = soup.find('h2', id='invited')
    if invited_h:
        ul = invited_h.find_next_sibling('ul')
        if ul:
            for li in ul.find_all('li', recursive=False):
                text = li.get_text(' ', strip=True)
                # Format: "Monday, Jan 14: Speaker Name (Affiliation)"
                m = re.match(
                    r'^(?:<[^>]+>)?([^:]+):\s*(.+?)(?:\s*\(([^)]+)\))?\s*$',
                    li.get_text(' ', strip=True)
                )
                day_text = ''
                speaker = ''
                affil = ''

                # Try span[font-weight:bold] for day
                day_span = li.find('span', style=re.compile(r'font-weight.*bold', re.IGNORECASE))
                if day_span:
                    day_text = day_span.get_text(strip=True).rstrip(':')
                    rest = text[len(day_span.get_text(strip=True)):].strip().lstrip(':').strip()
                    # "Speaker (Affil)"
                    aff_m = re.match(r'^(.*?)\s*\(([^)]+)\)\s*$', rest)
                    if aff_m:
                        speaker = aff_m.group(1).strip()
                        affil = aff_m.group(2).strip()
                    else:
                        speaker = rest
                else:
                    # Fallback: split on ':'
                    if ':' in text:
                        day_text, rest = text.split(':', 1)
                        rest = rest.strip()
                        aff_m = re.match(r'^(.*?)\s*\(([^)]+)\)\s*$', rest)
                        if aff_m:
                            speaker = aff_m.group(1).strip()
                            affil = aff_m.group(2).strip()
                        else:
                            speaker = rest
                    else:
                        speaker = text

                date = get_date_from_text(day_text)

                talks.append(make_talk(
                    year='2019',
                    paper_type='invited',
                    title='',  # No title available in HTML
                    speaker=speaker,
                    authors=speaker,
                    affiliations=affil,
                    scheduled_date=date,
                    notes='Invited talk; title not available in program HTML',
                ))

    # Tutorial talks section
    tutorials_h = soup.find('h2', id='tutorials')
    if tutorials_h:
        ul = tutorials_h.find_next_sibling('ul')
        if ul:
            for li in ul.find_all('li', recursive=False):
                text = li.get_text(' ', strip=True)

                # Title in <span class="title">
                title_span = li.find('span', class_='title')
                title = title_span.get_text(strip=True) if title_span else ''

                # Day in bold span
                day_span = li.find('span', style=re.compile(r'font-weight.*bold', re.IGNORECASE))
                day_text = day_span.get_text(strip=True).rstrip(':') if day_span else ''
                date = get_date_from_text(day_text)

                # Speaker: text between day and title/affil
                if day_span:
                    after_day = text[len(day_span.get_text(strip=True)):].strip().lstrip(':').strip()
                else:
                    after_day = text

                if title:
                    after_day = after_day.replace(title, '').strip().rstrip(',').strip()

                # Remove slide links text
                after_day = re.sub(r'slides?\s*\(.*?\)', '', after_day, flags=re.IGNORECASE).strip()

                # after_day should now be "Speaker Name (Affil)"
                aff_m = re.match(r'^(.*?)\s*\(([^)]+)\)\s*$', after_day)
                if aff_m:
                    speaker = aff_m.group(1).strip().rstrip(',')
                    affil = aff_m.group(2).strip()
                else:
                    speaker = after_day.rstrip(',').strip()
                    affil = ''

                # Presentation URL from links
                pres_url = ''
                for a in li.find_all('a', href=True):
                    href = a['href']
                    if href.endswith('.pdf') or 'slides' in a.get_text(strip=True).lower():
                        pres_url = href
                        break

                talks.append(make_talk(
                    year='2019',
                    paper_type='tutorial',
                    title=title,
                    speaker=speaker,
                    authors=speaker,
                    affiliations=affil,
                    presentation_url=pres_url,
                    scheduled_date=date,
                ))

    # Note about contributed talks
    if not talks:
        talks.append(make_talk(
            year='2019',
            paper_type='regular',
            notes='see qip2019_talk_schedule.pdf',
        ))

    return talks


# ============================================================
# QIP 2021 — MCQST static day pages (monday.html ... friday.html + tutorials)
# ============================================================

_QIP2021_DAY_DATES = {
    'monday':    '2021-02-01',
    'tuesday':   '2021-02-02',
    'wednesday': '2021-02-03',
    'thursday':  '2021-02-04',
    'friday':    '2021-02-05',
}

_QIP2021_TUTORIAL_DATES = {
    'tutorials_saturday': '2021-01-30',
    'tutorials_sunday':   '2021-01-31',
}

# Phrases in the title that mark a non-talk slot we want to skip
_QIP2021_SKIP_KEYWORDS = (
    'welcome', 'round table', 'round tables', 'breakfast club', 'lunch',
    'break', 'mentoring', 'mentor', 'lab tour', 'panel discussion',
    'industry session', 'industry exhibition', 'poster session',
    'town hall', 'business meeting', 'social', 'networking',
    'opening', 'closing', 'qip tv', 'coffee', 'reception',
)


def _qip2021_split_authors(authors_text: str) -> Tuple[List[str], int]:
    """Split a 2021 'Authors:' string into a list of names.

    Returns (authors, presenter_index). presenter_index is the index of the
    underlined name (presenter) or -1 if none.
    Strips parallel-session '//' separators (caller handles those upstream).
    """
    text = authors_text.strip().rstrip('.')
    # Replace ' and ' with comma so we can split uniformly
    text = re.sub(r'\s+and\s+', ', ', text)
    parts = [p.strip() for p in text.split(',') if p.strip()]
    return parts, -1  # presenter detected separately by caller via <u> tag


def _qip2021_extract_authors(authors_p) -> Tuple[str, str]:
    """Given the <p>Authors: ...</p> tag, return (joined_authors, presenter).

    Presenter is the name found inside a <u> tag, if any.
    Authors with '//' (parallel sessions) are kept joined with a ' // ' marker
    so downstream consumers can split them later.
    """
    presenter = ''
    u_tag = authors_p.find('u')
    if u_tag:
        presenter = u_tag.get_text(' ', strip=True)

    text = authors_p.get_text(' ', strip=True)
    # Strip leading "Authors:" label
    text = re.sub(r'^Authors\s*:\s*', '', text, flags=re.IGNORECASE)

    # If parallel sessions present, keep '//' as a separator in the output.
    if '//' in text:
        chunks = [c.strip() for c in text.split('//')]
        all_names = []
        for chunk in chunks:
            names, _ = _qip2021_split_authors(chunk)
            all_names.append(';'.join(names))
        return ' // '.join(all_names), presenter

    names, _ = _qip2021_split_authors(text)
    return ';'.join(names), presenter


_QIP2021_TIME_HEADER_RE = re.compile(
    r'^\s*(\d{1,2}[:.]\d{2})\s*[-–]\s*(\d{1,2}[:.]\d{2})'
)


def _qip2021_is_talk_header(p) -> Tuple[bool, str, str]:
    """Test whether <p> is a talk header. Returns (is_header, time_text, title).

    Two header formats:
      A) <p>...<h5>TIME-TIME | <b>TITLE</b></h5></p>      (morning plenaries)
      B) <p>TIME-TIME<br><b>TITLE</b></p>                  (afternoon parallels)
    """
    h5 = p.find('h5')
    if h5 is not None:
        h5_text = h5.get_text(' ', strip=True)
        b = h5.find('b')
        if b:
            title = b.get_text(' ', strip=True)
            idx = h5_text.find(title)
            time_text = h5_text[:idx] if idx >= 0 else h5_text
            return True, time_text, title
        # h5 with no <b>: title may follow ' | '
        if '|' in h5_text:
            time_text, title = [s.strip() for s in h5_text.split('|', 1)]
            return True, time_text, title
        return False, '', ''

    text = p.get_text(' ', strip=True)
    if not _QIP2021_TIME_HEADER_RE.match(text):
        return False, '', ''
    b = p.find('b')
    if b is None:
        return False, '', ''
    btext = b.get_text(' ', strip=True)
    if not btext or _QIP2021_TIME_HEADER_RE.match(btext):
        return False, '', ''
    # Time is the part of the <p> text before the title
    idx = text.find(btext)
    time_text = text[:idx] if idx >= 0 else text
    return True, time_text, btext


def _qip2021_parse_day(file_path: Path, date: str, paper_type_default: str) -> List[Dict]:
    """Parse a single QIP 2021 day file and return list of talk dicts."""
    if not file_path.exists():
        return []
    soup = read_html(file_path)
    talks: List[Dict] = []

    # Walk all <p> tags in document order; classify each as header or metadata.
    all_ps = soup.find_all('p')
    headers: List[Tuple[int, str, str]] = []  # (index, time_text, title)
    for i, p in enumerate(all_ps):
        is_h, time_text, title = _qip2021_is_talk_header(p)
        if is_h:
            headers.append((i, time_text, title))

    for n, (idx, time_text, title) in enumerate(headers):
        end_idx = headers[n + 1][0] if n + 1 < len(headers) else len(all_ps)
        block_ps = all_ps[idx + 1:end_idx]

        title_lower = title.lower()
        if any(kw in title_lower for kw in _QIP2021_SKIP_KEYWORDS):
            continue

        scheduled_time, duration = parse_time_range(time_text)

        speaker = ''
        authors = ''
        presenter = ''
        affiliations = ''
        abstract_parts: List[str] = []
        in_abstract = False

        for p in block_ps:
            ptext = p.get_text(' ', strip=True)
            if not ptext:
                continue
            low = ptext.lower()

            if low.startswith('speaker'):
                speaker = re.sub(r'^speakers?\s*:\s*', '', ptext, flags=re.IGNORECASE).strip()
                in_abstract = False
                continue
            if low.startswith('authors'):
                authors, presenter = _qip2021_extract_authors(p)
                in_abstract = False
                continue
            if low.startswith('affiliations') or low.startswith('affiliation'):
                affiliations = re.sub(
                    r'^affiliations?\s*:\s*', '', ptext, flags=re.IGNORECASE
                ).strip()
                in_abstract = False
                continue

            b_first = p.find('b')
            if b_first and b_first.get_text(strip=True).lower() == 'abstract':
                in_abstract = True
                rest_parts = []
                seen_label = False
                for child in p.descendants:
                    if (hasattr(child, 'name') and child.name == 'b'
                            and child.get_text(strip=True).lower() == 'abstract'):
                        seen_label = True
                        continue
                    if seen_label and getattr(child, 'name', None) is None:
                        rest_parts.append(str(child))
                tail = re.sub(r'\s+', ' ', ' '.join(rest_parts)).strip()
                if tail:
                    abstract_parts.append(tail)
                continue

            if in_abstract:
                abstract_parts.append(ptext)

        if not speaker and authors:
            speaker = presenter or authors.split(';')[0].split(' // ')[0].strip()

        # Skip headers with neither speaker nor authors (likely a session-break
        # row that snuck past the keyword filter).
        if not speaker and not authors:
            continue

        ptype = paper_type_default
        if not authors and speaker:
            ptype = 'invited'
        # 60-minute or longer slots in the morning are typically invited plenaries
        if duration >= 45 and ptype == 'regular':
            ptype = 'invited'

        notes = ''
        if authors and ' // ' in authors:
            notes = 'parallel session: multiple papers presented in same slot'

        abstract = re.sub(r'\s+', ' ', ' '.join(abstract_parts)).strip()

        talks.append(make_talk(
            year='2021',
            paper_type=ptype,
            title=title,
            speaker=speaker,
            authors=authors or speaker,
            affiliations=affiliations,
            abstract=abstract,
            scheduled_date=date,
            scheduled_time=scheduled_time,
            duration_minutes=str(duration) if duration > 0 else '',
            notes=notes,
        ))

    return talks


def _qip2021_parse_tutorials() -> List[Dict]:
    """Parse QIP 2021 tutorials/index.html."""
    path = ARCHIVE_BASE / '2021' / 'qip2021' / 'program' / 'tutorials' / 'index.html'
    if not path.exists():
        return []
    soup = read_html(path)
    talks: List[Dict] = []

    # Tutorial blocks: anchored by <a id="tutorials_saturday"> / <a id="tutorials_sunday">
    # Each tutorial has <h4 class="section-title">Speaker Name</h4>, then
    # <h3><a href="...">Title</a></h3>, then accordion body with affiliation/abstract.
    current_date = ''
    for el in soup.find_all(['a', 'h4', 'h3', 'div']):
        if el.name == 'a' and el.get('id', '') in _QIP2021_TUTORIAL_DATES:
            current_date = _QIP2021_TUTORIAL_DATES[el['id']]
            continue
        if el.name == 'h4' and 'section-title' in (el.get('class') or []):
            speaker = el.get_text(' ', strip=True)
            # Day-section h4 headings look like "Saturday, January 30th - Main stage (A)";
            # skip those so we only pick up speaker-name h4s.
            if re.search(r'(monday|tuesday|wednesday|thursday|friday|saturday|sunday)',
                         speaker, re.IGNORECASE):
                continue
            # Walk forward to find the matching h3 (title) and accordion body
            title = ''
            abstract = ''
            affiliation = ''
            walker = el
            for _ in range(40):
                walker = walker.find_next(['h3', 'div'])
                if walker is None:
                    break
                if walker.name == 'h3':
                    a = walker.find('a')
                    title = (a.get_text(' ', strip=True) if a else
                             walker.get_text(' ', strip=True))
                    continue
                if walker.name == 'div' and 'accordion-body' in (walker.get('class') or []):
                    paragraphs = walker.find_all('p')
                    parts = []
                    for p in paragraphs:
                        ptext = p.get_text(' ', strip=True)
                        if ptext.lower().startswith('affiliation'):
                            affiliation = re.sub(
                                r'^affiliations?\s*:\s*', '', ptext, flags=re.IGNORECASE
                            ).strip()
                        else:
                            parts.append(ptext)
                    abstract = re.sub(r'\s+', ' ', ' '.join(parts)).strip()
                    break

            if not speaker or not title:
                continue
            talks.append(make_talk(
                year='2021',
                paper_type='tutorial',
                title=title,
                speaker=speaker,
                authors=speaker,
                affiliations=affiliation,
                abstract=abstract,
                scheduled_date=current_date,
            ))

    return talks


def parse_2021() -> List[Dict]:
    """QIP 2021 — static day pages (Mon–Fri) plus tutorials.

    Each day file has talks in the format:
        <h5>TIME-TIME | <b>TITLE</b></h5>
        <p>Speaker: Name</p>            (sometimes)
        <p>Authors: A, <u>Presenter</u>, B [// parallel-session authors]</p>
        <p><i>Affiliations: Aff1 | Aff2 | ...</i></p>
        <p><b>Abstract</b><br>Body...</p>
    Non-talk slots (Welcome, Round tables, Mentoring, Breakfast Club, etc.)
    are filtered out by keyword.
    """
    base = ARCHIVE_BASE / '2021' / 'qip2021' / 'program'
    talks: List[Dict] = []

    # Tutorials (paper_type = tutorial)
    talks.extend(_qip2021_parse_tutorials())

    # Each day file
    for day, date in _QIP2021_DAY_DATES.items():
        talks.extend(_qip2021_parse_day(base / f'{day}.html', date, 'regular'))

    return talks


# ============================================================
# QIP 2023 — Indico static accepted-talks page
# ============================================================


def parse_2023() -> List[Dict]:
    """QIP 2023 — static accepted-talks editor-output div.

    The page (3889-accepted-talks.html) contains <div class="editor-output">
    with three <h3> sections: PLENARY TALKS, SHORT PLENARY TALKS, REGULAR TALKS.
    Each <li> has the form:
        Author1, Author2 and Author3. <a href="VIDEO_URL">Title</a>
    Some entries are merged (two papers in one slot) and use:
        Authors. <a>Title</a><br><i>merged with</i><br>Authors2. <a>Title2</a>
    """
    path = ARCHIVE_BASE / '2023' / 'event' / '13076' / 'page' / '3889-accepted-talks.html'
    soup = read_html(path)
    talks: List[Dict] = []

    container = soup.find('div', class_='editor-output')
    if container is None:
        return talks

    # Map h3 section names to paper types
    section_to_type = {
        'plenary talks':       'plenary_long',
        'short plenary talks': 'plenary_short',
        'regular talks':       'regular',
    }

    current_type = 'regular'
    for el in container.children:
        name = getattr(el, 'name', None)
        if name == 'h3':
            heading = el.get_text(' ', strip=True).lower()
            current_type = section_to_type.get(heading, 'regular')
            continue
        if name != 'ul':
            continue

        for li in el.find_all('li', recursive=False):
            # Detect "merged with" entries by splitting on the <i>merged with</i>.
            html = li.decode_contents()
            chunks = re.split(r'<br\s*/?>\s*<i>\s*merged with\s*</i>\s*<br\s*/?>',
                              html, flags=re.IGNORECASE)
            merged = len(chunks) > 1

            for chunk in chunks:
                sub = BeautifulSoup(chunk, 'html.parser')
                text = sub.get_text(' ', strip=True)
                if not text:
                    continue

                # Extract video URL (first <a href> that points to youtube/youtu.be)
                video_url = ''
                for a in sub.find_all('a', href=True):
                    href = a['href']
                    if 'youtu' in href.lower() or 'youtube' in href.lower():
                        video_url = href
                        break

                # Title is the first <a> link text (or remainder after author block).
                title = ''
                a = sub.find('a')
                if a:
                    title = a.get_text(' ', strip=True)

                # Authors: text before the title in the chunk.
                if title and title in text:
                    authors_text = text.split(title, 1)[0].strip()
                    remainder = text.split(title, 1)[1].strip()
                else:
                    # No <a>: split at last sentence-ending period before title-like text
                    m = re.match(r'^(.*?\.)\s+(.+)$', text)
                    if m:
                        authors_text, title = m.group(1), m.group(2)
                        remainder = ''
                    else:
                        continue

                authors_text = authors_text.rstrip('.').strip()
                authors = _split_author_list(authors_text)
                if not authors or not title:
                    continue

                speaker = authors[0]
                notes = 'merged talks slot' if merged else ''
                # If the title lacked an <a>, fall back to remainder for arxiv detection
                arxiv_ids = extract_arxiv_ids_from_tag(sub)

                talks.append(make_talk(
                    year='2023',
                    paper_type=current_type,
                    title=title,
                    speaker=speaker,
                    authors=join_authors(authors),
                    video_url=video_url,
                    arxiv_ids=arxiv_ids,
                    notes=notes,
                ))

    return talks


# ============================================================
# QIP 2024 — ASP.NET static pages (pid=259 talks, pid=264 plenary, pid=262 tutorial)
# ============================================================


def _qip2024_inner_body(path: Path) -> Optional[BeautifulSoup]:
    """Extract the inner <body>...</body> content from a QIP 2024 ASP.NET page.

    Each page wraps a nested <!DOCTYPE html><body>...</body></html> inside the
    main content div. Returns a BeautifulSoup of that inner body, or None.
    """
    if not path.exists():
        return None
    soup = read_html(path)
    container = soup.find('div', id='ctl00_ContentPlaceHolder1_mypage_left')
    if container is None:
        return None
    inner_html = str(container)
    m = re.search(r'<body>(.*?)</body>', inner_html, re.DOTALL | re.IGNORECASE)
    if not m:
        return None
    return BeautifulSoup(m.group(1), 'html.parser')


_QIP2024_DATE_MAP = {
    'jan. 13': '2024-01-13', 'jan. 14': '2024-01-14',
    'jan. 15': '2024-01-15', 'jan. 16': '2024-01-16',
    'jan. 17': '2024-01-17', 'jan. 18': '2024-01-18',
    'jan. 19': '2024-01-19',
}


def _qip2024_normalize_date(text: str) -> str:
    low = text.lower().replace('\xa0', ' ')
    for prefix, iso in _QIP2024_DATE_MAP.items():
        if prefix in low:
            return iso
    return ''


def _qip2024_parse_accepted(base: Path) -> List[Dict]:
    """pid=259 — list of accepted regular talks (authors + title only)."""
    inner = _qip2024_inner_body(base / 'mypage.aspx?pid=259&lang=en&sid=1522.html')
    if inner is None:
        return []
    talks: List[Dict] = []
    for li in inner.find_all('li'):
        text = li.get_text(' ', strip=True)
        if not text or len(text) < 10:
            continue
        # Title is the colored span (#2e628c)
        title_span = li.find('span', style=re.compile(r'color\s*:\s*#2e628c', re.IGNORECASE))
        if title_span is None:
            continue
        title = title_span.get_text(' ', strip=True)
        if title in text:
            authors_text = text.split(title, 1)[0].strip().rstrip('.').strip()
        else:
            continue
        authors = _split_author_list(authors_text)
        if not authors or not title:
            continue
        talks.append(make_talk(
            year='2024',
            paper_type='regular',
            title=title,
            speaker=authors[0],
            authors=join_authors(authors),
        ))
    return talks


def _qip2024_parse_plenary(base: Path) -> List[Dict]:
    """pid=264 — three tables: Invited Plenary, Long Plenary, Short Plenary.

    Columns: Date, Time, No., Title, Speaker/Authors.
    """
    inner = _qip2024_inner_body(base / 'mypage.aspx?pid=264&lang=en&sid=1522.html')
    if inner is None:
        return []
    talks: List[Dict] = []

    # Walk all top-level elements; track section heading text to assign type.
    current_type = 'plenary'
    for el in inner.descendants:
        if not hasattr(el, 'name') or el.name is None:
            continue
        if el.name == 'p':
            heading_text = el.get_text(' ', strip=True).lower()
            if 'invited plenary' in heading_text:
                current_type = 'invited'
            elif 'long plenary' in heading_text:
                current_type = 'plenary_long'
            elif 'short plenary' in heading_text:
                current_type = 'plenary_short'
        elif el.name == 'table':
            # Decide type from the table's header row if available
            rows = el.find_all('tr')
            if not rows:
                continue
            # First row = header; subsequent rows = talks
            for tr in rows[1:]:
                cells = [td.get_text(' ', strip=True).replace('\xa0', ' ').strip()
                         for td in tr.find_all('td')]
                if len(cells) < 5:
                    continue
                date_text, time_text, _no, title, authors_text = cells[:5]
                if not title:
                    continue
                date_iso = _qip2024_normalize_date(date_text)
                start_time, duration = parse_time_range(time_text)
                authors = _split_author_list(authors_text)
                speaker = authors[0] if authors else authors_text.strip()
                notes = ''
                if 'cancel' in title.lower():
                    notes = 'talk canceled'
                    title = re.sub(r'\s*\(talk canceled\)\s*', '', title,
                                   flags=re.IGNORECASE).strip()
                talks.append(make_talk(
                    year='2024',
                    paper_type=current_type,
                    title=title,
                    speaker=speaker,
                    authors=join_authors(authors) if authors else speaker,
                    scheduled_date=date_iso,
                    scheduled_time=start_time,
                    duration_minutes=str(duration) if duration > 0 else '',
                    notes=notes,
                ))
    return talks


def _qip2024_parse_tutorials(base: Path) -> List[Dict]:
    """pid=262 — tutorial grid (5 time slots × 2 days).

    The same tutorial appears twice (morning + afternoon halves of the same day);
    we deduplicate on (date, title, speaker).
    """
    inner = _qip2024_inner_body(base / 'mypage.aspx?pid=262&lang=en&sid=1522.html')
    if inner is None:
        return []
    talks: List[Dict] = []
    seen = set()

    for table in inner.find_all('table'):
        rows = table.find_all('tr')
        if not rows:
            continue
        # Header row gives the column → date mapping
        header_cells = [td.get_text(' ', strip=True).replace('\xa0', ' ').strip()
                        for td in rows[0].find_all(['td', 'th'])]
        col_dates: Dict[int, str] = {}
        for i, cell in enumerate(header_cells):
            iso = _qip2024_normalize_date(cell)
            if iso:
                col_dates[i] = iso
        if not col_dates:
            continue

        for tr in rows[1:]:
            cells = tr.find_all('td')
            # Skip rows that don't have enough columns
            if len(cells) < 2:
                continue
            # Account for rowspan continuations from a previous row: if this
            # row has fewer cells than the header, the leading time cells were
            # carried over and the first td actually corresponds to a later
            # column. Shift cell indices accordingly.
            offset = max(0, len(header_cells) - len(cells))
            for i, td in enumerate(cells):
                col = i + offset
                if col not in col_dates:
                    continue
                # Extract structured text: tutorial cells contain
                # <p>Title</p><p>Speaker</p>. Look for two distinct <p> blocks.
                paragraphs = [p.get_text(' ', strip=True) for p in td.find_all('p')]
                paragraphs = [p for p in paragraphs if p]
                # Skip empty / break / registration cells
                if not paragraphs:
                    continue
                joined = ' '.join(paragraphs).lower()
                if any(skip in joined for skip in
                       ('break', 'registration', 'lunch', 'reception',
                        'poster display', '(1f', '(4f')):
                    continue
                if len(paragraphs) < 2:
                    continue
                title, speaker = paragraphs[0], paragraphs[1]
                key = (col_dates[col], title, speaker)
                if key in seen:
                    continue
                seen.add(key)
                talks.append(make_talk(
                    year='2024',
                    paper_type='tutorial',
                    title=title,
                    speaker=speaker,
                    authors=speaker,
                    scheduled_date=col_dates[col],
                ))
    return talks


def parse_2024() -> List[Dict]:
    """QIP 2024 — Taipei ASP.NET archive.

    - pid=259: full list of accepted regular talks (authors + title)
    - pid=264: invited / long plenary / short plenary tables (date, time, title)
    - pid=262: tutorials grid (date, title, speaker)
    """
    base = ARCHIVE_BASE / '2024' / 'site'
    talks: List[Dict] = []
    talks.extend(_qip2024_parse_tutorials(base))
    talks.extend(_qip2024_parse_plenary(base))
    talks.extend(_qip2024_parse_accepted(base))
    return talks


# ============================================================
# Dispatch table
# ============================================================

PARSERS = {
    2002: parse_2002,
    2004: parse_2004_v2,
    2006: parse_2006,
    2007: parse_2007,
    2008: parse_2008,
    2009: parse_2009,
    2010: parse_2010,
    2011: parse_2011,
    2012: parse_2012,
    2013: parse_2013,
    2014: parse_2014,
    2015: parse_2015,
    2016: parse_2016,
    2019: parse_2019,
    2021: parse_2021,
    2023: parse_2023,
    2024: parse_2024,
}


def main():
    parser = argparse.ArgumentParser(description='Scrape QIP historical talk data')
    parser.add_argument('--year', type=int, help='Specific year to scrape')
    parser.add_argument('--all', action='store_true', help='Scrape all available years')
    parser.add_argument('--output-dir', type=Path, default=OUTPUT_DIR, help='Output directory')
    args = parser.parse_args()

    if not args.year and not args.all:
        parser.error('Specify --year YEAR or --all')

    years = list(PARSERS.keys()) if args.all else [args.year]

    for year in years:
        if year not in PARSERS:
            print(f'No parser for year {year}. Available: {sorted(PARSERS.keys())}',
                  file=sys.stderr)
            continue
        print(f'Parsing QIP {year}...')
        try:
            talks = PARSERS[year]()
            if talks:
                save_csv(talks, year, args.output_dir)
            else:
                print(f'  Warning: no talks found for {year}')
        except FileNotFoundError as e:
            print(f'  Error: file not found: {e}', file=sys.stderr)
        except Exception as e:
            import traceback
            print(f'  Error parsing {year}: {e}', file=sys.stderr)
            traceback.print_exc()


if __name__ == '__main__':
    main()
