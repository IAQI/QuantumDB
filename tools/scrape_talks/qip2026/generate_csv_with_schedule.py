#!/usr/bin/env python3
"""
Generate QIP 2026 CSV by merging JSON data with schedule information.
"""

import json
import csv
import sys
import unicodedata
from pathlib import Path
from typing import Dict, List, Optional
from bs4 import BeautifulSoup
from datetime import datetime


def normalize_title(title: str) -> str:
    """Normalize title for matching: NFD Unicode, remove diacritics, lowercase, strip punctuation."""
    if not title:
        return ""
    
    # Remove bracket annotations like [remote], [BEST STUDENT PAPER], etc.
    import re
    title = re.sub(r'\s*\[.*?\]\s*', ' ', title)
    
    # NFD normalization (decompose characters)
    normalized = unicodedata.normalize('NFD', title)
    
    # Remove diacritics (combining characters)
    without_diacritics = ''.join(
        char for char in normalized 
        if not unicodedata.combining(char)
    )
    
    # Lowercase
    lowercased = without_diacritics.lower()
    
    # Remove punctuation and extra spaces
    cleaned = ''.join(
        char if char.isalnum() or char.isspace() else ' '
        for char in lowercased
    )
    
    # Normalize whitespace
    return ' '.join(cleaned.split())


def parse_arxiv_id(arxiv_string: str) -> Optional[str]:
    """Extract arXiv ID(s) from various formats including URLs.
    
    Handles:
    - 'arXiv: 2503.19125' or 'arXiv:2310.05213v3'
    - 'https://arxiv.org/abs/2504.09171'
    - 'https://arxiv.org/pdf/2504.19966'
    - Multiple IDs separated by commas
    """
    if not arxiv_string:
        return None
    
    import re
    
    arxiv_ids = []
    
    # Split by comma to handle multiple entries
    parts = arxiv_string.split(',')
    
    for part in parts:
        part = part.strip()
        if not part:
            continue
        
        # Skip DOI URLs and other non-arXiv URLs
        if 'doi.org' in part.lower() or (part.startswith('http') and 'arxiv' not in part.lower()):
            continue
        
        # Try to extract from URL format: https://arxiv.org/abs/XXXX.XXXXX or https://arxiv.org/pdf/XXXX.XXXXX
        url_match = re.search(r'arxiv\.org/(?:abs|pdf)/(\d{4}\.\d{4,5})', part, re.IGNORECASE)
        if url_match:
            arxiv_ids.append(url_match.group(1))
            continue
        
        # Try direct arXiv ID format (with or without 'arXiv:' prefix)
        # Pattern: YYMM.NNNNN or YYMM.NNNNNvX
        arxiv_match = re.search(r'(\d{4}\.\d{4,5})', part)
        if arxiv_match:
            arxiv_ids.append(arxiv_match.group(1))
            continue
    
    # Return comma-separated list of unique arXiv IDs
    if arxiv_ids:
        unique_ids = []
        for aid in arxiv_ids:
            if aid not in unique_ids:
                unique_ids.append(aid)
        return ','.join(unique_ids)
    
    return None


def determine_paper_type(decision: str, duration_minutes: int = 0) -> str:
    """Determine paper type from decision string and optional duration."""
    decision_lower = decision.lower()
    
    if 'plenary' in decision_lower:
        # Use duration to determine long vs short
        if duration_minutes >= 60:
            return 'plenary_long'
        else:
            return 'plenary_short'
    elif 'merge' in decision_lower:
        return 'regular'  # Merged papers are still regular contributed papers
    elif decision_lower == 'accepted':
        return 'regular'
    else:
        return 'regular'


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


def parse_schedule_html(html_path: str) -> Dict[str, Dict]:
    """Parse schedule HTML and return mapping of normalized titles to schedule info."""
    
    with open(html_path, 'r', encoding='utf-8') as f:
        soup = BeautifulSoup(f.read(), 'html.parser')
    
    schedule_map = {}
    current_date = None
    
    # Find all day headers
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
            
            # Get session type
            label_elem = content_cell.find('span', class_='session__label')
            session_type = label_elem.get_text(strip=True).lower() if label_elem else ''
            
            # Get preview (contains talk details)
            preview_elem = content_cell.find('p', class_='session__preview')
            if not preview_elem:
                continue
            
            # Parse plenaries and tutorials
            if session_type in ['plenary', 'tutorial']:
                # Look for titles in <strong> tags within any <p> tags
                # Handle both direct <p> children and nested <p> within session__preview
                all_p_tags = preview_elem.find_all('p')
                
                # Group consecutive p tags to handle title + authors pattern
                i = 0
                while i < len(all_p_tags):
                    p_tag = all_p_tags[i]
                    strong_tags = p_tag.find_all('strong')
                    
                    for strong in strong_tags:
                        title_raw = strong.get_text(strip=True)
                        
                        # Skip empty or very short titles (likely not paper titles)
                        if not title_raw or len(title_raw) < 15:
                            continue
                        
                        # Extract speaker - could be in same p tag or next p tag
                        speaker = ''
                        
                        # First try: look in same p tag for additional lines/content
                        p_text = p_tag.get_text('\n', strip=True)
                        lines = p_text.split('\n')
                        
                        if len(lines) >= 2:
                            # Speaker on second line in same <p>
                            author_line = lines[1]
                            # Look for bold author names in same p tag
                            bold_authors = p_tag.find_all('strong')
                            if len(bold_authors) > 1:  # More than just the title
                                speaker = bold_authors[1].get_text(strip=True)
                            elif ', ' in author_line:
                                speaker = author_line.split(',')[0].strip()
                            else:
                                speaker = author_line.strip()
                        elif i + 1 < len(all_p_tags):
                            # Speaker might be in next <p> tag
                            next_p = all_p_tags[i + 1]
                            next_strong = next_p.find('strong')
                            if next_strong:
                                speaker = next_strong.get_text(strip=True)
                            else:
                                # Take first author from comma-separated list
                                author_line = next_p.get_text(strip=True)
                                if ', ' in author_line:
                                    speaker = author_line.split(',')[0].strip()
                                else:
                                    speaker = author_line.strip()
                        
                        # Normalize title for matching (this will strip [remote] etc.)
                        norm_title = normalize_title(title_raw)
                        
                        schedule_map[norm_title] = {
                            'date': current_date,
                            'start_time': start_time,
                            'speaker': speaker,
                            'duration_minutes': duration
                        }
                    
                    i += 1
            
            # Parse contributed sessions (parallel tracks)
            elif session_type in ['contributed', 'alg', 'com', 'fnd', 'inf', 'mb', 'qec', 'lrn', 'cry']:
                # Look for synopses (individual talk details in structured format)
                synopses = content_cell.find_all('div', class_='synopsis')
                
                if synopses:
                    # Parse individual talks from synopses
                    for synopsis in synopses:
                        synopsis_title = synopsis.find('div', class_='synopsis__title')
                        synopsis_preview = synopsis.find('div', class_='synopsis__preview')
                        
                        if synopsis_title:
                            title = synopsis_title.get_text(strip=True)
                            speaker = ''
                            
                            if synopsis_preview:
                                # Speaker is typically first line of preview
                                preview_text = synopsis_preview.get_text('\n', strip=True)
                                lines = preview_text.split('\n')
                                if lines:
                                    speaker = lines[0].strip()
                            
                            if title and len(title) >= 15:
                                norm_title = normalize_title(title)
                                schedule_map[norm_title] = {
                                    'date': current_date,
                                    'start_time': start_time,
                                    'speaker': speaker,
                                    'duration_minutes': 20  # Standard contributed talk
                                }
                else:
                    # Fallback: Parse from <p> tags with time markers
                    # Extract titles from <strong> tags to handle multi-line titles correctly
                    import re
                    
                    all_p_tags = preview_elem.find_all('p')
                    i = 0
                    while i < len(all_p_tags):
                        p_tag = all_p_tags[i]
                        p_text = p_tag.get_text(strip=True)
                        
                        # Look for time pattern at start: "HH:MM-HH:MM" (may or may not have space after)
                        time_match = re.match(r'(\d{2}:\d{2})-(\d{2}:\d{2})\s*', p_text)
                        
                        # Check if this is a merged session
                        is_merge = 'Merge:' in p_text or 'merge:' in p_text.lower()
                        
                        if time_match:
                            talk_start = time_match.group(1)
                            talk_end = time_match.group(2)
                            
                            # Check if this starts a merge
                            if is_merge:
                                # This is a merged session - collect all papers in this merge
                                # Papers in merge are in subsequent p tags without time prefixes
                                merged_papers = []
                                
                                # Get papers from current p tag (after "Merge:")
                                strong_tags = p_tag.find_all('strong')
                                for strong in strong_tags:
                                    title_raw = strong.get_text(strip=True)
                                    if title_raw and len(title_raw) >= 15 and 'Merge' not in title_raw:
                                        merged_papers.append((p_tag, strong, title_raw))
                                
                                # Look ahead for papers without time prefixes
                                j = i + 1
                                while j < len(all_p_tags):
                                    next_p = all_p_tags[j]
                                    next_text = next_p.get_text(strip=True)
                                    # Stop if we hit another time prefix
                                    if re.match(r'\d{2}:\d{2}-\d{2}:\d{2}', next_text):
                                        break
                                    # Collect papers from this p tag
                                    for strong in next_p.find_all('strong'):
                                        title_raw = strong.get_text(strip=True)
                                        if title_raw and len(title_raw) >= 15:
                                            merged_papers.append((next_p, strong, title_raw))
                                    j += 1
                                
                                # Process all merged papers with same time
                                for p_tag, strong, title_raw in merged_papers:
                                    # Extract speaker
                                    speaker = ''
                                    all_strong = p_tag.find_all('strong')
                                    if len(all_strong) > 1:
                                        # Look for bold author after title
                                        idx = list(all_strong).index(strong)
                                        if idx + 1 < len(all_strong):
                                            speaker = all_strong[idx + 1].get_text(strip=True)
                                    
                                    if not speaker:
                                        # Extract from text after title
                                        full_text = p_tag.get_text('\n', strip=True)
                                        if title_raw in full_text:
                                            after_title = full_text.split(title_raw, 1)[1].strip()
                                            if after_title:
                                                author_list = [a.strip() for a in after_title.split(',')]
                                                speaker = author_list[0] if author_list else ''
                                    
                                    norm_title = normalize_title(title_raw)
                                    schedule_map[norm_title] = {
                                        'date': current_date,
                                        'start_time': talk_start,
                                        'speaker': speaker,
                                        'duration_minutes': 20,
                                        'is_merged': True
                                    }
                                
                                # Skip past all the merged papers
                                i = j
                                continue
                            else:
                                # Regular single paper with time
                                # Extract title from <strong> tag (handles multi-line titles)
                                strong_tag = p_tag.find('strong')
                                if strong_tag:
                                    title_raw = strong_tag.get_text(strip=True)
                                else:
                                    # Fallback: extract from text after time
                                    remaining = p_text[time_match.end():].strip()
                                    lines = remaining.split('\n', 1)
                                    title_raw = lines[0].strip()
                                
                                # Extract speaker from remaining text or look for bold author
                                speaker = ''
                                # Get all strong tags in this p tag
                                all_strong = p_tag.find_all('strong')
                                if len(all_strong) > 1:
                                    # Second strong tag is usually the speaker
                                    speaker = all_strong[1].get_text(strip=True)
                                else:
                                    # Extract from text after title
                                    full_text = p_tag.get_text('\n', strip=True)
                                    # Remove time and title to get authors
                                    if title_raw in full_text:
                                        after_title = full_text.split(title_raw, 1)[1].strip()
                                        if after_title:
                                            # Take first author from comma-separated list
                                            author_list = [a.strip() for a in after_title.split(',')]
                                            speaker = author_list[0] if author_list else ''
                                
                                if title_raw and len(title_raw) >= 15:
                                    # Normalize will remove [remote] and other bracket annotations
                                    norm_title = normalize_title(title_raw)
                                    schedule_map[norm_title] = {
                                        'date': current_date,
                                        'start_time': talk_start,
                                        'speaker': speaker,
                                        'duration_minutes': 20
                                    }
                        elif not time_match and i > 0:
                            # This might be a paper without time in a merged session
                            # Only process if we haven't seen a time match yet (orphaned papers)
                            strong_tags = p_tag.find_all('strong')
                            for strong in strong_tags:
                                title_raw = strong.get_text(strip=True)
                                if title_raw and len(title_raw) >= 15:
                                    # Extract speaker
                                    speaker = ''
                                    all_strong = p_tag.find_all('strong')
                                    if len(all_strong) > 1:
                                        idx = list(all_strong).index(strong)
                                        if idx + 1 < len(all_strong):
                                            speaker = all_strong[idx + 1].get_text(strip=True)
                                    
                                    if not speaker:
                                        full_text = p_tag.get_text('\n', strip=True)
                                        if title_raw in full_text:
                                            after_title = full_text.split(title_raw, 1)[1].strip()
                                            if after_title:
                                                author_list = [a.strip() for a in after_title.split(',')]
                                                speaker = author_list[0] if author_list else ''
                                    
                                    # For orphaned papers without explicit merge, look back for time
                                    # Check previous p tags for a time
                                    last_time = None
                                    for prev_idx in range(i - 1, max(0, i - 3), -1):
                                        prev_text = all_p_tags[prev_idx].get_text(strip=True)
                                        prev_match = re.search(r'(\d{2}:\d{2})-(\d{2}:\d{2})', prev_text)
                                        if prev_match:
                                            last_time = prev_match.group(1)
                                            break
                                    
                                    if last_time:
                                        norm_title = normalize_title(title_raw)
                                        schedule_map[norm_title] = {
                                            'date': current_date,
                                            'start_time': last_time,
                                            'speaker': speaker,
                                            'duration_minutes': 20,
                                            'is_merged': True
                                        }
                        
                        i += 1
    
    return schedule_map


def merge_json_with_schedule(json_file: str, schedule_file: str, output_csv: str):
    """Merge JSON data with schedule information and generate CSV."""
    
    # Load JSON data
    with open(json_file, 'r') as f:
        papers = json.load(f)
    
    print(f"Loaded {len(papers)} papers from {json_file}")
    
    # Parse schedule
    schedule_map = parse_schedule_html(schedule_file)
    print(f"Parsed {len(schedule_map)} talks from schedule")
    
    # Prepare CSV data
    csv_data = []
    matched_count = 0
    
    for paper in papers:
        # Skip if not accepted
        if 'Accepted' not in paper.get('decision', ''):
            continue
        
        # Extract authors
        authors_list = paper.get('authors', [])
        authors = ';'.join([f"{a.get('first', '')} {a.get('last', '')}".strip() for a in authors_list])
        affiliations = ';'.join([a.get('affiliation', '') for a in authors_list])
        
        # Parse arXiv ID
        arxiv_id = parse_arxiv_id(paper.get('arxiv_number_url', ''))
        
        # Get title and normalize for matching
        title = paper.get('title', '')
        norm_title = normalize_title(title)
        
        # Look up schedule info
        schedule_info = schedule_map.get(norm_title, {})
        
        # Determine paper type (use schedule duration if available)
        duration = schedule_info.get('duration_minutes', 0)
        paper_type = determine_paper_type(paper.get('decision', 'Accepted'), duration)
        
        # Check for awards
        decision = paper.get('decision', '')
        award = None
        if 'BestStudentPaper' in decision:
            award = 'Best Student Paper'
        
        # Get schedule details
        scheduled_date = schedule_info.get('date', '')
        scheduled_time = schedule_info.get('start_time', '')
        speaker = schedule_info.get('speaker', '')
        duration_minutes = duration if duration > 0 else ''
        is_merged = schedule_info.get('is_merged', False)
        session_name = 'Merged slot' if is_merged else ''
        
        if schedule_info:
            matched_count += 1
        
        # Build CSV row
        row = {
            'venue': 'QIP',
            'year': 2026,
            'paper_type': paper_type,
            'title': title,
            'authors': authors,
            'affiliations': affiliations,
            'abstract': paper.get('abstract', ''),
            'arxiv_ids': arxiv_id if arxiv_id else '',
            'presentation_url': '',
            'video_url': '',
            'youtube_id': '',
            'session_name': session_name,
            'award': award if award else '',
            'notes': decision,
            'speaker': speaker,
            'scheduled_date': scheduled_date,
            'scheduled_time': scheduled_time,
            'duration_minutes': duration_minutes
        }
        
        csv_data.append(row)
    
    # Write full CSV
    fieldnames = [
        'venue', 'year', 'paper_type', 'title', 'authors', 
        'affiliations', 'abstract', 'arxiv_ids', 'presentation_url', 
        'video_url', 'youtube_id', 'session_name', 'award', 'notes',
        'speaker', 'scheduled_date', 'scheduled_time', 'duration_minutes'
    ]
    
    with open(output_csv, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(csv_data)
    
    # Write compact CSV without abstracts for easier manual checking
    compact_csv = str(output_csv).replace('_final.csv', '_compact.csv')
    compact_fieldnames = [
        'venue', 'year', 'paper_type', 'title', 'authors', 
        'arxiv_ids', 'speaker', 'scheduled_date', 'scheduled_time', 'duration_minutes', 'session_name'
    ]
    
    with open(compact_csv, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=compact_fieldnames, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(csv_data)
    
    print(f"\n✓ Generated {output_csv}")
    print(f"✓ Generated {compact_csv} (compact version for manual review)")
    print(f"  Total papers: {len(csv_data)}")
    print(f"  Matched with schedule: {matched_count} ({matched_count*100//len(csv_data)}%)")
    
    # Breakdown by paper type
    print(f"\nBreakdown by paper type:")
    type_counts = {}
    for row in csv_data:
        pt = row['paper_type']
        type_counts[pt] = type_counts.get(pt, 0) + 1
    for pt, count in sorted(type_counts.items()):
        print(f"  {pt}: {count}")
    
    # Show breakdown of matched vs unmatched
    matched_papers = [row for row in csv_data if row['speaker']]
    unmatched_papers = [row for row in csv_data if not row['speaker']]
    
    print(f"\nSchedule matching:")
    print(f"  Papers with speaker info: {len(matched_papers)}")
    print(f"  Papers without speaker info: {len(unmatched_papers)}")
    
    if matched_papers:
        print(f"\nMatched papers (with speaker/date/time):")
        for row in matched_papers[:5]:
            print(f"  - {row['title'][:60]}... ({row['speaker']}, {row['scheduled_date']} {row['scheduled_time']})")
        if len(matched_papers) > 5:
            print(f"  ... and {len(matched_papers) - 5} more")
    
    if unmatched_papers:
        print(f"\n⚠ Papers WITHOUT speaker info ({len(unmatched_papers)}):")
        for row in unmatched_papers[:10]:
            norm_title = normalize_title(row['title'])
            print(f"  - {row['title'][:70]}")
            print(f"    Normalized: {norm_title[:70]}")
        if len(unmatched_papers) > 10:
            print(f"  ... and {len(unmatched_papers) - 10} more")
        print(f"\n  Check if these titles appear in the schedule HTML but with different formatting.")
    
    # Write manual review file
    review_file = str(output_csv).replace('_final.csv', '_manual_review.txt')
    with open(review_file, 'w', encoding='utf-8') as f:
        f.write("QIP 2026 Papers - Manual Review Required\n")
        f.write("=" * 80 + "\n\n")
        f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Total papers: {len(csv_data)}\n")
        f.write(f"Matched with schedule: {matched_count} ({matched_count*100//len(csv_data)}%)\n")
        f.write(f"Requiring manual review: {len(unmatched_papers)}\n\n")
        
        if unmatched_papers:
            f.write("-" * 80 + "\n")
            f.write("PAPERS WITHOUT SCHEDULE INFORMATION\n")
            f.write("-" * 80 + "\n\n")
            f.write("These papers were not matched with the schedule. Possible reasons:\n")
            f.write("  • Title differs between JSON and schedule HTML\n")
            f.write("  • Paper was accepted but not scheduled for presentation\n")
            f.write("  • Late addition or withdrawn paper\n\n")
            
            for i, row in enumerate(unmatched_papers, 1):
                f.write(f"{i}. {row['title']}\n")
                f.write(f"   Authors: {row['authors']}\n")
                f.write(f"   Decision: {row['notes']}\n")
                f.write(f"   arXiv: {row['arxiv_ids'] if row['arxiv_ids'] else 'N/A'}\n")
                f.write(f"   Normalized title: {normalize_title(row['title'])}\n")
                f.write(f"\n   ACTION NEEDED:\n")
                f.write(f"   [ ] Search schedule HTML for this paper\n")
                f.write(f"   [ ] If found, note the exact title in schedule: _________________\n")
                f.write(f"   [ ] Add speaker: _________________\n")
                f.write(f"   [ ] Add date/time: _________________\n")
                f.write(f"   [ ] If not in schedule, confirm paper status\n")
                f.write("\n" + "-" * 80 + "\n\n")
        
        # Add merged sessions summary
        merged_papers = [row for row in csv_data if row.get('session_name') == 'Merged slot']
        if merged_papers:
            from collections import defaultdict
            merged_sessions = defaultdict(list)
            for row in merged_papers:
                key = f"{row['scheduled_date']} {row['scheduled_time']}"
                merged_sessions[key].append(row)
            
            f.write("-" * 80 + "\n")
            f.write("MERGED TIME SLOTS (VERIFY CORRECTNESS)\n")
            f.write("-" * 80 + "\n\n")
            f.write("These papers share the same time slot. Please verify:\n")
            f.write("  • All papers in each slot should actually be presented together\n")
            f.write("  • Speaker information is correct for each paper\n\n")
            
            for time_slot in sorted(merged_sessions.keys()):
                papers = merged_sessions[time_slot]
                f.write(f"Time Slot: {time_slot} ({len(papers)} papers)\n")
                f.write("-" * 40 + "\n")
                for i, row in enumerate(papers, 1):
                    f.write(f"  {i}. {row['title']}\n")
                    f.write(f"     Speaker: {row['speaker']}\n")
                    f.write(f"     Authors: {row['authors'][:80]}\n")
                f.write("\n   ACTION NEEDED:\n")
                f.write(f"   [ ] Verify all {len(papers)} papers share this time slot\n")
                f.write(f"   [ ] Confirm speaker assignments\n")
                f.write("\n" + "-" * 80 + "\n\n")
        
        # Add statistics summary
        f.write("-" * 80 + "\n")
        f.write("SUMMARY STATISTICS\n")
        f.write("-" * 80 + "\n\n")
        f.write(f"Total papers: {len(csv_data)}\n")
        f.write(f"Papers with complete schedule info: {len(matched_papers)}\n")
        f.write(f"Papers in merged slots: {len(merged_papers)}\n")
        f.write(f"Papers needing manual review: {len(unmatched_papers)}\n\n")
        
        f.write("Paper type breakdown:\n")
        for pt, count in sorted(type_counts.items()):
            f.write(f"  {pt}: {count}\n")
        
        f.write(f"\nCompletion rate: {matched_count*100//len(csv_data)}%\n")
    
    print(f"\n✓ Generated {review_file} (manual review file)")


if __name__ == '__main__':
    script_dir = Path(__file__).parent
    
    json_file = script_dir / 'qip2026-data.json'
    schedule_file = script_dir / 'qip_2026_schedule.html'
    output_csv = script_dir.parent / 'scraped_data' / 'qip_2026_papers_final.csv'
    
    if not json_file.exists():
        print(f"Error: {json_file} not found")
        sys.exit(1)
    
    if not schedule_file.exists():
        print(f"Error: {schedule_file} not found")
        sys.exit(1)
    
    merge_json_with_schedule(json_file, schedule_file, output_csv)
    
    print(f"\nNext steps:")
    print(f"  1. Review: {output_csv}")
    print(f"  2. Manual review: {str(output_csv).replace('_final.csv', '_manual_review.txt')}")
    print(f"  3. Import: cd tools/scrape_talks && ./import_from_csv.py scraped_data/qip_2026_papers_final.csv")

