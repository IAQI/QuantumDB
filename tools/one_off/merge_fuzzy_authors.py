#!/usr/bin/env python3
"""One-off: merge fuzzy-duplicate authors that share a first + last name but
differ only by a fuller middle name / initial / name particle.

`dedup_authors.py` only collapses authors with an *identical* normalized_name.
This catches the next tier: "Alex Bredariol Grilo" vs "Alex Grilo",
"Barbara Maria Terhal" vs "Barbara Terhal", "John van de Wetering" vs
"John Wetering", etc.

Safety: a group (same first+last) is merged ONLY if every spelling is an
ordered, initial-compatible subsequence of the richest spelling. If two
spellings have *conflicting* middle names (e.g. "John Robert Smith" vs
"John Andrew Smith"), the whole group is SKIPPED and printed for manual review,
so genuinely distinct people who share a first+last name are never merged.

Dry-run by default; pass --commit to apply. Reuses the reassign/merge SQL
mirrored from dedup_authors.py.
"""
import argparse
import asyncio
import os
import sys
from collections import defaultdict
from pathlib import Path

import asyncpg
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scrapers._lib import normalize_name  # noqa: E402


# (first, last) groups the auto-check skips for conflicting middles, but which
# manual review confirmed are each a single person (initial-spacing / typos).
# Forced groups merge into the spelling with the most normalized name tokens.
FORCE_KEYS = {
    ('andrew', 'yao'), ('charles', 'lim'), ('daniel', 'oi'), ('ernest', 'tan'),
    ('fernando', 'brandao'), ('laleh', 'beni'), ('salvatore', 'oliviero'),
    ('thomas', 'pedersen'),
}


def tokens(normalized):
    return [t for t in normalized.split() if t]


def _tok_match(a, b):
    """True if middle token a is equal to, or an initial of, token b (or vice versa)."""
    a, b = a.strip('.'), b.strip('.')
    if a == b:
        return True
    if len(a) == 1 and b.startswith(a):
        return True
    if len(b) == 1 and a.startswith(b):
        return True
    return False


def is_subsequence(short, long):
    """Greedy: is `short` an ordered, token-matching subsequence of `long`?"""
    i = 0
    for tok in long:
        if i < len(short) and _tok_match(short[i], tok):
            i += 1
    return i == len(short)


def richness(full_name, orcid):
    toks = full_name.split()
    return (1 if orcid else 0, len(toks), 1 if any(ord(c) > 127 for c in full_name) else 0, len(full_name))


async def main(commit):
    load_dotenv()
    url = os.environ.get('DATABASE_URL')
    if not url:
        print('DATABASE_URL not set'); return 1
    conn = await asyncpg.connect(url)
    rows = await conn.fetch('SELECT id, full_name, normalized_name, orcid FROM authors')

    # group by (first, last) of normalized_name
    groups = defaultdict(list)
    for r in rows:
        t = tokens(r['normalized_name'] or '')
        if len(t) < 2:
            continue
        groups[(t[0], t[-1])].append(r)

    merges, skipped = [], []
    for key, group in groups.items():
        if len({r['full_name'] for r in group}) < 2:
            continue  # all identical spelling already handled / single record
        if key in FORCE_KEYS:
            # pick the most complete spelling (most normalized tokens, then richness)
            ranked = sorted(group, key=lambda r: (len(tokens(r['normalized_name'])),) + richness(r['full_name'], r['orcid']), reverse=True)
            merges.append((ranked[0], ranked[1:]))
            continue
        ranked = sorted(group, key=lambda r: richness(r['full_name'], r['orcid']), reverse=True)
        canonical = ranked[0]
        canon_mid = tokens(canonical['normalized_name'])[1:-1]
        ok = all(is_subsequence(tokens(r['normalized_name'])[1:-1], canon_mid) for r in ranked[1:])
        if ok:
            merges.append((canonical, ranked[1:]))
        else:
            skipped.append((key, group))

    print(f'== {len(merges)} mergeable groups, {len(skipped)} skipped for review ==\n')
    for canonical, dups in sorted(merges, key=lambda m: m[0]['full_name']):
        print(f'  CANON {canonical["full_name"]!r}')
        for d in dups:
            print(f'     <- {d["full_name"]!r}')
    if skipped:
        print('\n-- SKIPPED (conflicting middles; review manually) --')
        for key, group in sorted(skipped):
            print(f'  {key}: ' + ' | '.join(sorted({r["full_name"] for r in group})))

    if not commit:
        print('\nDRY RUN — pass --commit to apply.')
        await conn.close()
        return 0

    print('\nApplying merges...')
    async with conn.transaction():
        for canonical, dups in merges:
            canon_id = canonical['id']
            for d in dups:
                dup_id = d['id']
                await conn.execute(
                    '''UPDATE authorships SET author_id=$1 WHERE author_id=$2 AND NOT EXISTS (
                         SELECT 1 FROM authorships au2 WHERE au2.publication_id=authorships.publication_id AND au2.author_id=$1)''',
                    canon_id, dup_id)
                await conn.execute('DELETE FROM authorships WHERE author_id=$1', dup_id)
                await conn.execute(
                    '''UPDATE committee_roles SET author_id=$1 WHERE author_id=$2 AND NOT EXISTS (
                         SELECT 1 FROM committee_roles cr2 WHERE cr2.conference_id=committee_roles.conference_id
                           AND cr2.author_id=$1 AND cr2.committee=committee_roles.committee AND cr2.position=committee_roles.position)''',
                    canon_id, dup_id)
                await conn.execute('DELETE FROM committee_roles WHERE author_id=$1', dup_id)
                await conn.execute(
                    '''UPDATE author_name_variants SET author_id=$1 WHERE author_id=$2 AND NOT EXISTS (
                         SELECT 1 FROM author_name_variants v2 WHERE v2.author_id=$1 AND v2.normalized_variant=author_name_variants.normalized_variant)''',
                    canon_id, dup_id)
                await conn.execute('DELETE FROM author_name_variants WHERE author_id=$1', dup_id)
                await conn.execute(
                    '''INSERT INTO author_name_variants (author_id, variant_name, normalized_variant, variant_type, notes, creator)
                       VALUES ($1,$2,$3,'alternate_spelling','merged from fuzzy-duplicate author row','merge_fuzzy_authors.py')
                       ON CONFLICT DO NOTHING''',
                    canon_id, d['full_name'], normalize_name(d['full_name']))
                await conn.execute('DELETE FROM authors WHERE id=$1', dup_id)
        await conn.execute('REFRESH MATERIALIZED VIEW CONCURRENTLY author_stats')
        await conn.execute('REFRESH MATERIALIZED VIEW CONCURRENTLY conference_stats')
        await conn.execute('REFRESH MATERIALIZED VIEW CONCURRENTLY coauthor_pairs')
    n = await conn.fetchval('SELECT COUNT(*) FROM authors')
    print(f'\n✓ Done. authors now: {n}')
    await conn.close()
    return 0


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--commit', action='store_true')
    args = ap.parse_args()
    sys.exit(asyncio.run(main(args.commit)))
