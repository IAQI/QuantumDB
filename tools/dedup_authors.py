#!/usr/bin/env python3
"""Recompute authors.normalized_name and merge duplicates that now collapse.

The Python importer's `normalize_name` was upgraded to:
  - fold single-letter middle-initial tokens ("Umesh V." → "umesh"),
  - strip diacritics ("Frédéric" → "frederic"),
  - strip honorifics ("Dr.", "Prof.").

This script:
  1. Recomputes `authors.normalized_name` for every row.
  2. Finds groups of authors that now share a `normalized_name`.
  3. Picks a canonical row in each group (highest "richness" score: more
     name tokens > has middle initial > has diacritics > has ORCID).
  4. Reassigns authorships, committee_roles, author_name_variants from
     duplicate rows to the canonical one (skipping any rows that would
     violate UNIQUE constraints).
  5. Inserts an `author_name_variants` row for each merged duplicate
     spelling.
  6. Deletes the duplicate `authors` rows.

Dry-run by default; pass `--commit` to apply.
"""
import asyncio
import os
import sys
import argparse
from pathlib import Path
from collections import defaultdict

import asyncpg
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent))
from scrapers._lib import normalize_name


def richness(full_name, orcid):
    """Score how "rich" a name spelling is. Higher = better canonical pick."""
    has_orcid = 1 if orcid else 0
    tokens = full_name.split()
    n_tokens = len(tokens)
    has_middle_initial = 1 if any(len(t.strip('.')) == 1 and t.endswith('.') for t in tokens) else 0
    has_diacritics = 1 if any(ord(c) > 127 for c in full_name) else 0
    return (has_orcid, n_tokens, has_middle_initial, has_diacritics)


async def main(commit: bool):
    load_dotenv()
    url = os.environ.get('DATABASE_URL')
    if not url:
        print('DATABASE_URL not set'); return 1
    conn = await asyncpg.connect(url)

    print('Step 1: recompute normalized_name for all authors...')
    rows = await conn.fetch('SELECT id, full_name, normalized_name, orcid FROM authors')
    print(f'  {len(rows)} authors loaded')

    new_normalized = {}
    n_changed = 0
    for r in rows:
        nn = normalize_name(r['full_name'])
        if nn != (r['normalized_name'] or ''):
            n_changed += 1
        new_normalized[r['id']] = nn
    print(f'  {n_changed} normalized_name values would change')

    print('\nStep 2: group authors by new normalized_name...')
    groups = defaultdict(list)
    for r in rows:
        groups[new_normalized[r['id']]].append(r)
    dup_groups = [(k, g) for k, g in groups.items() if len(g) > 1 and k]
    dup_groups.sort(key=lambda kg: (-len(kg[1]), kg[0]))
    print(f'  {len(dup_groups)} groups of duplicates ({sum(len(g)-1 for _, g in dup_groups)} merges)')

    print('\nStep 3: plan merges...')
    merges = []  # (canonical_id, [(dup_id, dup_name), ...])
    for key, group in dup_groups:
        ranked = sorted(group, key=lambda r: richness(r['full_name'], r['orcid']), reverse=True)
        canonical = ranked[0]
        dups = ranked[1:]
        merges.append((canonical, dups))
        print(f'  [{key}]')
        print(f'    CANONICAL: {canonical["full_name"]!r} ({canonical["id"]})')
        for d in dups:
            print(f'    merge -> : {d["full_name"]!r} ({d["id"]})')

    if not commit:
        print('\nDRY RUN — no changes made. Pass --commit to apply.')
        await conn.close()
        return 0

    print('\nStep 4: applying merges...')
    async with conn.transaction():
        # First, update all normalized_name values
        for r in rows:
            nn = new_normalized[r['id']]
            if nn != (r['normalized_name'] or ''):
                await conn.execute(
                    'UPDATE authors SET normalized_name = $1 WHERE id = $2',
                    nn, r['id']
                )

        # Then merge duplicates
        for canonical, dups in merges:
            canon_id = canonical['id']
            for d in dups:
                dup_id = d['id']
                # Reassign authorships (skip if a conflicting row exists)
                await conn.execute(
                    '''UPDATE authorships SET author_id = $1
                       WHERE author_id = $2 AND NOT EXISTS (
                         SELECT 1 FROM authorships au2
                         WHERE au2.publication_id = authorships.publication_id
                           AND au2.author_id = $1)''',
                    canon_id, dup_id
                )
                # Delete any remaining (collision) authorship rows
                await conn.execute(
                    'DELETE FROM authorships WHERE author_id = $1', dup_id
                )
                # Same dance for committee_roles (UNIQUE on conference+author+committee+position)
                await conn.execute(
                    '''UPDATE committee_roles SET author_id = $1
                       WHERE author_id = $2 AND NOT EXISTS (
                         SELECT 1 FROM committee_roles cr2
                         WHERE cr2.conference_id = committee_roles.conference_id
                           AND cr2.author_id = $1
                           AND cr2.committee = committee_roles.committee
                           AND cr2.position = committee_roles.position)''',
                    canon_id, dup_id
                )
                await conn.execute(
                    'DELETE FROM committee_roles WHERE author_id = $1', dup_id
                )
                # Move any existing author_name_variants to canonical
                await conn.execute(
                    '''UPDATE author_name_variants SET author_id = $1
                       WHERE author_id = $2 AND NOT EXISTS (
                         SELECT 1 FROM author_name_variants v2
                         WHERE v2.author_id = $1
                           AND v2.normalized_variant = author_name_variants.normalized_variant)''',
                    canon_id, dup_id
                )
                await conn.execute(
                    'DELETE FROM author_name_variants WHERE author_id = $1', dup_id
                )
                # Insert an author_name_variants entry for the dup spelling
                await conn.execute(
                    '''INSERT INTO author_name_variants
                         (author_id, variant_name, normalized_variant, variant_type, notes, creator)
                       VALUES ($1, $2, $3, 'alternate_spelling',
                               'merged from duplicate author row', 'dedup_authors.py')
                       ON CONFLICT DO NOTHING''',
                    canon_id, d['full_name'], normalize_name(d['full_name'])
                )
                # Finally delete the duplicate author
                await conn.execute('DELETE FROM authors WHERE id = $1', dup_id)

        # Refresh materialized views (after data changes)
        await conn.execute('REFRESH MATERIALIZED VIEW CONCURRENTLY author_stats')
        await conn.execute('REFRESH MATERIALIZED VIEW CONCURRENTLY conference_stats')
        await conn.execute('REFRESH MATERIALIZED VIEW CONCURRENTLY coauthor_pairs')

    n_authors = await conn.fetchval('SELECT COUNT(*) FROM authors')
    n_variants = await conn.fetchval('SELECT COUNT(*) FROM author_name_variants')
    print(f'\n✓ Done. authors: {n_authors}, author_name_variants: {n_variants}')
    await conn.close()
    return 0


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--commit', action='store_true',
                    help='Actually apply the merges (default: dry-run)')
    args = ap.parse_args()
    sys.exit(asyncio.run(main(args.commit)))
