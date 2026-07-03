"""CLI body for `import_from_csv.py committees` — import committee CSVs into the DB."""

import csv
import logging
import os
import re
from pathlib import Path
from typing import Optional, Dict
from uuid import UUID

import asyncpg
from dotenv import load_dotenv

from scrapers._lib import clean_field, get_or_create_author


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def map_committee_type(committee_type: str) -> str:
    """Map CSV committee_type to database enum value."""
    mapping = {
        'program': 'PC',
        'steering': 'SC',
        'organizing': 'OC',
        'local_organizing': 'OC',  # legacy alias — merged into organizing
    }
    return mapping.get(committee_type, committee_type)


# role_title is a free-text label meant to add detail *beyond* committee+position
# (e.g. "Publicity Chair", "Rump Session Organizer"). Some scrapes/hand-edits instead
# wrote the position/committee word back into it ("Chair", "PC Member", "LO Co-Chair"),
# which is pure noise next to a table already grouped by committee+position. Drop those.
#
# This is a denylist of *rank/committee restatement* strings only. It deliberately does
# NOT touch titles that disagree with the position (e.g. position=member +
# "Technical Operations Chair") — those carry the real job the enum couldn't express.
REDUNDANT_ROLE_TITLES = {
    'chair', 'cochair', 'member', 'areachair',
    'pcchair', 'pccochair', 'pcmember',
    'scchair', 'sccochair', 'scmember',
    'occhair', 'occochair', 'ocmember',
    'lochair', 'locochair', 'lomember',
    'programchair', 'steeringchair', 'organizingchair', 'localchair',
}


def _is_redundant_role_title(title: Optional[str]) -> bool:
    """True if ``title`` merely restates the committee/position (see REDUNDANT_ROLE_TITLES)."""
    if not title:
        return False
    key = re.sub(r'[^a-z]', '', title.lower())
    return key in REDUNDANT_ROLE_TITLES


def map_position(position: str) -> str:
    """Map CSV position to database enum value."""
    if not position:
        return 'member'

    # Normalise hyphens to underscores so both the documented 'co_chair' and the
    # stray 'co-chair' spelling map to the co_chair enum (otherwise co_chair rows
    # silently fell through to 'member').
    position = position.lower().strip().replace('-', '_')
    mapping = {
        'chair': 'chair',
        'co_chair': 'co_chair',
        'area_chair': 'area_chair',
        'member': 'member'
    }
    return mapping.get(position, 'member')


async def get_conference_id(
    conn: asyncpg.Connection,
    venue: str,
    year: int
) -> Optional[UUID]:
    """Get conference ID."""
    return await conn.fetchval(
        "SELECT id FROM conferences WHERE venue = $1 AND year = $2",
        venue,
        year
    )


async def import_member(
    conn: asyncpg.Connection,
    venue: str,
    year: int,
    member: Dict[str, str]
) -> bool:
    """Import a single committee member."""
    
    # Get conference
    conference_id = await get_conference_id(conn, venue, year)
    if not conference_id:
        logger.error(f"Conference not found: {venue} {year}")
        return False
    
    # Normalise text fields (decode entities, fold odd whitespace)
    member['full_name'] = clean_field(member.get('full_name'))
    member['affiliation'] = clean_field(member.get('affiliation')) or None
    member['role_title'] = clean_field(member.get('role_title')) or None
    if _is_redundant_role_title(member['role_title']):
        logger.info(
            f"Dropping redundant role_title '{member['role_title']}' for "
            f"{member['full_name']} ({venue} {year})"
        )
        member['role_title'] = None

    # Get or create author
    author_id = await get_or_create_author(
        conn,
        member['full_name'],
        member.get('affiliation')
    )
    
    # Map values to database enums
    db_committee = map_committee_type(member['committee_type'])
    db_position = map_position(member.get('position'))
    
    # Check if committee role already exists
    existing = await conn.fetchval(
        """
        SELECT id FROM committee_roles
        WHERE conference_id = $1 AND author_id = $2 AND committee = $3
        """,
        conference_id,
        author_id,
        db_committee
    )
    
    if existing:
        # Update position, affiliation, and role_title if different
        await conn.execute(
            """
            UPDATE committee_roles
            SET position = $1, affiliation = $2, role_title = $3, updated_at = NOW(), modifier = 'import_from_csv'
            WHERE id = $4
            """,
            db_position,
            member.get('affiliation'),
            member.get('role_title'),
            existing
        )
        logger.debug(f"Updated existing role: {member['full_name']} - {member['committee_type']}")
    else:
        # Insert new role
        await conn.execute(
            """
            INSERT INTO committee_roles (conference_id, author_id, committee, position, affiliation, role_title, creator, modifier)
            VALUES ($1, $2, $3, $4, $5, $6, 'import_from_csv', 'import_from_csv')
            """,
            conference_id,
            author_id,
            db_committee,
            db_position,
            member.get('affiliation'),
            member.get('role_title')
        )
        logger.info(f"Imported: {member['full_name']} - {member['committee_type']} ({member.get('position') or 'member'})")
    
    return True


async def import_from_csv(
    pool: asyncpg.Pool,
    csv_file: Path,
    dry_run: bool = False
) -> tuple[int, int]:
    """Import committee data from CSV file."""
    
    # Read CSV file
    members = []
    with open(csv_file, 'r', encoding='utf-8', newline='') as f:
        reader = csv.DictReader(f)
        members = list(reader)
    
    if not members:
        logger.error("No members found in CSV file")
        return 0, 0
    
    venue = members[0]['venue']
    year = int(members[0]['year'])
    
    logger.info(f"Loaded {len(members)} members from {csv_file}")
    logger.info(f"Conference: {venue} {year}")
    
    if dry_run:
        logger.info("DRY RUN - would import:")
        for member in members:
            logger.info(f"  {member['full_name']} - {member['committee_type']} ({member.get('position') or 'member'})")
        return len(members), 0
    
    # Import members
    imported = 0
    failed = 0
    
    async with pool.acquire() as conn:
        async with conn.transaction():
            for member in members:
                try:
                    success = await import_member(conn, venue, year, member)
                    if success:
                        imported += 1
                    else:
                        failed += 1
                except Exception as e:
                    logger.error(f"Error importing {member['full_name']}: {e}")
                    failed += 1
    
    return imported, failed


def add_arguments(parser):
    """Wire CLI flags onto ``parser``. Used by the unified entry point."""
    parser.add_argument('csv_files', type=str, nargs='+',
                        help='Path(s) to CSV file(s) with committee data')
    parser.add_argument('--dry-run', action='store_true',
                        help='Show what would be imported without actually importing')
    parser.add_argument('--db-url', type=str,
                        help='Database URL (default: from DATABASE_URL env var)')


async def async_main(args) -> int:
    """Run the committee import end-to-end. Returns shell exit code."""
    csv_paths = [Path(f) for f in args.csv_files]
    missing = [p for p in csv_paths if not p.exists()]
    if missing:
        for p in missing:
            logger.error(f"CSV file not found: {p}")
        return 1

    pool = None
    if not args.dry_run:
        load_dotenv()
        db_url = args.db_url or os.getenv('DATABASE_URL')
        if not db_url:
            logger.error("No database URL provided. Set DATABASE_URL or use --db-url")
            return 1
        try:
            pool = await asyncpg.create_pool(db_url, min_size=1, max_size=5)
        except Exception as e:
            logger.error(f"Failed to connect to database: {e}")
            return 1

    try:
        total_imported = 0
        total_failed = 0

        for csv_path in csv_paths:
            if len(csv_paths) > 1:
                logger.info(f"--- Processing {csv_path} ---")
            imported, failed = await import_from_csv(pool, csv_path, args.dry_run)
            total_imported += imported
            total_failed += failed

        if len(csv_paths) > 1:
            logger.info(f"--- Total across {len(csv_paths)} files ---")

        if args.dry_run:
            logger.info(f"DRY RUN: {total_imported} records would be imported")
        else:
            logger.info(f"✓ Successfully imported {total_imported} records")
            if total_failed > 0:
                logger.warning(f"✗ Failed to import {total_failed} records")

        return 0 if total_failed == 0 else 1
    finally:
        if pool is not None:
            await pool.close()


def _self_test() -> None:
    """Sanity-check the redundant-role_title rule. Run: python3 -m scrapers.committees.importer"""
    blank = ['Chair', 'Co-Chair', 'PC Member', 'SC Member', 'LO Co-Chair',
             'Program Chair', 'PC Chair', 'member', '  chair  ']
    keep = ['General Chair', 'Honorary Chair', 'Rump Session Organizer',
            'Technical Operations Chair', 'Local Service', 'webmaster', None, '']
    for t in blank:
        assert _is_redundant_role_title(t), f"expected redundant: {t!r}"
    for t in keep:
        assert not _is_redundant_role_title(t), f"expected kept: {t!r}"
    print(f"OK: {len(blank)} redundant + {len(keep)} kept titles classified correctly")


if __name__ == '__main__':
    _self_test()
