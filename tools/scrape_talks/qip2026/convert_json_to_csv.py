#!/usr/bin/env python3
"""Convert QIP 2026 JSON data to CSV format for import."""

import json
import csv
import sys
from pathlib import Path


def parse_arxiv_id(arxiv_string):
    """Extract arXiv ID from string like 'arXiv: 2503.19125' or 'arXiv:2310.05213v3'."""
    if not arxiv_string:
        return None
    
    # Remove 'arXiv:' prefix and whitespace
    arxiv_id = arxiv_string.replace('arXiv:', '').replace('arXiv', '').strip()
    # Remove 'v' version suffix if present
    if 'v' in arxiv_id:
        arxiv_id = arxiv_id.split('v')[0]
    
    return arxiv_id if arxiv_id else None


def determine_paper_type(decision):
    """Determine paper type from decision string."""
    decision_lower = decision.lower()
    
    if 'plenary' in decision_lower:
        return 'plenary'
    elif 'merge' in decision_lower:
        return 'regular'  # Merged papers are still regular contributed papers
    elif decision_lower == 'accepted':
        return 'regular'
    else:
        return 'regular'


def convert_json_to_csv(json_file, output_csv, venue='QIP', year=2026):
    """Convert QIP JSON format to CSV format matching talk import schema."""
    
    # Load JSON data
    with open(json_file, 'r') as f:
        papers = json.load(f)
    
    print(f"Loaded {len(papers)} papers from {json_file}")
    
    # Prepare CSV data
    csv_data = []
    
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
        
        # Determine paper type
        paper_type = determine_paper_type(paper.get('decision', 'Accepted'))
        
        # Extract topics/keywords
        topics = ';'.join(paper.get('topics', []))
        tags_list = paper.get('tags', [])
        # Tags are dicts with 'tag' key
        tags = ';'.join([t.get('tag', '') if isinstance(t, dict) else str(t) for t in tags_list]) if tags_list else ''
        
        # Check for awards
        decision = paper.get('decision', '')
        award = None
        if 'BestStudentPaper' in decision:
            award = 'Best Student Paper'
        
        # Build CSV row
        row = {
            'venue': venue,
            'year': year,
            'paper_type': paper_type,
            'title': paper.get('title', ''),
            'authors': authors,
            'affiliations': affiliations,
            'abstract': paper.get('abstract', ''),
            'arxiv_ids': arxiv_id if arxiv_id else '',
            'presentation_url': '',
            'video_url': '',
            'youtube_id': '',
            'session_name': '',
            'award': award if award else '',
            'notes': paper.get('decision', ''),  # Store original decision for reference
            'speaker': '',  # To be filled by schedule parser
            'scheduled_date': '',  # To be filled by schedule parser
            'scheduled_time': '',  # To be filled by schedule parser
            'duration_minutes': ''  # To be filled by schedule parser
        }
        
        csv_data.append(row)
    
    # Write CSV
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
    
    print(f"✓ Converted {len(csv_data)} accepted papers to {output_csv}")
    print(f"\nBreakdown by paper type:")
    type_counts = {}
    for row in csv_data:
        pt = row['paper_type']
        type_counts[pt] = type_counts.get(pt, 0) + 1
    for pt, count in sorted(type_counts.items()):
        print(f"  {pt}: {count}")
    
    return csv_data


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: ./convert_json_to_csv.py <json_file> [output_csv]")
        print("Example: ./convert_json_to_csv.py qip2026-data.json qip_2026_papers.csv")
        sys.exit(1)
    
    json_file = Path(sys.argv[1])
    if not json_file.exists():
        print(f"Error: {json_file} not found")
        sys.exit(1)
    
    # Default output filename
    if len(sys.argv) >= 3:
        output_csv = Path(sys.argv[2])
    else:
        output_csv = json_file.with_suffix('.csv')
    
    convert_json_to_csv(json_file, output_csv)
    
    print(f"\nNext steps:")
    print(f"  1. Review: {output_csv}")
    print(f"  2. Import: cd tools/scrape_talks && ./import_from_csv.py ../../{output_csv}")
