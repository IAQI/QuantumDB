#!/usr/bin/env python3
"""Import verified committee data from CSV file into database."""

import argparse
import asyncio
import csv
import logging
import os
import sys
import re
from pathlib import Path
from typing import Optional, List, Dict
from uuid import UUID

import asyncpg
from dotenv import load_dotenv


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def normalize_name(name: str) -> str:
    """Normalize author name for matching."""
    # Remove common prefixes/suffixes
    name = re.sub(r'\b(Dr\.|Prof\.|Jr\.|Sr\.|Ph\.?D\.?|M\.?D\.?)\b', '', name, flags=re.IGNORECASE)
    # Remove extra whitespace
    name = ' '.join(name.split())
    return name.strip()


def split_name(full_name: str) -> tuple[str, str]:
    """Split full name into family and given names."""
    normalized = normalize_name(full_name)
    parts = normalized.rsplit(' ', 1)
    
    if len(parts) == 1:
        return parts[0], ''
    else:
        return parts[1], parts[0]


def map_committee_type(committee_type: str) -> str:
    """Map CSV committee_type to database enum value."""
    mapping = {
        'program': 'PC',
        'steering': 'SC',
        'local_organizing': 'Local',
        'organizing': 'OC'
    }
    return mapping.get(committee_type, committee_type)


def map_position(position: str) -> str:
    """Map CSV position to database enum value."""
    if not position:
        return 'member'
    
    position = position.lower().strip()
    mapping = {
        'chair': 'chair',
        'co-chair': 'co_chair',
        'area_chair': 'area_chair',
        'member': 'member'
    }
    return mapping.get(position, 'member')


async def get_or_create_author(
    conn: asyncpg.Connection,
    full_name: str,
    affiliation: Optional[str]
) -> UUID:
    """Get existing author or create new one."""
    family_name, given_name = split_name(full_name)
    normalized_full = normalize_name(full_name).lower()
    
    # Try to find existing author by normalized_name
    author_id = await conn.fetchval(
        """
        SELECT a.id FROM authors a
        LEFT JOIN author_name_variants v ON a.id = v.author_id
        WHERE a.normalized_name = $1
           OR LOWER(v.variant_name) = $1
        LIMIT 1
        """,
        normalized_full
    )
    
    if author_id:
        logger.debug(f"Found existing author: {full_name} -> {author_id}")
        
        # Update affiliation if provided and different
        if affiliation:
            await conn.execute(
                """
                UPDATE authors 
                SET affiliation = $1 
                WHERE id = $2 AND (affiliation IS NULL OR affiliation != $1)
                """,
                affiliation,
                author_id
            )
        
        return author_id
    
    # Create new author
    author_id = await conn.fetchval(
        """
        INSERT INTO authors (full_name, family_name, given_name, normalized_name, affiliation, creator, modifier)
        VALUES ($1, $2, $3, $4, $5, 'import_from_csv', 'import_from_csv')
        RETURNING id
        """,
        full_name,
        family_name,
        given_name,
        normalized_full,
        affiliation
    )
    
    logger.info(f"Created new author: {full_name} ({author_id})")
    return author_id


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


async def main():
    """Main import function."""
    parser = argparse.ArgumentParser(
        description='Import committee data from CSV file into database'
    )
    parser.add_argument('csv_file', type=str,
                       help='Path to CSV file with committee data')
    parser.add_argument('--dry-run', action='store_true',
                       help='Show what would be imported without actually importing')
    parser.add_argument('--db-url', type=str,
                       help='Database URL (default: from DATABASE_URL env var)')
    
    args = parser.parse_args()
    
    # Check file exists
    csv_path = Path(args.csv_file)
    if not csv_path.exists():
        logger.error(f"CSV file not found: {csv_path}")
        return 1
    
    # Load environment
    load_dotenv()
    db_url = args.db_url or os.getenv('DATABASE_URL')
    if not db_url:
        logger.error("No database URL provided. Set DATABASE_URL or use --db-url")
        return 1
    
    # Connect to database
    try:
        pool = await asyncpg.create_pool(db_url, min_size=1, max_size=5)
        
        # Import data
        imported, failed = await import_from_csv(pool, csv_path, args.dry_run)
        
        if args.dry_run:
            logger.info(f"DRY RUN: {imported} records would be imported")
        else:
            logger.info(f"✓ Successfully imported {imported} records")
            if failed > 0:
                logger.warning(f"✗ Failed to import {failed} records")
        
        await pool.close()
        return 0 if failed == 0 else 1
        
    except Exception as e:
        logger.error(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
