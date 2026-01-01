#!/usr/bin/env python3
"""Scrape committee data and save to CSV file for manual verification."""

import argparse
import asyncio
import csv
import logging
import os
import sys
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime
from urllib.parse import unquote

import asyncpg
from dotenv import load_dotenv

# Add scrapers directory to path
sys.path.insert(0, str(Path(__file__).parent))
from scrapers import QCryptScraper, QIPScraper, TQCScraper


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def get_scraper_class(venue: str):
    """Get the appropriate scraper class for the venue."""
    venue_upper = venue.upper()
    if venue_upper == 'QCRYPT':
        return QCryptScraper
    elif venue_upper == 'QIP':
        return QIPScraper
    elif venue_upper == 'TQC':
        return TQCScraper
    else:
        raise ValueError(f"Unknown venue: {venue}")


def save_to_csv(
    venue: str,
    year: int,
    members: List[Dict[str, str]],
    output_dir: Path,
    force: bool = False
) -> Path:
    """Save scraped data to CSV file."""
    output_dir.mkdir(parents=True, exist_ok=True)
    
    filename = f"{venue.lower()}_{year}_committees.csv"
    output_file = output_dir / filename
    
    if output_file.exists() and not force:
        logger.warning(f"Output file already exists: {output_file}")
        logger.warning("Use --force to overwrite")
        return None
    
    # Add venue and year to each member record
    for member in members:
        member['venue'] = venue.upper()
        member['year'] = year
    
    # Write CSV
    fieldnames = ['venue', 'year', 'committee_type', 'position', 'full_name', 'affiliation', 'notes']
    
    with open(output_file, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(members)
    
    logger.info(f"Saved {len(members)} members to {output_file}")
    return output_file


def url_to_local_path(url: str, local_dir: Path = None) -> Path:
    """Convert URL to local file path (similar to scrape_committees.py)."""
    if local_dir is None:
        local_dir = Path.home() / 'Web'
    
    # Decode URL-encoded characters (e.g., %3F -> ?, %3D -> =)
    url = unquote(url)
    
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


async def get_conference_archive_url(venue: str, year: int) -> Optional[str]:
    """Get archive URL from database for the given conference."""
    load_dotenv()
    database_url = os.environ.get('DATABASE_URL')
    
    if not database_url:
        logger.warning("DATABASE_URL not set, will use scraper's default URL")
        return None
    
    try:
        conn = await asyncpg.connect(database_url)
        try:
            # Query for the conference archive URLs
            row = await conn.fetchrow(
                """
                SELECT archive_pc_url, archive_organizers_url 
                FROM conferences 
                WHERE venue = $1 AND year = $2
                """,
                venue.upper(),
                year
            )
            
            if row:
                # Prefer PC URL, fall back to organizers URL
                url = row['archive_pc_url'] or row['archive_organizers_url']
                if url:
                    logger.info(f"Found archive URL in database: {url}")
                    return url
                else:
                    logger.warning(f"Conference found but no archive URLs set for {venue} {year}")
            else:
                logger.warning(f"Conference {venue} {year} not found in database")
            
            return None
        finally:
            await conn.close()
    except Exception as e:
        logger.warning(f"Error querying database: {e}. Will use scraper's default URL.")
        return None


def main():
    """Main scraper function (synchronous wrapper)."""
    return asyncio.run(async_main())


async def async_main():
    """Main scraper function."""
    parser = argparse.ArgumentParser(
        description='Scrape conference committee data to JSON file'
    )
    parser.add_argument('--venue', required=True, choices=['QCRYPT', 'QIP', 'TQC'],
                       help='Conference venue')
    parser.add_argument('--year', type=int, required=True,
                       help='Conference year')
    parser.add_argument('--local', action='store_true',
                       help='Use local HTML file instead of fetching from web')
    parser.add_argument('--local-file', type=str,
                       help='Path to local HTML file (overrides default local path)')
    parser.add_argument('--local-dir', type=str,
                       help='Base directory for local files (default: ~/Web)')
    parser.add_argument('--output-dir', type=str, default='./scraped_data',
                       help='Output directory for JSON files (default: ./scraped_data)')
    parser.add_argument('--force', action='store_true',
                       help='Overwrite existing output file')
    
    args = parser.parse_args()
    
    # Get the archive URL from database first, fall back to scraper's default
    url = await get_conference_archive_url(args.venue, args.year)
    
    if not url:
        # Fall back to scraper's hardcoded URL
        logger.info("Using scraper's default URL")
        try:
            scraper_class = get_scraper_class(args.venue)
            temp_scraper = scraper_class(year=args.year)
            url = temp_scraper.get_url()
        except ValueError as e:
            logger.error(str(e))
            return 1
    
    # Determine local file path if using local mode
    local_file = None
    if args.local:
        if args.local_file:
            local_file = args.local_file
        else:
            # Use the URL to determine local path
            local_dir = Path(args.local_dir) if args.local_dir else Path.home() / 'Web'
            local_file = url_to_local_path(url, local_dir)
        
        if not Path(local_file).exists():
            logger.error(f"Local file not found: {local_file}")
            return 1
        
        logger.info(f"Using local file: {local_file}")
    
    # Create the scraper with local file if specified
    try:
        scraper_class = get_scraper_class(args.venue)
        scraper = scraper_class(year=args.year, local_file=local_file)
    except ValueError as e:
        logger.error(str(e))
        return 1
    
    # Scrape data
    try:
        logger.info(f"Scraping {args.venue} {args.year} committee data...")
        members = scraper.scrape()
        logger.info(f"Found {len(members)} committee members")
        
        if not members:
            logger.warning("No members found. Check the HTML structure and scraper implementation.")
            return 1
        
        # Show sample
        logger.info(f"Sample member: {members[0]}")
        
    except NotImplementedError as e:
        logger.error(str(e))
        logger.info("Hint: Customize the scraper for this conference/year in scrapers/ directory")
        return 1
    except Exception as e:
        logger.error(f"Error scraping: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    # Save to file
    try:
        output_dir = Path(args.output_dir)
        output_file = save_to_csv(args.venue, args.year, members, output_dir, args.force)
        
        if output_file:
            logger.info(f"✓ Successfully saved committee data for {args.venue} {args.year}")
            logger.info(f"Review the data in: {output_file}")
            logger.info("After verification, you can import using import_from_csv.py")
            return 0
        else:
            return 1
        
    except Exception as e:
        logger.error(f"Error saving file: {e}")
        return 1


if __name__ == '__main__':
    exit_code = main()
    sys.exit(exit_code)
