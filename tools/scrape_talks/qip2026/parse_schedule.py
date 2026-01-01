#!/usr/bin/env python3
"""
Parse QIP 2026 schedule to extract speaker and timing information.
"""

import re
import csv
import json
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from bs4 import BeautifulSoup


def parse_time(time_str: str) -> tuple[str, str]:
    """Parse time range like '09:30-11:00' into start and end times."""
    parts = time_str.strip().split('-')
    if len(parts) != 2:
        return ('', '')
    return (parts[0].strip(), parts[1].strip())


def calculate_duration_minutes(start_time: str, end_time: str) -> int:
    """Calculate duration in minutes between start and end times."""
    if not start_time or not end_time:
        return 0
    
    try:
        fmt = '%H:%M'
        start = datetime.strptime(start_time, fmt)
        end = datetime.strptime(end_time, fmt)
        duration = (end - start).total_seconds() / 60
        return int(duration)
    except ValueError:
        return 0


def parse_schedule_html(html_path: str) -> List[Dict[str, Any]]:
    """Parse the schedule HTML and extract talk information."""
    
    with open(html_path, 'r', encoding='utf-8') as f:
        soup = BeautifulSoup(f.read(), 'html.parser')
    
    talks = []
    current_date = None
    
    # Find all day headers and session rows
    day_headers = soup.find_all('div', class_='day-header')
    
    for day_header in day_headers:
        # Extract date
        subtitle = day_header.find('h3', class_='day-header__subtitle')
        if subtitle:
            current_date = subtitle.get_text(strip=True)
        
        # Find the next sessions table
        sessions_table = day_header.find_next('table', class_='sessions')
        if not sessions_table:
            continue
        
        # Process each session row
        for session_row in sessions_table.find_all('tr', class_='session'):
            # Get time
            time_cell = session_row.find('td', class_='session__date')
            time_str = time_cell.get_text(strip=True) if time_cell else ''
            start_time, end_time = parse_time(time_str)
            duration = calculate_duration_minutes(start_time, end_time)
            
            # Get session content
            content_cell = session_row.find('td', class_='session__content')
            if not content_cell:
                continue
            
            # Get session type (label)
            label_elem = content_cell.find('span', class_='session__label')
            session_type = label_elem.get_text(strip=True).lower() if label_elem else ''
            
            # Get track/room
            track_elem = content_cell.find('span', class_='session__track')
            track = track_elem.get_text(strip=True) if track_elem else ''
            
            # Get title
            title_elem = content_cell.find('h2', class_='session__title')
            title = title_elem.get_text(strip=True) if title_elem else ''
            
            # Get preview (contains speaker info)
            preview_elem = content_cell.find('p', class_='session__preview')
            preview_text = ''
            if preview_elem:
                preview_text = preview_elem.get_text('\n', strip=True)
            
            # Process based on session type
            if session_type in ['plenary', 'tutorial']:
                # Single talk or merged talks
                # For plenaries, check if the actual title is in the preview (for SHORT PLENARY)
                paper_type = 'tutorial' if session_type == 'tutorial' else determine_plenary_type(title, duration)
                
                # Check for merged talks by looking for multiple <strong> tags with titles
                if preview_elem:
                    p_tags = preview_elem.find_all('p')
                    
                    # Collect all papers in this session (usually 1, sometimes 2+ for merged)
                    papers_in_session = []
                    
                    for p_tag in p_tags:
                        # Look for <strong> tag that might be a title
                        strong_elems = p_tag.find_all('strong')
                        if not strong_elems:
                            continue
                        
                        # Check if first strong looks like a title (longer text)
                        first_strong = strong_elems[0].get_text(strip=True)
                        if len(first_strong) > 15:  # Likely a title, not just a name
                            paper_title = first_strong
                            speaker = ''
                            
                            # Get text after the title to find authors
                            full_text = p_tag.get_text(strip=True)
                            # Remove the title from the start
                            after_title = full_text[len(paper_title):].strip()
                            
                            if after_title:
                                authors = [a.strip() for a in after_title.split(',')]
                                # Find which author is in <strong> (excluding the title)
                                for strong in strong_elems[1:]:  # Skip first (title)
                                    strong_text = strong.get_text(strip=True)
                                    if strong_text in authors:
                                        speaker = strong_text
                                        break
                                # If no speaker in strong, use first author
                                if not speaker and authors and authors[0]:
                                    speaker = authors[0]
                            
                            papers_in_session.append({
                                'title': paper_title,
                                'speaker': speaker
                            })
                    
                    # Add all papers found to talks list
                    if papers_in_session:
                        for paper_info in papers_in_session:
                            talks.append({
                                'date': current_date,
                                'start_time': start_time,
                                'end_time': end_time,
                                'duration_minutes': duration,
                                'track': track,
                                'session_type': session_type,
                                'paper_type': paper_type,
                                'title': paper_info['title'],
                                'speaker': paper_info['speaker'],
                                'affiliation': ''
                            })
                    else:
                        # Fallback to old method if no papers found
                        speaker, affiliation = parse_speaker_info(preview_text)
                        talks.append({
                            'date': current_date,
                            'start_time': start_time,
                            'end_time': end_time,
                            'duration_minutes': duration,
                            'track': track,
                            'session_type': session_type,
                            'paper_type': paper_type,
                            'title': title,
                            'speaker': speaker,
                            'affiliation': affiliation
                        })
                else:
                    # No preview, use session title
                    talks.append({
                        'date': current_date,
                        'start_time': start_time,
                        'end_time': end_time,
                        'duration_minutes': duration,
                        'track': track,
                        'session_type': session_type,
                        'paper_type': paper_type,
                        'title': title,
                        'speaker': '',
                        'affiliation': ''
                    })
            
            elif session_type in ['alg', 'com', 'fnd', 'inf', 'mb', 'qec', 'lrn', 'cry']:
                # Parallel session with multiple talks
                # Look for synopses (individual talk details)
                synopses = content_cell.find_all('div', class_='synopsis')
                
                if synopses:
                    # Parse individual talks from synopses
                    for synopsis in synopses:
                        synopsis_title = synopsis.find('div', class_='synopsis__title')
                        synopsis_preview = synopsis.find('div', class_='synopsis__preview')
                        synopsis_meta = synopsis.find('div', class_='synopsis__meta')
                        
                        if synopsis_title:
                            talk_title = synopsis_title.get_text(strip=True)
                            speaker = synopsis_preview.get_text(strip=True) if synopsis_preview else ''
                            
                            talks.append({
                                'date': current_date,
                                'start_time': start_time,
                                'end_time': end_time,
                                'duration_minutes': duration,
                                'track': track,
                                'session_type': session_type,
                                'paper_type': 'regular',
                                'title': talk_title,
                                'speaker': speaker,
                                'affiliation': ''
                            })
                else:
                    # Parse from preview text with time markers
                    parse_parallel_session(talks, preview_text, current_date, track, session_type)
    
    return talks


def parse_speaker_info(text: str) -> tuple[str, str]:
    """Extract speaker name and affiliation from preview text."""
    if not text:
        return ('', '')
    
    lines = text.strip().split('\n')
    speaker = lines[0].strip() if len(lines) > 0 else ''
    affiliation = lines[1].strip() if len(lines) > 1 else ''
    
    return (speaker, affiliation)


def determine_plenary_type(title: str, duration: int) -> str:
    """Determine if a plenary talk is long or short based on title and duration."""
    title_lower = title.lower()
    
    # Invited plenaries are typically long
    if 'invited' in title_lower:
        return 'plenary_long'
    
    # Short plenaries are explicitly labeled
    if 'short plenary' in title_lower:
        return 'plenary_short'
    
    # Otherwise use duration (60+ minutes = long, <60 = short)
    if duration >= 60:
        return 'plenary_long'
    else:
        return 'plenary_short'


def parse_parallel_session(talks: List[Dict], preview_text: str, date: str, track: str, session_type: str):
    """Parse parallel session text that contains multiple talks with time markers."""
    if not preview_text:
        return
    
    # Pattern: "HH:MM-HH:MM Title\nAuthors"
    # Example: "13:30-14:00 Quantum simulation...\nSergey Bravyi, Sergiy Zhuk..."
    pattern = r'(\d{2}:\d{2})-(\d{2}:\d{2})\s+(.+?)(?=\d{2}:\d{2}-|\Z)'
    
    matches = re.finditer(pattern, preview_text, re.DOTALL)
    
    for match in matches:
        start_time = match.group(1)
        end_time = match.group(2)
        content = match.group(3).strip()
        
        # Split content into title and authors
        lines = content.split('\n', 1)
        title = lines[0].strip()
        authors = lines[1].strip() if len(lines) > 1 else ''
        
        # Extract first author as speaker
        speaker = ''
        if authors:
            author_list = [a.strip() for a in authors.split(',')]
            speaker = author_list[0] if author_list else ''
        
        duration = calculate_duration_minutes(start_time, end_time)
        
        talks.append({
            'date': date,
            'start_time': start_time,
            'end_time': end_time,
            'duration_minutes': duration,
            'track': track,
            'session_type': session_type,
            'paper_type': 'regular',
            'title': title,
            'speaker': speaker,
            'affiliation': ''
        })


def match_with_papers(schedule_talks: List[Dict], papers_csv: str) -> List[Dict]:
    """Match schedule information with papers from CSV."""
    
    # Read papers
    papers = []
    with open(papers_csv, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        papers = list(reader)
    
    # Create title-to-schedule mapping (normalize titles for matching)
    schedule_map = {}
    for talk in schedule_talks:
        normalized_title = normalize_title(talk['title'])
        schedule_map[normalized_title] = talk
    
    # Update papers with schedule info
    updated_papers = []
    for paper in papers:
        paper_title = normalize_title(paper['title'])
        
        if paper_title in schedule_map:
            schedule_info = schedule_map[paper_title]
            paper['speaker'] = schedule_info['speaker']
            paper['scheduled_date'] = schedule_info['date']
            paper['scheduled_time'] = schedule_info['start_time']
            paper['duration_minutes'] = str(schedule_info['duration_minutes'])
            
            # Update paper_type - distinguish plenary types from schedule
            if paper['paper_type'] == 'plenary':
                paper['paper_type'] = schedule_info['paper_type']
        else:
            # For papers not matched in schedule
            # Check if they're merged plenaries (will have plenary in notes field)
            if paper['paper_type'] == 'plenary':
                notes = paper.get('notes', '').lower()
                if 'longplenary' in notes:
                    paper['paper_type'] = 'plenary_long'
                elif 'plenary' in notes:
                    # Default to short for merged plenaries unless explicitly long
                    paper['paper_type'] = 'plenary_short'
        
        # All non-plenary papers are regular (contributed)
        if paper['paper_type'] not in ['plenary', 'plenary_long', 'plenary_short', 'invited', 'tutorial', 'keynote', 'poster']:
            paper['paper_type'] = 'regular'
        
        updated_papers.append(paper)
    
    return updated_papers


def normalize_title(title: str) -> str:
    """Normalize title for matching (lowercase, remove extra whitespace, punctuation)."""
    import unicodedata
    
    # Remove common prefixes
    title = re.sub(r'^(TUTORIAL|PLENARY|SHORT PLENARY \d+|INVITED PLENARY \d*):?\s*', '', title, flags=re.IGNORECASE)
    
    # Convert to NFD (decomposed) Unicode and remove diacritics
    title = unicodedata.normalize('NFD', title)
    title = ''.join(c for c in title if unicodedata.category(c) != 'Mn')
    
    # Convert to lowercase
    title = title.lower()
    
    # Remove all punctuation and special characters
    title = re.sub(r'[^\w\s]', '', title)
    
    # Normalize whitespace
    title = ' '.join(title.split())
    
    return title


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Parse QIP 2026 schedule')
    parser.add_argument('schedule_html', help='Path to schedule HTML file')
    parser.add_argument('papers_csv', help='Path to papers CSV file')
    parser.add_argument('output_csv', help='Path to output CSV file')
    
    args = parser.parse_args()
    
    print(f"Parsing schedule from {args.schedule_html}...")
    schedule_talks = parse_schedule_html(args.schedule_html)
    print(f"✓ Found {len(schedule_talks)} scheduled talks")
    
    print(f"\nMatching with papers from {args.papers_csv}...")
    updated_papers = match_with_papers(schedule_talks, args.papers_csv)
    
    # Write updated CSV
    if updated_papers:
        fieldnames = updated_papers[0].keys()
        with open(args.output_csv, 'w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(updated_papers)
        
        print(f"✓ Updated papers written to {args.output_csv}")
        
        # Print statistics
        with_speaker = sum(1 for p in updated_papers if p.get('speaker'))
        plenary_long = sum(1 for p in updated_papers if p.get('paper_type') == 'plenary_long')
        plenary_short = sum(1 for p in updated_papers if p.get('paper_type') == 'plenary_short')
        regular = sum(1 for p in updated_papers if p.get('paper_type') == 'regular')
        
        print(f"\nStatistics:")
        print(f"  Papers with speaker info: {with_speaker}/{len(updated_papers)}")
        print(f"  Paper types:")
        print(f"    plenary_long: {plenary_long}")
        print(f"    plenary_short: {plenary_short}")
        print(f"    regular: {regular}")


if __name__ == '__main__':
    main()
