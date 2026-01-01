#!/usr/bin/env python3
"""Import verified talk data from CSV file into database."""

import argparse
import asyncio
import csv
import logging
import os
import sys
import re
import json
from pathlib import Path
from typing import Optional, List, Dict
from uuid import UUID
from datetime import datetime

import asyncpg
from dotenv import load_dotenv


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def parse_semicolon_list(value: str) -> Optional[List[str]]:
    """Parse semicolon-separated string into list."""
    if not value or not value.strip():
        return None
    return [item.strip() for item in value.split(';') if item.strip()]


def generate_canonical_key(venue: str, year: int, paper_type: str, index: int) -> str:
    """Generate canonical_key for publication.

    Format: {VENUE}{YEAR}-{paper_type}-{index}
    Examples: QCRYPT2023-invited-1, QIP2024-tutorial-2
    """
    return f"{venue}{year}-{paper_type}-{index}"


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


async def import_talk(
    conn: asyncpg.Connection,
    venue: str,
    year: int,
    talk: Dict[str, str],
    canonical_key: str,
    source_metadata: Dict,
    csv_filename: str
) -> bool:
    """Import a single talk with authors."""

    # Get conference
    conference_id = await get_conference_id(conn, venue, year)
    if not conference_id:
        logger.error(f"Conference not found: {venue} {year}")
        return False

    # Parse list fields
    speakers = parse_semicolon_list(talk.get('speakers', ''))
    authors = parse_semicolon_list(talk.get('authors', ''))
    affiliations = parse_semicolon_list(talk.get('affiliations', ''))
    arxiv_ids = parse_semicolon_list(talk.get('arxiv_ids', ''))

    # Use speakers as authors if authors not specified
    if not authors and speakers:
        authors = speakers

    if not authors:
        logger.warning(f"No authors for talk: {talk.get('title', 'unknown')}")
        return False

    # Check if publication already exists
    existing = await conn.fetchval(
        "SELECT id FROM publications WHERE canonical_key = $1",
        canonical_key
    )

    publication_id = None

    # Add source info to metadata
    enriched_metadata = {
        **source_metadata,
        'csv_file': csv_filename
    }

    # Parse schedule fields
    talk_date = None
    if talk.get('scheduled_date'):
        try:
            # Parse date like "28 January" and assume year from conference
            from dateutil import parser
            date_str = f"{talk['scheduled_date']} {year}"
            talk_date = parser.parse(date_str).date()
        except Exception as e:
            logger.warning(f"Could not parse date '{talk.get('scheduled_date')}': {e}")

    talk_time = None
    if talk.get('scheduled_time'):
        try:
            # Parse time like "13:00"
            talk_time = datetime.strptime(talk['scheduled_time'], '%H:%M').time()
        except Exception as e:
            logger.warning(f"Could not parse time '{talk.get('scheduled_time')}': {e}")

    duration_minutes = None
    if talk.get('duration_minutes'):
        try:
            duration_minutes = int(talk['duration_minutes'])
        except (ValueError, TypeError):
            pass

    if existing:
        logger.debug(f"Publication exists: {canonical_key}, updating...")
        # Update publication
        await conn.execute(
            """
            UPDATE publications
            SET title = $1, abstract = $2, paper_type = $3::paper_type,
                arxiv_ids = $4, session_name = $5, presentation_url = $6,
                video_url = $7, youtube_id = $8, award = $9,
                metadata = $10, talk_date = $11, talk_time = $12, duration_minutes = $13,
                updated_at = NOW(), modifier = 'import_from_csv'
            WHERE id = $14
            """,
            talk.get('title'),
            talk.get('abstract') or None,
            talk.get('paper_type'),
            arxiv_ids,
            talk.get('session_name') or None,
            talk.get('presentation_url') or None,
            talk.get('video_url') or None,
            talk.get('youtube_id') or None,
            talk.get('award') or None,
            json.dumps(enriched_metadata),
            talk_date,
            talk_time,
            duration_minutes,
            existing
        )
        publication_id = existing
    else:
        # Insert new publication
        publication_id = await conn.fetchval(
            """
            INSERT INTO publications (
                conference_id, canonical_key, title, abstract, paper_type,
                arxiv_ids, session_name, presentation_url, video_url, youtube_id,
                award, metadata, talk_date, talk_time, duration_minutes,
                creator, modifier
            ) VALUES (
                $1, $2, $3, $4, $5::paper_type,
                $6, $7, $8, $9, $10,
                $11, $12, $13, $14, $15,
                'import_from_csv', 'import_from_csv'
            ) RETURNING id
            """,
            conference_id, canonical_key, talk.get('title'), talk.get('abstract') or None, talk.get('paper_type'),
            arxiv_ids, talk.get('session_name') or None, talk.get('presentation_url') or None,
            talk.get('video_url') or None, talk.get('youtube_id') or None,
            talk.get('award') or None, json.dumps(enriched_metadata),
            talk_date, talk_time, duration_minutes
        )
        logger.info(f"Created publication: {talk.get('title')}")

    # Clear existing authorships (for updates)
    await conn.execute(
        "DELETE FROM authorships WHERE publication_id = $1",
        publication_id
    )

    # Create authorships
    for idx, author_name in enumerate(authors, start=1):
        # Get affiliation for this author position
        affiliation = None
        if affiliations and len(affiliations) >= idx:
            affiliation = affiliations[idx - 1]

        # Get or create author
        author_id = await get_or_create_author(conn, author_name, affiliation)

        # Create authorship
        await conn.execute(
            """
            INSERT INTO authorships (
                publication_id, author_id, author_position, published_as_name, affiliation,
                metadata, creator, modifier
            ) VALUES (
                $1, $2, $3, $4, $5, $6, 'import_from_csv', 'import_from_csv'
            )
            """,
            publication_id, author_id, idx, author_name, affiliation, json.dumps(enriched_metadata)
        )

    logger.info(f"Imported: {talk.get('title')} with {len(authors)} author(s)")
    return True


async def import_from_csv(
    pool: asyncpg.Pool,
    csv_file: Path,
    dry_run: bool = False
) -> tuple[int, int]:
    """Import talks from CSV."""

    # Read CSV
    talks = []
    with open(csv_file, 'r', encoding='utf-8', newline='') as f:
        reader = csv.DictReader(f)
        talks = list(reader)

    if not talks:
        logger.error("No talks in CSV")
        return 0, 0

    venue = talks[0]['venue']
    year = int(talks[0]['year'])

    logger.info(f"Loaded {len(talks)} talks from {csv_file.name}")
    logger.info(f"Conference: {venue} {year}")

    if dry_run:
        logger.info("DRY RUN - would import:")
        for talk in talks:
            logger.info(f"  {talk.get('paper_type', 'unknown')}: {talk.get('title', 'N/A')[:80]}")
        return len(talks), 0

    # Import talks in transaction
    imported = 0
    failed = 0

    # Group by paper_type for canonical_key generation
    talks_by_type = {}
    for talk in talks:
        paper_type = talk.get('paper_type', 'invited')
        if paper_type not in talks_by_type:
            talks_by_type[paper_type] = []
        talks_by_type[paper_type].append(talk)

    async with pool.acquire() as conn:
        async with conn.transaction():
            for paper_type, type_talks in talks_by_type.items():
                for idx, talk in enumerate(type_talks, start=1):
                    try:
                        canonical_key = generate_canonical_key(venue, year, paper_type, idx)

                        # Source metadata
                        source_metadata = {
                            'source_type': 'conference_website',
                            'source_url': talk.get('notes', ''),  # Notes field can contain source URL
                            'scraped_date': datetime.now().isoformat(),
                            'notes': f'Imported from CSV'
                        }

                        success = await import_talk(
                            conn, venue, year, talk, canonical_key, source_metadata, csv_file.name
                        )
                        if success:
                            imported += 1
                        else:
                            failed += 1
                    except Exception as e:
                        logger.error(f"Error importing {talk.get('title', 'unknown')}: {e}")
                        failed += 1

    return imported, failed


async def async_main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description='Import talks from CSV into database'
    )
    parser.add_argument('csv_file', type=str, help='Path to CSV file')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be imported without making changes')
    parser.add_argument('--db-url', type=str, help='Database URL (overrides DATABASE_URL env var)')

    args = parser.parse_args()

    # Load environment and get database URL
    load_dotenv()
    database_url = args.db_url or os.environ.get('DATABASE_URL')

    if not database_url:
        logger.error("DATABASE_URL not set. Set it in .env file or use --db-url")
        sys.exit(1)

    csv_file = Path(args.csv_file)
    if not csv_file.exists():
        logger.error(f"CSV file not found: {csv_file}")
        sys.exit(1)

    # Create connection pool
    try:
        pool = await asyncpg.create_pool(database_url)
    except Exception as e:
        logger.error(f"Failed to connect to database: {e}")
        sys.exit(1)

    try:
        # Import talks
        imported, failed = await import_from_csv(pool, csv_file, dry_run=args.dry_run)

        # Report results
        if args.dry_run:
            logger.info(f"\nDRY RUN complete. Would import {imported} talks.")
        else:
            logger.info(f"\n✓ Import complete!")
            logger.info(f"  Imported: {imported}")
            if failed > 0:
                logger.warning(f"  Failed: {failed}")

            # Suggest verification
            venue = None
            year = None
            with open(csv_file, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                first_row = next(reader, None)
                if first_row:
                    venue = first_row['venue']
                    year = first_row['year']

            if venue and year:
                logger.info(f"\nVerify with SQL:")
                logger.info(f"  SELECT title, paper_type FROM publications p")
                logger.info(f"  JOIN conferences c ON p.conference_id = c.id")
                logger.info(f"  WHERE c.venue = '{venue}' AND c.year = {year}")
                logger.info(f"  AND p.paper_type IN ('invited', 'tutorial', 'keynote');")

    finally:
        await pool.close()


def main():
    """Entry point for CLI."""
    asyncio.run(async_main())


if __name__ == '__main__':
    main()
