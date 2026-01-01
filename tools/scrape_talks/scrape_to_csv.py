#!/usr/bin/env python3
"""Scrape invited/tutorial talk data and save to CSV file for manual verification."""

import argparse
import asyncio
import csv
import logging
import os
import sys
from pathlib import Path
from typing import List, Dict, Optional, Any
from datetime import datetime
from urllib.parse import unquote

import asyncpg
from dotenv import load_dotenv

# Add scrapers directory to path
sys.path.insert(0, str(Path(__file__).parent))
from scrapers import QCryptTalkScraper, QIPTalkScraper, TQCTalkScraper


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def get_scraper_class(venue: str):
    """Get the appropriate scraper class for the venue."""
    venue_upper = venue.upper()
    if venue_upper == 'QCRYPT':
        return QCryptTalkScraper
    elif venue_upper == 'QIP':
        return QIPTalkScraper
    elif venue_upper == 'TQC':
        return TQCTalkScraper
    else:
        raise ValueError(f"Unknown venue: {venue}")


def serialize_list(items: Optional[List[str]]) -> str:
    """Convert list to semicolon-separated string."""
    if not items:
        return ''
    return ';'.join(str(item) for item in items if item)


def save_to_csv(
    venue: str,
    year: int,
    talks: List[Dict[str, Any]],
    output_dir: Path,
    force: bool = False
) -> Optional[Path]:
    """Save scraped talks to CSV file."""
    output_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{venue.lower()}_{year}_talks.csv"
    output_file = output_dir / filename

    if output_file.exists() and not force:
        logger.warning(f"Output file already exists: {output_file}")
        logger.warning("Use --force to overwrite")
        return None

    # Add venue and year to each talk record and serialize lists
    for talk in talks:
        talk['venue'] = venue.upper()
        talk['year'] = year

        # Serialize list fields
        for list_field in ['speakers', 'authors', 'affiliations', 'arxiv_ids']:
            if list_field in talk and isinstance(talk[list_field], list):
                talk[list_field] = serialize_list(talk[list_field])

    # Write CSV
    fieldnames = [
        'venue', 'year', 'paper_type', 'title', 'speakers', 'authors',
        'affiliations', 'abstract', 'arxiv_ids', 'presentation_url',
        'video_url', 'youtube_id', 'session_name', 'award', 'notes'
    ]

    with open(output_file, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(talks)

    logger.info(f"Saved {len(talks)} talks to {output_file}")

    # Show sample of what was scraped
    if talks:
        logger.info("\nSample talks:")
        for talk in talks[:3]:
            logger.info(f"  {talk.get('paper_type', 'unknown')}: {talk.get('title', 'N/A')[:80]}")
            if talk.get('speakers'):
                speakers_str = talk['speakers'] if isinstance(talk['speakers'], str) else serialize_list(talk['speakers'])
                logger.info(f"    Speakers: {speakers_str}")

    return output_file


def url_to_local_path(url: str, local_dir: Path = None) -> Path:
    """Convert URL to local file path."""
    if local_dir is None:
        local_dir = Path.home() / 'Web'

    # Decode URL-encoded characters
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


async def get_conference_archive_program_url(venue: str, year: int) -> Optional[str]:
    """Get archive program URL from database for the given conference."""
    load_dotenv()
    database_url = os.environ.get('DATABASE_URL')

    if not database_url:
        logger.warning("DATABASE_URL not set, will use scraper's default URL")
        return None

    try:
        conn = await asyncpg.connect(database_url)
        try:
            # Query for the conference archive program URL
            row = await conn.fetchrow(
                """
                SELECT archive_program_url
                FROM conferences
                WHERE venue = $1 AND year = $2
                """,
                venue.upper(),
                year
            )

            if row and row['archive_program_url']:
                url = row['archive_program_url']
                logger.info(f"Found archive program URL in database: {url}")
                return url
            elif row:
                logger.warning(f"Conference found but no archive_program_url set for {venue} {year}")
            else:
                logger.warning(f"Conference {venue} {year} not found in database")

            return None
        finally:
            await conn.close()
    except Exception as e:
        logger.warning(f"Error querying database: {e}. Will use scraper's default URL.")
        return None


async def async_main():
    """Main CLI function."""
    parser = argparse.ArgumentParser(
        description='Scrape invited/tutorial talks from conference program pages to CSV'
    )
    parser.add_argument('--venue', required=True, choices=['QCRYPT', 'QIP', 'TQC'],
                       help='Conference venue')
    parser.add_argument('--year', type=int, required=True,
                       help='Conference year')
    parser.add_argument('--local', action='store_true',
                       help='Use local HTML file instead of fetching from web')
    parser.add_argument('--local-file', type=str,
                       help='Explicit path to local HTML file')
    parser.add_argument('--local-dir', type=str, default='~/Web',
                       help='Base directory for local files (default: ~/Web)')
    parser.add_argument('--output-dir', type=str, default='./scraped_data',
                       help='Output directory for CSV files')
    parser.add_argument('--force', action='store_true',
                       help='Overwrite existing CSV file')

    args = parser.parse_args()

    # Expand ~ in paths
    local_dir = Path(args.local_dir).expanduser()
    output_dir = Path(args.output_dir)

    # Get program URL from database or use default
    archive_url = await get_conference_archive_program_url(args.venue, args.year)

    # Determine local file path if using local mode
    local_file = None
    if args.local:
        if args.local_file:
            local_file = args.local_file
        elif archive_url:
            local_file = url_to_local_path(archive_url, local_dir)
        else:
            # Fallback: create scraper to get default URL
            scraper_class = get_scraper_class(args.venue)
            temp_scraper = scraper_class(year=args.year)
            try:
                default_url = temp_scraper.get_url()
                local_file = url_to_local_path(default_url, local_dir)
            except NotImplementedError:
                logger.error(f"No default URL for {args.venue} {args.year} and no archive URL in database")
                sys.exit(1)

        if local_file:
            logger.info(f"Using local file: {local_file}")
            if not Path(local_file).exists():
                logger.error(f"Local file not found: {local_file}")
                sys.exit(1)

    # Create scraper and fetch data
    try:
        scraper_class = get_scraper_class(args.venue)
        scraper = scraper_class(year=args.year, local_file=local_file)

        logger.info(f"Scraping {args.venue} {args.year} talks...")
        talks = scraper.scrape()

        if not talks:
            logger.warning("No talks found! The scraper may need customization for this year's HTML structure.")
            logger.warning("Consider:")
            logger.warning("  1. Check the HTML structure of the program page")
            logger.warning("  2. Update the scraper parsing logic in scrapers/{}.py".format(args.venue.lower()))
            logger.warning("  3. Try manually creating a CSV file as a template")

        # Save to CSV
        output_file = save_to_csv(
            args.venue,
            args.year,
            talks,
            output_dir,
            force=args.force
        )

        if output_file:
            logger.info(f"\n✓ Successfully scraped {len(talks)} talks")
            logger.info(f"✓ Saved to: {output_file}")
            logger.info("\nNext steps:")
            logger.info(f"  1. Review and edit: {output_file}")
            logger.info(f"  2. Import to database: ./import_from_csv.py {output_file}")

    except NotImplementedError as e:
        logger.error(f"Scraper not implemented: {e}")
        logger.error("This year/venue combination requires custom scraper implementation.")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Error during scraping: {e}", exc_info=True)
        sys.exit(1)


def main():
    """Entry point for CLI."""
    asyncio.run(async_main())


if __name__ == '__main__':
    main()
