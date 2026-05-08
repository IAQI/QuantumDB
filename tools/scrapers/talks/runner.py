"""CLI body for `scrape_to_csv.py talks` — fetch talk CSVs."""
import argparse
import csv
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from .._lib import get_archive_url, url_to_local_path
from . import QCryptTalkScraper, QIPTalkScraper, TQCTalkScraper

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
DEFAULT_OUTPUT_DIR = REPO_ROOT / "data" / "conferences"

_VENUES = {
    'QCRYPT': QCryptTalkScraper,
    'QIP': QIPTalkScraper,
    'TQC': TQCTalkScraper,
}


def serialize_list(items: Optional[List[str]]) -> str:
    """Convert list to semicolon-separated string."""
    if not items:
        return ''
    return ';'.join(str(item) for item in items if item)


def save_to_csv(venue: str, year: int, talks: List[Dict[str, Any]],
                output_dir: Path, force: bool = False) -> Optional[Path]:
    """Save scraped talks to ``<output_dir>/<venue>_<year>/talks.csv``."""
    conference_dir = output_dir / f"{venue.lower()}_{year}"
    conference_dir.mkdir(parents=True, exist_ok=True)

    output_file = conference_dir / "talks.csv"

    if output_file.exists() and not force:
        logger.warning(f"Output file already exists: {output_file}")
        logger.warning("Use --force to overwrite")
        return None

    for talk in talks:
        talk['venue'] = venue.upper()
        talk['year'] = year
        for list_field in ['speakers', 'authors', 'affiliations', 'arxiv_ids']:
            if list_field in talk and isinstance(talk[list_field], list):
                talk[list_field] = serialize_list(talk[list_field])

    fieldnames = [
        'venue', 'year', 'paper_type', 'title', 'speakers', 'authors',
        'affiliations', 'abstract', 'arxiv_ids', 'presentation_url',
        'video_url', 'youtube_id', 'session_name', 'award', 'notes',
        'scheduled_date', 'scheduled_time', 'duration_minutes',
    ]

    with open(output_file, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(talks)

    logger.info(f"Saved {len(talks)} talks to {output_file}")

    if talks:
        logger.info("\nSample talks:")
        for talk in talks[:3]:
            logger.info(f"  {talk.get('paper_type', 'unknown')}: {talk.get('title', 'N/A')[:80]}")
            if talk.get('speakers'):
                speakers_str = talk['speakers'] if isinstance(talk['speakers'], str) else serialize_list(talk['speakers'])
                logger.info(f"    Speakers: {speakers_str}")

    return output_file


def add_arguments(parser: argparse.ArgumentParser) -> None:
    """Wire CLI flags onto ``parser``. Used by the unified entry point."""
    parser.add_argument('--venue', required=True, choices=list(_VENUES.keys()),
                        help='Conference venue')
    parser.add_argument('--year', type=int, required=True,
                        help='Conference year')
    parser.add_argument('--local', action='store_true',
                        help='Use local HTML file instead of fetching from web')
    parser.add_argument('--local-file', type=str,
                        help='Explicit path to local HTML file')
    parser.add_argument('--local-dir', type=str, default='~/Web',
                        help='Base directory for local files (default: ~/Web)')
    parser.add_argument('--output-dir', type=str, default=str(DEFAULT_OUTPUT_DIR),
                        help=f'Output directory; CSV is written to <output-dir>/<venue>_<year>/talks.csv (default: {DEFAULT_OUTPUT_DIR})')
    parser.add_argument('--force', action='store_true',
                        help='Overwrite existing CSV file')


async def async_main(args: argparse.Namespace) -> int:
    """Run the talk scrape end-to-end. Returns shell exit code."""
    local_dir = Path(args.local_dir).expanduser()
    output_dir = Path(args.output_dir)

    archive_url = await get_archive_url(args.venue, args.year, ['archive_program_url'])
    scraper_class = _VENUES[args.venue.upper()]

    local_file = None
    if args.local:
        if args.local_file:
            local_file = args.local_file
        elif archive_url:
            local_file = url_to_local_path(archive_url, local_dir)
        else:
            try:
                default_url = scraper_class(year=args.year).get_url()
                local_file = url_to_local_path(default_url, local_dir)
            except NotImplementedError:
                logger.error(f"No default URL for {args.venue} {args.year} and no archive URL in database")
                return 1

        if local_file:
            logger.info(f"Using local file: {local_file}")
            if not Path(local_file).exists():
                logger.error(f"Local file not found: {local_file}")
                return 1

    try:
        scraper = scraper_class(year=args.year, local_file=local_file)
        logger.info(f"Scraping {args.venue} {args.year} talks...")
        talks = scraper.scrape()

        if not talks:
            logger.warning("No talks found! The scraper may need customization for this year's HTML structure.")
            logger.warning("Consider:")
            logger.warning("  1. Check the HTML structure of the program page")
            logger.warning(f"  2. Update the scraper parsing logic in scrapers/talks/{args.venue.lower()}.py")
            logger.warning("  3. Try manually creating a CSV file as a template")

        output_file = save_to_csv(args.venue, args.year, talks, output_dir, force=args.force)

        if output_file:
            logger.info(f"\n✓ Successfully scraped {len(talks)} talks")
            logger.info(f"✓ Saved to: {output_file}")
            logger.info("\nNext steps:")
            logger.info(f"  1. Review and edit: {output_file}")
            logger.info(f"  2. Import to database: ./import_from_csv.py talks {output_file}")

        return 0
    except NotImplementedError as e:
        logger.error(f"Scraper not implemented: {e}")
        logger.error("This year/venue combination requires custom scraper implementation.")
        return 1
    except Exception as e:
        logger.error(f"Error during scraping: {e}", exc_info=True)
        return 1
