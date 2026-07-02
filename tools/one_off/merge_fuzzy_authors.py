#!/usr/bin/env python3
"""Propose fuzzy-duplicate author merges as curated alias rows.

Groups authors that share a first + last name but differ only by a fuller
middle name / initial / name particle — e.g. "Alex Bredariol Grilo" vs
"Alex Grilo", "Barbara Maria Terhal" vs "Barbara Terhal", "John van de
Wetering" vs "John Wetering". `dedup_authors.py` Phase B only collapses
*identical* normalized names; this catches the next tier.

This tool NEVER writes to the database. It only PROPOSES `former -> current`
rows for `data/author_aliases.csv`; `dedup_authors.py` Phase A applies them on
every reload, so the merges stay reproducible from the CSVs (no DB-direct
changes). Workflow: reload DB from CSVs -> `dedup_authors.py --commit` ->
`merge_fuzzy_authors.py --emit` -> review + append rows to author_aliases.csv
-> `dedup_authors.py --commit` again.

Usage:
    python tools/one_off/merge_fuzzy_authors.py           # human-readable report
    python tools/one_off/merge_fuzzy_authors.py --emit     # CSV rows for author_aliases.csv

Safety: a group (same first+last) is proposed ONLY if every spelling is an
ordered, initial-compatible subsequence of the richest spelling. Conflicting
middle names (e.g. "John Robert Smith" vs "John Andrew Smith") are SKIPPED and
printed for manual review, so distinct people sharing a first+last name are
never merged. FORCE_KEYS lists (first, last) groups the auto-check skips but
that manual review confirmed are a single person (initial-spacing / typos).
"""
import argparse
import asyncio
import csv
import os
import sys
from collections import defaultdict

import asyncpg
from dotenv import load_dotenv


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


async def detect(conn):
    """Return (merges, skipped). Each merge is (canonical_row, [duplicate_rows])."""
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
    return merges, skipped


async def main(emit):
    load_dotenv()
    url = os.environ.get('DATABASE_URL')
    if not url:
        print('DATABASE_URL not set', file=sys.stderr)
        return 1
    conn = await asyncpg.connect(url)
    try:
        merges, skipped = await detect(conn)
    finally:
        await conn.close()

    if emit:
        # CSV rows ready to append to data/author_aliases.csv
        # (columns: former_name,current_name,variant_type,notes)
        w = csv.writer(sys.stdout)
        for canonical, dups in sorted(merges, key=lambda m: m[0]['full_name']):
            for d in dups:
                w.writerow([
                    d['full_name'], canonical['full_name'], 'alternate_spelling',
                    'fuzzy-merge: same first+last, fuller middle name/initial/particle',
                ])
        return 0

    print(f'== {len(merges)} mergeable groups, {len(skipped)} skipped for review ==\n')
    for canonical, dups in sorted(merges, key=lambda m: m[0]['full_name']):
        print(f'  CANON {canonical["full_name"]!r}')
        for d in dups:
            print(f'     <- {d["full_name"]!r}')
    if skipped:
        print('\n-- SKIPPED (conflicting middles; review manually) --')
        for key, group in sorted(skipped):
            print(f'  {key}: ' + ' | '.join(sorted({r["full_name"] for r in group})))
    print('\nThis tool never writes to the DB. Re-run with --emit to print rows for '
          'data/author_aliases.csv, then apply them with dedup_authors.py --commit.')
    return 0


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--emit', action='store_true',
                    help='print CSV rows for data/author_aliases.csv instead of a human-readable report')
    args = ap.parse_args()
    sys.exit(asyncio.run(main(args.emit)))
