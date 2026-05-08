"""CLI body for `scrape_to_csv.py committees` — fetch committee CSVs."""
import argparse
import csv
import logging
from pathlib import Path
from typing import Dict, List

from .._lib import get_archive_url, url_to_local_path
from . import QCryptScraper, QIPScraper, TQCScraper

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
DEFAULT_OUTPUT_DIR = REPO_ROOT / "data" / "conferences"

_VENUES = {
    'QCRYPT': QCryptScraper,
    'QIP': QIPScraper,
    'TQC': TQCScraper,
}


def save_to_csv(venue: str, year: int, members: List[Dict[str, str]],
                output_dir: Path, force: bool = False) -> Path:
    """Save scraped data to ``<output_dir>/<venue>_<year>/committees.csv``."""
    conference_dir = output_dir / f"{venue.lower()}_{year}"
    conference_dir.mkdir(parents=True, exist_ok=True)

    output_file = conference_dir / "committees.csv"

    if output_file.exists() and not force:
        logger.warning(f"Output file already exists: {output_file}")
        logger.warning("Use --force to overwrite")
        return None

    for member in members:
        member['venue'] = venue.upper()
        member['year'] = year

    fieldnames = ['venue', 'year', 'committee_type', 'position',
                  'full_name', 'affiliation', 'role_title']

    with open(output_file, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(members)

    logger.info(f"Saved {len(members)} members to {output_file}")
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
                        help='Path to local HTML file (overrides default local path)')
    parser.add_argument('--local-dir', type=str,
                        help='Base directory for local files (default: ~/Web)')
    parser.add_argument('--output-dir', type=str, default=str(DEFAULT_OUTPUT_DIR),
                        help=f'Output directory; CSV is written to <output-dir>/<venue>_<year>/committees.csv (default: {DEFAULT_OUTPUT_DIR})')
    parser.add_argument('--force', action='store_true',
                        help='Overwrite existing output file')


async def async_main(args: argparse.Namespace) -> int:
    """Run the committee scrape end-to-end. Returns shell exit code."""
    url = await get_archive_url(args.venue, args.year,
                                ['archive_pc_url', 'archive_organizers_url'])
    scraper_class = _VENUES[args.venue.upper()]

    if not url:
        logger.info("Using scraper's default URL")
        try:
            url = scraper_class(year=args.year).get_url()
        except NotImplementedError as e:
            logger.error(str(e))
            return 1

    local_file = None
    if args.local:
        if args.local_file:
            local_file = args.local_file
        else:
            local_dir = Path(args.local_dir).expanduser() if args.local_dir else Path.home() / 'Web'
            local_file = url_to_local_path(url, local_dir)

        if not Path(local_file).exists():
            logger.error(f"Local file not found: {local_file}")
            return 1

        logger.info(f"Using local file: {local_file}")

    try:
        scraper = scraper_class(year=args.year, local_file=local_file)
        logger.info(f"Scraping {args.venue} {args.year} committee data...")
        members = scraper.scrape()
        logger.info(f"Found {len(members)} committee members")

        if not members:
            logger.warning("No members found. Check the HTML structure and scraper implementation.")
            return 1

        logger.info(f"Sample member: {members[0]}")
    except NotImplementedError as e:
        logger.error(str(e))
        logger.info("Hint: Customize the scraper for this conference/year in scrapers/committees/")
        return 1
    except Exception as e:
        logger.error(f"Error scraping: {e}")
        import traceback
        traceback.print_exc()
        return 1

    try:
        output_dir = Path(args.output_dir)
        output_file = save_to_csv(args.venue, args.year, members, output_dir, args.force)
        if not output_file:
            return 1

        logger.info(f"✓ Successfully saved committee data for {args.venue} {args.year}")
        logger.info(f"Review the data in: {output_file}")
        logger.info("After verification, you can import using import_from_csv.py")
        return 0
    except Exception as e:
        logger.error(f"Error saving file: {e}")
        return 1
