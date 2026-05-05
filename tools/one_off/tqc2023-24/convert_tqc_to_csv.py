#!/usr/bin/env python3
"""
Convert TQC 2023-24 BibTeX talks and calendar schedules to CSV format.

This unified script:
1. Extracts talks from BibTeX file
2. Downloads and parses Google Calendar schedule
3. Merges schedule information with talks
4. Outputs CSV files ready for import

Usage:
    python3 convert_tqc_to_csv.py
"""

import re
import csv
import sys
import urllib.request
from datetime import datetime
from typing import Dict, List, Optional
from pathlib import Path

try:
    from icalendar import Calendar
except ImportError:
    print("Error: icalendar library not found. Install with: pip3 install icalendar")
    sys.exit(1)


# =============================================================================
# BibTeX Parsing Functions
# =============================================================================

def extract_arxiv_id(url: str) -> Optional[str]:
    """Extract arXiv ID from URL if present."""
    if not url:
        return None

    # Match arxiv.org/abs/XXXX.XXXXX
    match = re.search(r'arxiv\.org/abs/(\d+\.\d+)', url)
    if match:
        return match.group(1)

    # Old-style arXiv IDs
    match = re.search(r'arxiv\.org/abs/([a-z-]+/\d+)', url)
    if match:
        return match.group(1)

    return None


def parse_authors(author_string: str) -> List[str]:
    """Parse author string into list of individual authors."""
    if not author_string:
        return []

    # Split by " and " (BibTeX author separator)
    authors = [a.strip() for a in author_string.split(' and ')]
    return authors


def clean_latex(text: str) -> str:
    """Remove common LaTeX commands and clean up text."""
    if not text:
        return text

    # Remove common LaTeX math delimiters
    text = re.sub(r'\$([^\$]+)\$', r'\1', text)

    # Remove common LaTeX commands but keep content
    text = re.sub(r'\\emph\{([^}]+)\}', r'\1', text)
    text = re.sub(r'\\textbf\{([^}]+)\}', r'\1', text)
    text = re.sub(r'\\textit\{([^}]+)\}', r'\1', text)

    # Remove backslash from common symbols
    text = text.replace('\\leq', '≤')
    text = text.replace('\\geq', '≥')
    text = text.replace('\\cdot', '·')
    text = text.replace('\\circ', '∘')
    text = text.replace('\\times', '×')

    # Remove remaining single backslashes before symbols
    text = re.sub(r'\\([^a-zA-Z])', r'\1', text)

    return text


def parse_bibtex_file(filepath: str) -> List[Dict[str, str]]:
    """Parse BibTeX file and extract Talk, Conference, and Workshop entries."""

    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    entries = []

    # Process @Talk, @Conference, and @Workshop entry types
    for entry_type in ['@Talk{', '@Conference{', '@Workshop{']:
        current_pos = 0

        while True:
            # Find next entry of this type
            entry_start = content.find(entry_type, current_pos)
            if entry_start == -1:
                break

            # Find the entry ID
            id_start = entry_start + len(entry_type)
            id_end = content.find(',', id_start)
            entry_id = content[id_start:id_end].strip()

            # Find the closing brace - count braces to handle nesting
            brace_count = 1
            i = id_end + 1
            while i < len(content) and brace_count > 0:
                if content[i] == '{':
                    brace_count += 1
                elif content[i] == '}':
                    brace_count -= 1
                i += 1

            entry_end = i
            entry_content = content[id_end + 1:entry_end - 1]

            # Extract fields from entry
            fields = {
                'entry_id': entry_id,
                'entry_type': entry_type.strip('@{')
            }

            # Helper function to extract a field value
            def extract_field(field_name):
                pattern = rf'{field_name}\s*=\s*{{([^}}]*(?:{{[^}}]*}}[^}}]*)*)}}'
                match = re.search(pattern, entry_content, re.DOTALL)
                if match:
                    value = match.group(1).strip()
                    value = re.sub(r'\s+', ' ', value)
                    return value
                return None

            fields['title'] = extract_field('title')
            fields['author'] = extract_field('author')
            fields['year'] = extract_field('year')
            fields['url'] = extract_field('url')
            fields['abstract'] = extract_field('abstract')
            fields['keywords'] = extract_field('keywords')
            fields['howpublished'] = extract_field('howpublished')

            entries.append(fields)
            current_pos = entry_end

    return entries


def process_bibtex_entries(entries: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """Process raw BibTeX entries into CSV-ready format."""

    talks = []
    for entry in entries:
        # Skip if missing essential fields
        if not entry.get('title') or not entry.get('author') or not entry.get('year'):
            print(f"Warning: Skipping entry {entry.get('entry_id', 'unknown')} due to missing fields",
                  file=sys.stderr)
            continue

        # Extract arXiv ID if URL is present
        arxiv_id = extract_arxiv_id(entry.get('url', '')) if entry.get('url') else None

        # Parse authors
        authors_list = parse_authors(entry.get('author', ''))

        # Clean LaTeX formatting
        title = clean_latex(entry.get('title', ''))
        abstract = clean_latex(entry.get('abstract', '')) if entry.get('abstract') else ''

        # Determine paper_type and notes
        entry_type = entry.get('entry_type', '')
        paper_type = 'regular'

        notes = f"BibTeX entry type: {entry_type}"
        if entry_type == 'Conference':
            notes += " (proceedings track - published in LIPIcs)"
        elif entry_type == 'Workshop':
            notes += " (workshop track)"

        talks.append({
            'venue': 'TQC',
            'year': entry.get('year', ''),
            'paper_type': paper_type,
            'title': title,
            'speakers': '; '.join(authors_list),
            'authors': '; '.join(authors_list),
            'affiliations': '',
            'arxiv_ids': arxiv_id or '',
            'session_name': entry.get('keywords', ''),
            'scheduled_date': '',
            'scheduled_time': '',
            'duration_minutes': '',
            'presentation_url': '',
            'video_url': '',
            'youtube_id': '',
            'award': '',
            'notes': notes,
            '_entry_id': entry.get('entry_id', ''),
            '_entry_type': entry_type,
            '_url': entry.get('url', ''),
            '_howpublished': entry.get('howpublished', ''),
            'abstract': abstract,
        })

    return talks


# =============================================================================
# ICS Calendar Parsing Functions
# =============================================================================

def extract_speaker_from_summary(summary: str) -> Optional[str]:
    """Extract speaker name from calendar summary."""

    # TQC 2023 format: "A) Speaker Name - Title"
    match = re.match(r'^[A-Z]\)\s*([^-|]+?)\s*-', summary)
    if match:
        return match.group(1).strip()

    # TQC 2024 format: "A: Title | Speaker1, Speaker2, ..."
    # or "Track: Title | Speaker1, Speaker2, ..."
    match = re.match(r'^[A-Z]:\s*[^|]+\|\s*([^,]+)', summary)
    if match:
        # Extract first speaker name before comma
        return match.group(1).strip()

    # Generic format: "Name - Title"
    match = re.match(r'^([^-|]+?)\s*[-|]', summary)
    if match:
        name = match.group(1).strip()
        # Check if it looks like a name (not too long, not a track letter)
        if len(name.split()) <= 5 and not re.match(r'^[A-Z][:\)]', name):
            return name

    return None


def parse_ics_calendar(filepath: str, year: int) -> List[Dict]:
    """Parse ICS calendar file for specific year."""

    with open(filepath, 'rb') as f:
        cal = Calendar.from_ical(f.read())

    events = []

    for component in cal.walk():
        if component.name != "VEVENT":
            continue

        # Get start time
        dtstart = component.get('dtstart')
        if not dtstart:
            continue

        dt = dtstart.dt

        # Handle both datetime and date objects
        if isinstance(dt, datetime):
            # Convert timezone-aware datetime to naive datetime
            # The calendar stores times in the event's local timezone or UTC
            # We want to preserve the displayed time (what attendees would see)
            if dt.tzinfo is not None:
                from datetime import timezone

                # Convert UTC to local conference time if needed
                # TQC 2023 was in Lisbon (UTC+1), TQC 2024 was in Okinawa (UTC+9)
                if dt.tzinfo == timezone.utc or dt.utcoffset() == timezone.utc.utcoffset(None):
                    # UTC time - need to convert to local conference time
                    if year == 2023:
                        # TQC 2023: Lisbon (UTC+1 in summer)
                        import datetime as dt_module
                        offset = dt_module.timedelta(hours=1)
                        dt_local = dt.replace(tzinfo=None) + offset
                    elif year == 2024:
                        # TQC 2024: Okinawa (UTC+9)
                        import datetime as dt_module
                        offset = dt_module.timedelta(hours=9)
                        dt_local = dt.replace(tzinfo=None) + offset
                    else:
                        dt_local = dt.replace(tzinfo=None)
                else:
                    # Already in local time, just remove timezone
                    dt_local = dt.replace(tzinfo=None)
            else:
                dt_local = dt

            event_year = dt_local.year
            date_str = dt_local.strftime('%Y-%m-%d')
            time_str = dt_local.strftime('%H:%M:%S')
            dt_obj = dt_local
        else:
            event_year = dt.year
            date_str = dt.isoformat()
            time_str = ''
            dt_obj = datetime.combine(dt, datetime.min.time())

        # Filter by year
        if event_year != year:
            continue

        event = {
            'datetime': dt_obj,
            'date': date_str,
            'time': time_str,
            'duration_minutes': '',  # Will be filled if dtend is available
        }

        # Get end time and calculate duration
        dtend = component.get('dtend')
        if dtend and isinstance(dt, datetime) and isinstance(dtend.dt, datetime):
            # Both start and end are datetime objects
            dt_end = dtend.dt

            # Convert end time to local time using same offset as start
            if dt_end.tzinfo is not None:
                from datetime import timezone
                if dt_end.tzinfo == timezone.utc or dt_end.utcoffset() == timezone.utc.utcoffset(None):
                    if year == 2023:
                        import datetime as dt_module
                        offset = dt_module.timedelta(hours=1)
                        dt_end_local = dt_end.replace(tzinfo=None) + offset
                    elif year == 2024:
                        import datetime as dt_module
                        offset = dt_module.timedelta(hours=9)
                        dt_end_local = dt_end.replace(tzinfo=None) + offset
                    else:
                        dt_end_local = dt_end.replace(tzinfo=None)
                else:
                    dt_end_local = dt_end.replace(tzinfo=None)
            else:
                dt_end_local = dt_end

            # Calculate duration in minutes
            duration = (dt_end_local - dt_local).total_seconds() / 60
            if duration > 0:
                event['duration_minutes'] = str(int(duration))

        # Get summary
        summary = component.get('summary')
        if summary:
            event['summary'] = str(summary)

            # Extract speaker from summary
            speaker = extract_speaker_from_summary(event['summary'])
            if speaker:
                event['speaker'] = speaker
            else:
                event['speaker'] = ''

            # Extract title based on format
            # TQC 2024 format: "A: Title | Authors"
            if '|' in event['summary'] and ':' in event['summary'].split('|')[0]:
                # Extract title between : and |
                title_part = event['summary'].split('|')[0]
                if ':' in title_part:
                    event['title_from_summary'] = title_part.split(':', 1)[1].strip()
                else:
                    event['title_from_summary'] = title_part.strip()
            # TQC 2023 format: "A) Speaker - Title"
            elif ' - ' in event['summary']:
                event['title_from_summary'] = event['summary'].split(' - ', 1)[1].strip()
            else:
                event['title_from_summary'] = event['summary']

        # Get description and extract arXiv IDs
        description = component.get('description')
        if description:
            desc_text = str(description)
            arxiv_ids = []
            for match in re.finditer(r'arxiv\.org/abs/(\d+\.\d+)', desc_text, re.IGNORECASE):
                arxiv_ids.append(match.group(1))
            event['arxiv_ids'] = ', '.join(arxiv_ids) if arxiv_ids else ''
        else:
            event['arxiv_ids'] = ''

        events.append(event)

    return events


def filter_talks(events: List[Dict]) -> List[Dict]:
    """Filter calendar events to only include talks."""

    skip_keywords = [
        'poster session', 'problem session', 'hackathon',
        'welcome', 'coffee', 'lunch', 'dinner', 'tour', 'break',
        'social', 'reception', 'excursion', 'panel',
        'registration', 'opening', 'banquet', 'ride', 'museum',
        'labs visit', 'online poster', 'gala'
    ]

    talks = []
    for event in events:
        summary = event.get('summary', '').lower()

        if any(keyword in summary for keyword in skip_keywords):
            continue

        if len(summary) < 10:
            continue

        talks.append(event)

    return talks


# =============================================================================
# Merging Functions
# =============================================================================

def normalize_title(title: str) -> str:
    """Normalize title for matching."""
    title = title.lower()
    title = re.sub(r'[^\w\s]', ' ', title)
    title = re.sub(r'\s+', ' ', title)
    return title.strip()


def merge_schedule_with_talks(talks: List[Dict], schedule: List[Dict]) -> List[Dict]:
    """Merge scheduling information into talks data."""

    merged_talks = []
    matched_count = 0

    for talk in talks:
        merged_talk = talk.copy()

        # Find best matching schedule entry
        best_match = None
        best_score = 0

        for sched in schedule:
            score = 0

            # Check arXiv ID (strong match)
            sched_arxiv_ids = set(sched.get('arxiv_ids', '').split(', ')) - {''}
            talk_arxiv_id = talk.get('arxiv_ids', '').strip()
            if talk_arxiv_id and talk_arxiv_id in sched_arxiv_ids:
                score += 100

            # Check title similarity
            sched_title = normalize_title(sched.get('title_from_summary', ''))
            talk_title = normalize_title(talk.get('title', ''))
            if sched_title and talk_title:
                sched_words = set(sched_title.split())
                talk_words = set(talk_title.split())
                if sched_words and talk_words:
                    overlap = len(sched_words & talk_words)
                    union = len(sched_words | talk_words)
                    similarity = overlap / union if union > 0 else 0
                    score += similarity * 50

            if score > best_score and score > 20:
                best_score = score
                best_match = sched

        # Merge schedule data if match found
        if best_match:
            merged_talk['scheduled_date'] = best_match.get('date', '')
            merged_talk['scheduled_time'] = best_match.get('time', '')
            merged_talk['duration_minutes'] = best_match.get('duration_minutes', '')

            # Use speaker from calendar as the primary speaker
            # The 'speaker' field was already extracted in parse_ics_calendar
            speaker = best_match.get('speaker', '')
            if speaker:
                # Replace the speakers field with just the presenter
                # (authors are still preserved in the 'authors' field)
                merged_talk['speakers'] = speaker
            # If no speaker extracted, keep the authors as speakers

            matched_count += 1

        merged_talks.append(merged_talk)

    return merged_talks, matched_count


# =============================================================================
# CSV Output Functions
# =============================================================================

def write_csv(talks: List[Dict], output_path: str):
    """Write talks to CSV file in standard format."""

    if not talks:
        print("No talks to write!", file=sys.stderr)
        return

    # Standard columns - abstract last to avoid cluttering review
    fieldnames = [
        'venue',
        'year',
        'paper_type',
        'title',
        'speakers',
        'authors',
        'affiliations',
        'arxiv_ids',
        'session_name',
        'scheduled_date',
        'scheduled_time',
        'duration_minutes',
        'presentation_url',
        'video_url',
        'youtube_id',
        'award',
        'notes',
        '_entry_id',
        '_entry_type',
        '_url',
        '_howpublished',
        'abstract',
    ]

    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, quoting=csv.QUOTE_ALL, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(talks)

    print(f"  Wrote {len(talks)} talks to {output_path}")


# =============================================================================
# Main Workflow
# =============================================================================

def main():
    import os

    print("="*70)
    print("TQC 2023-24 BibTeX and Calendar to CSV Converter")
    print("="*70)

    # File paths
    bibtex_file = 'tqc-publications-23-24.bib'
    calendar_url = "https://calendar.google.com/calendar/ical/8vggdde35g9dplrr2r9fqcjink%40group.calendar.google.com/public/basic.ics"
    calendar_file = 'tqc-calendar.ics'
    output_dir = '../scraped_data'

    # Step 1: Parse BibTeX file
    print("\n[1/5] Parsing BibTeX file...")
    if not os.path.exists(bibtex_file):
        print(f"Error: {bibtex_file} not found!")
        sys.exit(1)

    entries = parse_bibtex_file(bibtex_file)
    print(f"  Found {len(entries)} Talk/Conference/Workshop entries")

    talks = process_bibtex_entries(entries)
    talks_2023 = [t for t in talks if t['year'] == '2023']
    talks_2024 = [t for t in talks if t['year'] == '2024']
    print(f"  TQC 2023: {len(talks_2023)} talks")
    print(f"  TQC 2024: {len(talks_2024)} talks")

    # Step 2: Download calendar
    print("\n[2/5] Downloading Google Calendar...")
    try:
        urllib.request.urlretrieve(calendar_url, calendar_file)
        print(f"  Downloaded to {calendar_file}")
    except Exception as e:
        print(f"  Error downloading calendar: {e}")
        sys.exit(1)

    # Step 3: Parse calendar for TQC 2023
    print("\n[3/5] Parsing calendar for TQC 2023...")
    events_2023 = parse_ics_calendar(calendar_file, 2023)
    schedule_2023 = filter_talks(events_2023)
    schedule_2023.sort(key=lambda x: x.get('datetime'))
    print(f"  Found {len(schedule_2023)} TQC 2023 talk events")

    # Step 4: Parse calendar for TQC 2024
    print("\n[4/5] Parsing calendar for TQC 2024...")
    events_2024 = parse_ics_calendar(calendar_file, 2024)
    schedule_2024 = filter_talks(events_2024)
    schedule_2024.sort(key=lambda x: x.get('datetime'))
    print(f"  Found {len(schedule_2024)} TQC 2024 talk events")

    # Step 5: Merge and write output
    print("\n[5/5] Merging schedule with talks and writing CSV files...")

    # TQC 2023
    merged_2023, matched_2023 = merge_schedule_with_talks(talks_2023, schedule_2023)
    output_2023 = os.path.join(output_dir, 'tqc_2023_talks_with_schedule.csv')
    write_csv(merged_2023, output_2023)
    match_pct_2023 = (matched_2023 / len(talks_2023) * 100) if talks_2023 else 0
    print(f"    - {matched_2023}/{len(talks_2023)} talks matched with schedule ({match_pct_2023:.0f}%)")

    # TQC 2024
    merged_2024, matched_2024 = merge_schedule_with_talks(talks_2024, schedule_2024)
    output_2024 = os.path.join(output_dir, 'tqc_2024_talks_with_schedule.csv')
    write_csv(merged_2024, output_2024)
    match_pct_2024 = (matched_2024 / len(talks_2024) * 100) if talks_2024 else 0
    print(f"    - {matched_2024}/{len(talks_2024)} talks matched with schedule ({match_pct_2024:.0f}%)")

    # Summary
    print("\n" + "="*70)
    print("✓ Conversion complete!")
    print("="*70)
    print(f"\nOutput files:")
    print(f"  • {output_2023}")
    print(f"  • {output_2024}")
    print(f"\nNext step: Import into database with import_from_csv.py")
    print("="*70)


if __name__ == '__main__':
    main()
