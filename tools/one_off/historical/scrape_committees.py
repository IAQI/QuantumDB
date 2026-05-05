#!/usr/bin/env python3
"""Scrape committee membership data from archived conference websites."""

import argparse
import asyncio
import json
import logging
import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple
from uuid import UUID, uuid4

import asyncpg
from bs4 import BeautifulSoup
import aiohttp
from dotenv import load_dotenv


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class CommitteeMember:
    """Committee member information."""
    name: str
    committee: str  # OC, PC, SC, Local
    position: str  # chair, co_chair, area_chair, member
    role_title: Optional[str] = None
    affiliation: Optional[str] = None


@dataclass
class ConferenceToScrape:
    """Conference to scrape."""
    id: UUID
    venue: str
    year: int
    archive_pc_url: Optional[str] = None
    archive_organizers_url: Optional[str] = None
    archive_steering_url: Optional[str] = None


def normalize_name(name: str) -> str:
    """Normalize author name for matching."""
    # Remove common prefixes/suffixes
    name = re.sub(r'\b(Dr\.|Prof\.|Jr\.|Sr\.|Ph\.?D\.?|M\.?D\.?)\b', '', name, flags=re.IGNORECASE)
    # Remove extra whitespace
    name = ' '.join(name.split())
    # Convert to lowercase for matching
    return name.lower().strip()


def get_local_dir(args: argparse.Namespace) -> Path:
    """Get the local web directory."""
    if args.local_dir:
        return Path(args.local_dir)
    home = os.environ.get('HOME', '.')
    return Path(home) / 'Web'


def url_to_local_path(args: argparse.Namespace, url: str) -> Path:
    """Convert URL to local file path."""
    local_dir = get_local_dir(args)
    
    # Parse the URL to extract domain and path
    without_protocol = url.removeprefix('http://').removeprefix('https://')
    parts = without_protocol.split('/', 1)
    domain = parts[0]
    path = parts[1] if len(parts) > 1 else ''
    
    # Check if the local_dir already ends with the domain
    if local_dir.name == domain:
        base = local_dir
    else:
        base = local_dir / domain
    
    # Construct the full path
    full_path = base / path
    
    # If it's a directory URL, add index.html
    if not path or not '.' in Path(path).name or path.endswith('/'):
        full_path = full_path / 'index.html'
    
    return full_path


async def get_conferences_to_scrape(
    pool: asyncpg.Pool,
    args: argparse.Namespace
) -> List[ConferenceToScrape]:
    """Get list of conferences to scrape."""
    query = """
        SELECT id, venue, year, archive_pc_url, archive_organizers_url, archive_steering_url
        FROM conferences
        WHERE (archive_pc_url IS NOT NULL 
               OR archive_organizers_url IS NOT NULL 
               OR archive_steering_url IS NOT NULL)
    """
    params = []
    
    if args.venue and args.venue.lower() != 'all':
        query += " AND venue = $1"
        params.append(args.venue.upper())
    
    if args.year:
        param_num = len(params) + 1
        query += f" AND year = ${param_num}"
        params.append(args.year)
    
    query += " ORDER BY year DESC, venue"
    
    rows = await pool.fetch(query, *params)
    
    return [
        ConferenceToScrape(
            id=row['id'],
            venue=row['venue'],
            year=row['year'],
            archive_pc_url=row['archive_pc_url'],
            archive_organizers_url=row['archive_organizers_url'],
            archive_steering_url=row['archive_steering_url']
        )
        for row in rows
    ]


async def check_committee_exists(pool: asyncpg.Pool, conference_id: UUID) -> bool:
    """Check if committee data already exists for conference."""
    count = await pool.fetchval(
        "SELECT COUNT(*) FROM committee_roles WHERE conference_id = $1",
        conference_id
    )
    return count > 0


async def scrape_committee_page(
    url: str,
    args: argparse.Namespace,
    committee_type: str
) -> List[CommitteeMember]:
    """Scrape committee page and extract members."""
    logger.info(f"Scraping {committee_type} from: {url}")
    
    # Get HTML content
    if args.local:
        local_path = url_to_local_path(args, url)
        logger.info(f"Reading local file: {local_path}")
        
        if not local_path.exists():
            raise FileNotFoundError(f"Local file not found: {local_path}")
        
        html_content = local_path.read_text(encoding='utf-8', errors='ignore')
    else:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as response:
                html_content = await response.text()
    
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Parse committee members
    return parse_committee_members(soup, committee_type)


def parse_committee_members(soup: BeautifulSoup, committee_type: str) -> List[CommitteeMember]:
    """Parse committee members from HTML."""
    members = []
    
    # Define section header patterns
    section_patterns = {
        'PC': ['program committee', 'pc members', 'programme committee'],
        'OC': ['organizing committee', 'organising committee', 'local organizing committee',
               'local organising committee', 'organization', 'organisers', 'organizers'],
        'SC': ['steering committee', 'sc members']
    }.get(committee_type, [])
    
    logger.info(f"Looking for section matching: {section_patterns}")
    
    # Try section-based parsing
    section_members = parse_section_based(soup, section_patterns, committee_type)
    if section_members:
        logger.info(f"Found {len(section_members)} members using section-based parsing")
        return section_members
    
    # Try specific selectors
    specific_selectors = [
        '.committee-member', '.person', '.team-member',
        'div.member', 'div.speaker'
    ]
    
    for selector in specific_selectors:
        elements = soup.select(selector)
        if elements:
            logger.info(f"Using specific selector: {selector} ({len(elements)} elements)")
            for element in elements:
                text = element.get_text(' ', strip=True)
                
                if len(text) < 3 or len(text) > 300:
                    continue
                
                member = parse_member_entry(text, committee_type)
                if member:
                    members.append(member)
            
            if members:
                members = deduplicate_members(members)
                return members
    
    # Generic selectors
    logger.info("Trying generic list selectors")
    generic_selectors = ['ul li', 'div.content p', 'article p']
    
    for selector in generic_selectors:
        for element in soup.select(selector):
            text = element.get_text(' ', strip=True)
            
            if len(text) < 3 or len(text) > 300:
                continue
            
            member = parse_member_entry(text, committee_type)
            if member:
                members.append(member)
    
    members = deduplicate_members(members)
    
    if not members:
        logger.warning("No committee members found")
    
    return members


def parse_section_based(
    soup: BeautifulSoup,
    section_patterns: List[str],
    committee_type: str
) -> Optional[List[CommitteeMember]]:
    """Parse using heading-based sections."""
    headings = soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6'])
    
    for idx, heading in enumerate(headings):
        heading_text = heading.get_text().lower()
        
        # Check if this heading matches any pattern
        if any(pattern in heading_text for pattern in section_patterns):
            logger.info(f"Found section header: '{heading.get_text().strip()}'")
            
            # Find next heading at same or higher level
            heading_level = int(heading.name[1])
            next_heading = None
            
            for h in headings[idx + 1:]:
                next_level = int(h.name[1])
                if next_level <= heading_level:
                    next_heading = h
                    break
            
            members = extract_members_between_headings(
                soup, heading, next_heading, committee_type
            )
            
            if members:
                logger.info(f"Found {len(members)} members using section-based parsing")
                return members
    
    return None


def extract_members_between_headings(
    soup: BeautifulSoup,
    start_heading,
    end_heading,
    committee_type: str
) -> List[CommitteeMember]:
    """Extract members between two headings by traversing siblings."""
    members = []
    
    # Start from the heading and iterate through siblings
    current = start_heading
    
    while current:
        # Get next sibling
        current = current.next_sibling
        
        # Stop if we reach the end heading
        if current == end_heading:
            break
        
        # Skip text nodes
        if not hasattr(current, 'name'):
            continue
        
        # Stop if we hit another h2 (major section boundary)
        if current.name == 'h2':
            break
        
        # Process member containers
        # Check if current element contains a section.members (might be nested in p, div, etc.)
        member_section = None
        if current.name == 'section' and 'members' in current.get('class', []):
            member_section = current
        else:
            # Look for section.members inside this element (e.g., <p><section class=members>)
            member_section = current.find('section', class_='members', recursive=False)
        
        if member_section:
            # Extract from fancy member cards in <section class="members">
            # Structure: <li><div class=label><h3>Name</h3><h4>Affiliation</h4>...<h4>Role</h4>
            member_list = member_section.find('ul', class_='members')
            if member_list:
                for li in member_list.find_all('li', recursive=False):
                    # Try to extract structured data from HTML tags
                    label = li.find('div', class_='label')
                    if label:
                        # Extract name from h3
                        h3 = label.find('h3')
                        name = h3.get_text(strip=True) if h3 else None
                        
                        # Extract affiliation and role from h4 tags
                        h4_tags = label.find_all('h4')
                        affiliation = None
                        role_text = ''
                        
                        for h4 in h4_tags:
                            h4_text = h4.get_text(strip=True)
                            # Role indicators usually contain these keywords
                            if any(kw in h4_text.lower() for kw in ['chair', 'member', 'co-chair', 'area chair', 'support']):
                                role_text = h4_text
                            elif not affiliation:  # First non-role h4 is likely affiliation
                                affiliation = h4_text
                        
                        if name:
                            # Detect position from role text
                            position, role_title = detect_position(name, role_text, role_text)
                            
                            member = CommitteeMember(
                                name=clean_name(name),
                                committee=committee_type,
                                position=position,
                                role_title=role_title,
                                affiliation=affiliation
                            )
                            members.append(member)
                    else:
                        # Fallback to text extraction for non-structured cards
                        text = li.get_text(' ', strip=True)
                        if 3 <= len(text) <= 300:
                            member = parse_member_entry(text, committee_type)
                            if member:
                                members.append(member)
        
        elif current.name == 'ul':
            # Check if this is a member list (not navigation, socials, etc.)
            ul_classes = current.get('class', [])
            if 'menu' not in ul_classes and 'social' not in ul_classes and 'socials' not in ul_classes:
                # Plain list - extract members
                for li in current.find_all('li', recursive=False):
                    text = li.get_text(' ', strip=True)
                    if 3 <= len(text) <= 300:
                        member = parse_member_entry(text, committee_type)
                        if member:
                            members.append(member)
    
    return deduplicate_members(members)


def parse_member_entry(text: str, committee_type: str) -> Optional[CommitteeMember]:
    """Parse a single member entry."""
    text_lower = text.lower()
    
    # Blacklist - only filter if the whole text is mostly blacklisted content
    blacklist_primary = [
        'accepted papers', 'call for papers', 'code of conduct', 'charter',
        'schedule', 'speakers', 'poster', 'pictures', 'sponsors', 'partners',
        'proceedings', 'registration', 'venue', 'travel',
        'accommodation', 'contact', 'about', 'home', 'news', 'archive',
        'previous', 'next', 'program', 'tutorials', 'workshops',
        'members only', 'login', 'logout', 'search',
    ]
    
    # Navigation items - filter more aggressively
    blacklist_nav = [
        'twitter', 'youtube', 'linkedin', 'facebook', 'instagram',
        'steering committee', 'program committee', 'organizing committee',
        'general chairs', 'program chairs', 'local arrangements'
    ]
    
    # Check if this is just a navigation/header item (exact match or very short)
    for item in blacklist_nav:
        if item in text_lower and len(text) < 100:
            # But allow if it looks like a person's entry (has capitalized words)
            words = text.split()
            if len(words) >= 2 and any(w[0].isupper() for w in words if w):
                continue
            return None
    
    # Check for purely non-person content
    for item in blacklist_primary:
        if item == text_lower or (item in text_lower and len(text) < 30):
            return None
    
    # Skip all caps or URLs
    if text.isupper() or 'http://' in text or 'https://' in text or 'www.' in text:
        return None
    
    # Must have alphabetic characters
    alpha_count = sum(c.isalpha() for c in text)
    if alpha_count < 3:
        return None
    
    # Must have multiple words
    word_count = len(text.split())
    if word_count < 2 and '(' not in text:
        return None
    
    # Extract name, affiliation, role
    name, affiliation, role_info = extract_name_affiliation_role(text)
    
    # Validate name
    if len(name) < 3 or len(name) > 100:
        return None
    
    if name == name.lower() or name == name.upper():
        return None
    
    # Detect position
    position, role_title = detect_position(name, text, role_info)
    
    return CommitteeMember(
        name=clean_name(name),
        committee=committee_type,
        position=position,
        role_title=role_title,
        affiliation=affiliation
    )


def extract_name_affiliation_role(text: str) -> Tuple[str, Optional[str], str]:
    """Extract name, affiliation, and role information."""
    name = ''
    affiliation = None
    role_info = ''
    
    # Institutional keywords that mark the start of affiliation
    institution_keywords = {
        'university', 'institute', 'college', 'laboratory', 'center', 'centre',
        'school', 'department', 'lab', 'research', 'academy', 'national',
        'ministry', 'agency', 'corporation', 'company', 'foundation', 'society',
        'organization', 'organisation', 'consortium', 'jpmorgan', 'amazon',
        'google', 'microsoft', 'ibm', 'aws', 'ntt', 'cesga', 'cnrs', 'inria',
        'eth', 'mit', 'caltech', 'weizmann', 'fraunhofer', 'hhh', 'iis'
    }
    
    # Pattern: "Name University/Company Site role"
    if ' Site ' in text:
        parts = text.split(' Site ', 1)
        before_site = parts[0]
        after_site = parts[1] if len(parts) > 1 else ''
        
        words = before_site.split()
        
        # Find where affiliation starts (first institutional keyword)
        # Also handle cases like "New York University" where "New York" precedes the keyword
        affiliation_start = None
        for i in range(1, len(words)):  # Start from index 1 (at least one word for name)
            if words[i].lower() in institution_keywords:
                affiliation_start = i
                # Check if previous word(s) are common location/institution prefixes
                if i > 2:  # At least 3 words before (name + location prefix)
                    prev_word = words[i-1].lower()
                    if prev_word in {'new', 'york', 'hong', 'kong', 'san', 'los', 'tel', 'aviv', 'rio', 'cape', 'town', 'mexico', 'city'}:
                        affiliation_start = i - 1
                        # Handle two-word prefixes like "New York", "Hong Kong", "San Francisco"
                        if i > 3 and words[i-2].lower() in {'new', 'san', 'hong', 'tel', 'rio', 'cape'}:
                            affiliation_start = i - 2
                break
        
        if affiliation_start is None:
            # No institution keyword found, assume first 2-3 words are name
            # (for cases like "Li Qian Toronto")
            name_word_count = min(3, len(words))
            # Stop at first lowercase word
            for i in range(1, min(4, len(words))):
                if words[i] and not words[i][0].isupper():
                    name_word_count = i
                    break
        else:
            # Name is everything before the institution keyword
            name_word_count = affiliation_start
        
        name = ' '.join(words[:name_word_count])
        
        if name_word_count < len(words):
            affiliation = ' '.join(words[name_word_count:])
        
        role_info = after_site
    
    # Pattern: "Name (Affiliation)"
    elif '(' in text and ')' in text:
        parts = text.split('(', 1)
        name = parts[0].strip()
        
        rest = parts[1]
        end_paren = rest.find(')')
        if end_paren != -1:
            in_parens = rest[:end_paren]
            
            # Check if it's a role or affiliation
            if 'chair' in in_parens.lower() or 'member' in in_parens.lower():
                role_info = in_parens
            else:
                affiliation = in_parens
            
            after_parens = rest[end_paren + 1:].strip()
            if after_parens:
                role_info += ' ' + after_parens
    
    # Pattern: "Name - Affiliation"
    elif ' - ' in text or ' – ' in text:
        separator = ' - ' if ' - ' in text else ' – '
        parts = text.split(separator, 1)
        name = parts[0].strip()
        
        rest = parts[1] if len(parts) > 1 else ''
        rest_lower = rest.lower()
        
        if 'chair' in rest_lower or 'member' in rest_lower or 'organizer' in rest_lower:
            role_info = rest
        else:
            affiliation = rest
    
    # Pattern: "Name, Affiliation"
    elif ',' in text:
        parts = text.split(',', 1)
        name = parts[0].strip()
        
        rest = parts[1].strip() if len(parts) > 1 else ''
        rest_lower = rest.lower()
        
        if 'chair' in rest_lower or 'member' in rest_lower or 'organizer' in rest_lower:
            role_info = rest
        else:
            affiliation = rest
    
    # Default: just the name
    else:
        name = text
        role_info = text
    
    return name, affiliation, role_info


def detect_position(name: str, full_text: str, role_info: str) -> Tuple[str, Optional[str]]:
    """Detect position from text."""
    combined = f"{full_text} {role_info}".lower()
    
    if 'general chair' in combined or 'conference chair' in combined:
        return 'chair', 'General Chair'
    elif 'program chair' in combined or 'pc chair' in combined or 'pc primary chair' in combined:
        return 'chair', 'Program Chair'
    elif 'steering chair' in combined or 'sc chair' in combined:
        return 'chair', 'Steering Chair'
    elif 'local chair' in combined:
        return 'chair', 'Local Chair'
    elif 'co-chair' in combined or 'cochair' in combined or 'pc co-chair' in combined:
        return 'co_chair', None
    elif 'area chair' in combined or 'senior pc' in combined:
        return 'area_chair', None
    elif 'chair' in combined:
        return 'chair', None
    else:
        return 'member', None


def clean_name(name: str) -> str:
    """Clean and normalize name."""
    return ' '.join(name.split())


def deduplicate_members(members: List[CommitteeMember]) -> List[CommitteeMember]:
    """Remove duplicate members."""
    seen = {}
    result = []
    
    for member in sorted(members, key=lambda m: m.name):
        normalized = normalize_name(member.name)
        if normalized not in seen:
            seen[normalized] = True
            result.append(member)
    
    return result


async def get_or_create_author(
    pool: asyncpg.Pool,
    name: str,
    affiliation: Optional[str]
) -> UUID:
    """Get or create author record."""
    normalized = normalize_name(name)
    
    # Try to find existing
    existing = await pool.fetchval(
        "SELECT id FROM authors WHERE normalized_name = $1",
        normalized
    )
    
    if existing:
        logger.info(f"Found existing author: {name} ({existing})")
        return existing
    
    # Create new
    author_id = uuid4()
    
    metadata = {'affiliation': affiliation} if affiliation else {}
    
    await pool.execute(
        """INSERT INTO authors (id, full_name, normalized_name, affiliation, metadata, created_at, updated_at, creator, modifier)
           VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)""",
        author_id, name, normalized, affiliation, json.dumps(metadata),
        datetime.utcnow(), datetime.utcnow(), 'scraper', 'scraper'
    )
    
    logger.info(f"Created new author: {name} ({author_id})")
    return author_id


async def insert_committee_role(
    pool: asyncpg.Pool,
    conference_id: UUID,
    author_id: UUID,
    committee: str,
    position: str,
    role_title: Optional[str]
) -> None:
    """Insert committee role."""
    role_id = uuid4()
    metadata = {'role_title': role_title} if role_title else {}
    
    await pool.execute(
        """INSERT INTO committee_roles (id, conference_id, author_id, committee, position, metadata, created_at, updated_at, creator, modifier)
           VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
           ON CONFLICT (conference_id, author_id, committee, position) 
           DO UPDATE SET metadata = EXCLUDED.metadata, updated_at = EXCLUDED.updated_at, modifier = 'scraper'""",
        role_id, conference_id, author_id, committee, position,
        json.dumps(metadata), datetime.utcnow(), datetime.utcnow(), 'scraper', 'scraper'
    )


async def insert_committee_members(
    pool: asyncpg.Pool,
    conference_id: UUID,
    members: List[CommitteeMember]
) -> None:
    """Insert all committee members."""
    for member in members:
        author_id = await get_or_create_author(pool, member.name, member.affiliation)
        await insert_committee_role(
            pool, conference_id, author_id,
            member.committee, member.position, member.role_title
        )
    
    logger.info(f"Inserted {len(members)} committee members")


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Scrape committee membership data from archived conference websites'
    )
    parser.add_argument('-v', '--venue', help='Conference venue (QIP, QCRYPT, TQC, or all)')
    parser.add_argument('-y', '--year', type=int, help='Specific conference year')
    parser.add_argument('--dry-run', action='store_true', help="Don't commit to database")
    parser.add_argument('--force', action='store_true', help='Force re-scrape even if data exists')
    parser.add_argument('--local', action='store_true', help='Use local files from ~/Web/')
    parser.add_argument('--local-dir', type=str, help='Custom local web directory')
    
    args = parser.parse_args()
    
    # Load environment
    load_dotenv()
    
    # Validate local directory
    if args.local:
        local_dir = get_local_dir(args)
        if not local_dir.exists():
            raise FileNotFoundError(f"Local directory does not exist: {local_dir}")
        logger.info(f"Using local files from: {local_dir}")
    
    # Connect to database
    database_url = os.environ.get('DATABASE_URL')
    if not database_url:
        raise ValueError("DATABASE_URL must be set")
    
    pool = await asyncpg.create_pool(database_url)
    
    try:
        logger.info("Connected to database")
        
        # Get conferences
        conferences = await get_conferences_to_scrape(pool, args)
        
        if not conferences:
            logger.info("No conferences found matching criteria")
            return
        
        logger.info(f"Found {len(conferences)} conference(s) to scrape")
        
        # Process each conference
        for conf in conferences:
            logger.info(f"\n=== Processing {conf.venue} {conf.year} ===")
            
            # Check if should skip
            if not args.force:
                exists = await check_committee_exists(pool, conf.id)
                if exists:
                    logger.info(f"Committee data already exists for {conf.venue} {conf.year}. Use --force to re-scrape.")
                    continue
            
            # Scrape Program Committee
            if conf.archive_pc_url:
                try:
                    members = await scrape_committee_page(conf.archive_pc_url, args, 'PC')
                    logger.info(f"Found {len(members)} PC members")
                    
                    if args.dry_run:
                        for member in members:
                            logger.info(f"  - {member.name} ({member.affiliation or '?'}) [{member.position}]")
                    else:
                        await insert_committee_members(pool, conf.id, members)
                except Exception as e:
                    logger.warning(f"Failed to scrape PC: {e}")
            
            # Scrape Organizing Committee
            if conf.archive_organizers_url:
                try:
                    members = await scrape_committee_page(conf.archive_organizers_url, args, 'OC')
                    logger.info(f"Found {len(members)} OC members")
                    
                    if args.dry_run:
                        for member in members:
                            logger.info(f"  - {member.name} ({member.affiliation or '?'}) [{member.position}]")
                    else:
                        await insert_committee_members(pool, conf.id, members)
                except Exception as e:
                    logger.warning(f"Failed to scrape OC: {e}")
            
            # Scrape Steering Committee
            if conf.archive_steering_url:
                try:
                    members = await scrape_committee_page(conf.archive_steering_url, args, 'SC')
                    logger.info(f"Found {len(members)} SC members")
                    
                    if args.dry_run:
                        for member in members:
                            logger.info(f"  - {member.name} ({member.affiliation or '?'}) [{member.position}]")
                    else:
                        await insert_committee_members(pool, conf.id, members)
                except Exception as e:
                    logger.warning(f"Failed to scrape SC: {e}")
        
        logger.info("\nScraping complete!")
    
    finally:
        await pool.close()


if __name__ == '__main__':
    asyncio.run(main())
