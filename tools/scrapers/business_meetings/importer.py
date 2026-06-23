"""CLI body for `import_from_csv.py business-meetings`.

Imports a *tall* business-meeting CSV (one row per announced fact) into the
``conference_business_meetings`` table. The CSV is the human-editable source of
truth; this importer pivots its rows into one DB row per conference and records
per-fact provenance in ``metadata.sources``.

CSV columns: ``venue,year,field,value,source_type,source_url,source_date,notes``

Recognized ``field`` values map to typed columns; ``track_breakdown`` takes a
JSON value; ``notes`` rows and any row's ``notes`` cell feed the ``notes``
column. Unknown fields are warned about and stashed in ``metadata.extra`` (never
silently dropped). Re-importing a file overwrites that conference's row from the
CSV (the CSV is authoritative), so keep all known facts for a conference in its
file.
"""

import argparse
import csv
import datetime
import json
import logging
import os
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from uuid import UUID

import asyncpg
from dotenv import load_dotenv

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger(__name__)

# field name -> integer column
INT_FIELDS = {
    'registered_participants',
    'onsite_participants',
    'countries_represented',
    'talk_submissions',
    'talks_accepted',
    'posters_submitted',
    'posters_accepted',
}
# All recognized field names (drives provenance capture + unknown-field warnings)
KNOWN_FIELDS = INT_FIELDS | {'meeting_date', 'acceptance_rate', 'track_breakdown', 'notes'}


async def get_conference_id(conn: asyncpg.Connection, venue: str, year: int) -> Optional[UUID]:
    """Resolve a seeded conference by (venue, year)."""
    return await conn.fetchval(
        "SELECT id FROM conferences WHERE venue = $1 AND year = $2",
        venue,
        year,
    )


def pivot_rows(rows: List[Dict[str, str]]) -> Tuple[Dict, Dict, List[str]]:
    """Pivot tall fact-rows for one conference into (columns, metadata, problems).

    ``columns`` maps DB column -> typed value. ``metadata`` is the JSONB payload
    ({"sources": {...}, "extra": {...}}). ``problems`` lists human-readable
    warnings (bad values, unknown fields) for surfacing to the caller.
    """
    columns: Dict[str, object] = {}
    sources: Dict[str, Dict[str, str]] = {}
    extra: Dict[str, str] = {}
    notes_parts: List[str] = []
    slides: List[Dict[str, str]] = []
    problems: List[str] = []

    for r in rows:
        field = (r.get('field') or '').strip()
        value = (r.get('value') or '').strip()
        if not field:
            continue

        # Per-fact provenance
        prov = {
            k: v for k, v in (
                ('source_type', (r.get('source_type') or '').strip()),
                ('source_url', (r.get('source_url') or '').strip()),
                ('source_date', (r.get('source_date') or '').strip()),
            ) if v
        }
        row_note = (r.get('notes') or '').strip()

        # A slide-deck link: `field` is `slide:<label>`, `value` is the URL.
        if field.startswith('slide:'):
            label = field[len('slide:'):].strip()
            if value:
                slides.append({'label': label, 'url': value})
            else:
                problems.append(f"slide {label!r}: empty URL — skipped")
            continue

        if field in INT_FIELDS:
            try:
                columns[field] = int(value)
            except ValueError:
                problems.append(f"{field}: non-integer value {value!r} — skipped")
                continue
        elif field == 'acceptance_rate':
            try:
                columns[field] = Decimal(value)
            except (InvalidOperation, ValueError):
                problems.append(f"acceptance_rate: non-numeric value {value!r} — skipped")
                continue
        elif field == 'meeting_date':
            try:
                columns[field] = datetime.date.fromisoformat(value)
            except ValueError:
                problems.append(f"meeting_date: not ISO YYYY-MM-DD {value!r} — skipped")
                continue
        elif field == 'track_breakdown':
            try:
                columns[field] = json.loads(value)
            except json.JSONDecodeError as e:
                problems.append(f"track_breakdown: invalid JSON ({e}) — skipped")
                continue
        elif field == 'notes':
            if value:
                notes_parts.append(value)
        else:
            problems.append(f"unknown field {field!r} — stashed in metadata.extra")
            extra[field] = value

        if field in KNOWN_FIELDS and prov:
            sources[field] = prov
        # A per-fact annotation in the notes cell rides along with that field.
        if row_note and field != 'notes':
            notes_parts.append(f"{field}: {row_note}")

    if notes_parts:
        columns['notes'] = "\n".join(notes_parts)
    if slides:
        columns['slides'] = slides

    metadata: Dict[str, object] = {}
    if sources:
        metadata['sources'] = sources
    if extra:
        metadata['extra'] = extra

    return columns, metadata, problems


async def upsert_meeting(
    conn: asyncpg.Connection,
    conference_id: UUID,
    columns: Dict,
    metadata: Dict,
) -> None:
    """Insert or update the single business-meeting row for a conference."""
    track = columns.get('track_breakdown')
    slides = columns.get('slides') or []
    await conn.execute(
        """
        INSERT INTO conference_business_meetings
            (conference_id, meeting_date, registered_participants, onsite_participants,
             countries_represented, talk_submissions, talks_accepted, posters_submitted,
             posters_accepted, acceptance_rate, track_breakdown, notes, slides, metadata,
             creator, modifier)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11::jsonb, $12, $13::jsonb, $14::jsonb,
                'import_from_csv', 'import_from_csv')
        ON CONFLICT (conference_id) DO UPDATE SET
            meeting_date            = EXCLUDED.meeting_date,
            registered_participants = EXCLUDED.registered_participants,
            onsite_participants     = EXCLUDED.onsite_participants,
            countries_represented   = EXCLUDED.countries_represented,
            talk_submissions        = EXCLUDED.talk_submissions,
            talks_accepted          = EXCLUDED.talks_accepted,
            posters_submitted       = EXCLUDED.posters_submitted,
            posters_accepted        = EXCLUDED.posters_accepted,
            acceptance_rate         = EXCLUDED.acceptance_rate,
            track_breakdown         = EXCLUDED.track_breakdown,
            notes                   = EXCLUDED.notes,
            slides                  = EXCLUDED.slides,
            metadata                = EXCLUDED.metadata,
            updated_at              = NOW(),
            modifier                = 'import_from_csv'
        """,
        conference_id,
        columns.get('meeting_date'),
        columns.get('registered_participants'),
        columns.get('onsite_participants'),
        columns.get('countries_represented'),
        columns.get('talk_submissions'),
        columns.get('talks_accepted'),
        columns.get('posters_submitted'),
        columns.get('posters_accepted'),
        columns.get('acceptance_rate'),
        json.dumps(track) if track is not None else None,
        columns.get('notes'),
        json.dumps(slides),
        json.dumps(metadata),
    )


async def import_from_csv(pool: Optional[asyncpg.Pool], csv_file: Path, dry_run: bool) -> Tuple[int, int]:
    """Import one tall business-meeting CSV. Returns (conferences_upserted, failed)."""
    with open(csv_file, 'r', encoding='utf-8', newline='') as f:
        rows = list(csv.DictReader(f))

    if not rows:
        logger.error(f"No rows in {csv_file}")
        return 0, 0

    # Group by conference (normally one per file)
    by_conf: Dict[Tuple[str, int], List[Dict[str, str]]] = defaultdict(list)
    for r in rows:
        try:
            key = (r['venue'].strip(), int(r['year']))
        except (KeyError, ValueError):
            logger.error(f"Row missing/invalid venue or year: {r}")
            continue
        by_conf[key].append(r)

    upserted = 0
    failed = 0
    for (venue, year), conf_rows in by_conf.items():
        columns, metadata, problems = pivot_rows(conf_rows)
        for p in problems:
            logger.warning(f"  [{venue} {year}] {p}")

        facts = sorted(k for k in columns if k != 'notes')
        logger.info(f"{venue} {year}: {len(facts)} facts ({', '.join(facts) or 'none'})")

        if dry_run:
            logger.info(f"  DRY RUN — would upsert; metadata={json.dumps(metadata)}")
            upserted += 1
            continue

        async with pool.acquire() as conn:
            conference_id = await get_conference_id(conn, venue, year)
            if not conference_id:
                logger.error(f"  Conference not found (seed it first): {venue} {year}")
                failed += 1
                continue
            try:
                async with conn.transaction():
                    await upsert_meeting(conn, conference_id, columns, metadata)
                logger.info(f"  ✓ upserted business meeting for {venue} {year}")
                upserted += 1
            except Exception as e:
                logger.error(f"  Error upserting {venue} {year}: {e}")
                failed += 1

    return upserted, failed


def add_arguments(parser: argparse.ArgumentParser) -> None:
    """Wire CLI flags onto ``parser``. Used by the unified entry point."""
    parser.add_argument('csv_files', type=str, nargs='+',
                        help='Path(s) to tall business_meeting.csv file(s)')
    parser.add_argument('--dry-run', action='store_true',
                        help='Show what would be imported without writing to the DB')
    parser.add_argument('--db-url', type=str,
                        help='Database URL (default: from DATABASE_URL env var)')


async def async_main(args) -> int:
    """Run the business-meeting import end-to-end. Returns shell exit code."""
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
        total_upserted = 0
        total_failed = 0
        for csv_path in csv_paths:
            if len(csv_paths) > 1:
                logger.info(f"--- Processing {csv_path} ---")
            upserted, failed = await import_from_csv(pool, csv_path, args.dry_run)
            total_upserted += upserted
            total_failed += failed

        if args.dry_run:
            logger.info(f"DRY RUN: {total_upserted} conference(s) would be upserted")
        else:
            logger.info(f"✓ Upserted {total_upserted} business-meeting record(s)")
            if total_failed:
                logger.warning(f"✗ {total_failed} failed")
        return 0 if total_failed == 0 else 1
    finally:
        if pool is not None:
            await pool.close()
