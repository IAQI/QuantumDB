#!/usr/bin/env python3
"""Merge duplicate/aliased author rows into a single canonical identity.

Two kinds of merge:

A. **Curated aliases** (`data/author_aliases.csv`) — explicit
   `former_name → current_name` pairs that normalization CANNOT detect, e.g. a
   surname change ("Tobias Eberle" → "Tobias Gehring"). Matched by exact
   `full_name`. This is the durable home for name changes, so they survive a
   full rebuild-from-CSV (the DB has no signal that two surnames are one person).

B. **Normalized-name collapse** — after recomputing `authors.normalized_name`
   (fold middle initials, strip diacritics/honorifics), authors that now share a
   `normalized_name` are merged, canonical = highest "richness" score.

In both cases authorships / committee_roles / existing variants are reassigned
to the canonical row (`published_as_name` on each authorship is preserved, so a
paper keeps the name it was published under), an `author_name_variants` row is
recorded for the merged spelling, and the duplicate `authors` row is deleted.

Dry-run by default; pass `--commit` to apply.
"""
import asyncio
import csv
import os
import sys
import argparse
from pathlib import Path
from collections import defaultdict

import asyncpg
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent))
from scrapers._lib import normalize_name

ALIASES_PATH = Path(__file__).resolve().parent.parent / 'data' / 'author_aliases.csv'


def richness(full_name, orcid):
    """Score how "rich" a name spelling is. Higher = better canonical pick."""
    has_orcid = 1 if orcid else 0
    tokens = full_name.split()
    n_tokens = len(tokens)
    has_middle_initial = 1 if any(len(t.strip('.')) == 1 and t.endswith('.') for t in tokens) else 0
    has_diacritics = 1 if any(ord(c) > 127 for c in full_name) else 0
    return (has_orcid, n_tokens, has_middle_initial, has_diacritics)


def load_aliases():
    """Read curated former→current name merges. Returns list of dicts."""
    if not ALIASES_PATH.exists():
        return []
    with open(ALIASES_PATH, encoding='utf-8', newline='') as f:
        return [r for r in csv.DictReader(f) if (r.get('former_name') or '').strip()]


async def merge_author(conn, canon_id, dup_id, variant_name, variant_type, notes, creator):
    """Reassign a duplicate author's links to the canonical row, record a name
    variant, and delete the duplicate. `published_as_name` is left untouched."""
    # Publications this duplicate presents. We must clear the presenter link
    # *before* touching its authorship rows and restore it (to the canonical
    # author) *after*, because `ensure_presenter_is_author` guards both
    # `publications.presenter_author_id` and `authorships`: setting the presenter
    # to the canonical row before it is an author would fail, and reassigning the
    # presenter's authorship while the link still points at the duplicate would
    # fail too. The canonical row is always an author of these pubs afterwards
    # (the duplicate's authorship is reassigned to it, or it was already one).
    presenter_pubs = [r['id'] for r in await conn.fetch(
        'SELECT id FROM publications WHERE presenter_author_id = $1', dup_id)]
    if presenter_pubs:
        await conn.execute(
            'UPDATE publications SET presenter_author_id = NULL WHERE presenter_author_id = $1',
            dup_id)
    # Reassign authorships (skip rows that would collide on (publication, author))
    await conn.execute(
        '''UPDATE authorships SET author_id = $1
           WHERE author_id = $2 AND NOT EXISTS (
             SELECT 1 FROM authorships au2
             WHERE au2.publication_id = authorships.publication_id
               AND au2.author_id = $1)''',
        canon_id, dup_id)
    await conn.execute('DELETE FROM authorships WHERE author_id = $1', dup_id)
    # Restore the presenter link, now pointing at the canonical (author) row.
    if presenter_pubs:
        await conn.execute(
            'UPDATE publications SET presenter_author_id = $1 WHERE id = ANY($2::uuid[])',
            canon_id, presenter_pubs)
    # Committee roles (UNIQUE on conference+author+committee+position)
    await conn.execute(
        '''UPDATE committee_roles SET author_id = $1
           WHERE author_id = $2 AND NOT EXISTS (
             SELECT 1 FROM committee_roles cr2
             WHERE cr2.conference_id = committee_roles.conference_id
               AND cr2.author_id = $1
               AND cr2.committee = committee_roles.committee
               AND cr2.position = committee_roles.position)''',
        canon_id, dup_id)
    await conn.execute('DELETE FROM committee_roles WHERE author_id = $1', dup_id)
    # Move existing variants of the dup to canonical
    await conn.execute(
        '''UPDATE author_name_variants SET author_id = $1
           WHERE author_id = $2 AND NOT EXISTS (
             SELECT 1 FROM author_name_variants v2
             WHERE v2.author_id = $1
               AND v2.normalized_variant = author_name_variants.normalized_variant)''',
        canon_id, dup_id)
    await conn.execute('DELETE FROM author_name_variants WHERE author_id = $1', dup_id)
    # Record the merged spelling as a variant of the canonical row
    await conn.execute(
        '''INSERT INTO author_name_variants
             (author_id, variant_name, normalized_variant, variant_type, notes, creator)
           VALUES ($1, $2, $3, $4, $5, $6)
           ON CONFLICT DO NOTHING''',
        canon_id, variant_name, normalize_name(variant_name), variant_type, notes, creator)
    await conn.execute('DELETE FROM authors WHERE id = $1', dup_id)


async def run_alias_merges(conn, commit):
    """Phase A: apply curated former→current merges (matched by exact full_name)."""
    aliases = load_aliases()
    if not aliases:
        return
    print(f'Phase A: curated aliases ({ALIASES_PATH.name}) — {len(aliases)} entries')
    for a in aliases:
        former = a['former_name'].strip()
        current = a['current_name'].strip()
        vtype = (a.get('variant_type') or 'former_name').strip()
        notes = (a.get('notes') or '').strip()
        former_row = await conn.fetchrow('SELECT id FROM authors WHERE full_name = $1', former)
        canon_row = await conn.fetchrow('SELECT id FROM authors WHERE full_name = $1', current)
        if not former_row:
            print(f'  - {former!r} -> {current!r}: former not present (already merged) — skip')
            continue
        if not canon_row:
            print(f'  ! {former!r} -> {current!r}: canonical {current!r} not found — SKIP')
            continue
        if former_row['id'] == canon_row['id']:
            print(f'  - {former!r} -> {current!r}: already the same row — skip')
            continue
        print(f'  ✓ {former!r} -> {current!r}  ({vtype})')
        if commit:
            await merge_author(conn, canon_row['id'], former_row['id'],
                               former, vtype, notes or 'curated alias merge', 'author_aliases.csv')


async def main(commit: bool):
    load_dotenv()
    url = os.environ.get('DATABASE_URL')
    if not url:
        print('DATABASE_URL not set'); return 1
    conn = await asyncpg.connect(url)

    # Phase A: curated alias merges (own transaction so the normalized pass below
    # sees the post-merge state).
    if commit:
        async with conn.transaction():
            await run_alias_merges(conn, commit)
    else:
        await run_alias_merges(conn, commit)

    print('\nStep 1: recompute normalized_name for all authors...')
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
    merges = []  # (canonical_row, [dup_rows])
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
                    nn, r['id'])

        # Then merge duplicates
        for canonical, dups in merges:
            for d in dups:
                await merge_author(conn, canonical['id'], d['id'], d['full_name'],
                                   'alternate_spelling', 'merged from duplicate author row',
                                   'dedup_authors.py')

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
