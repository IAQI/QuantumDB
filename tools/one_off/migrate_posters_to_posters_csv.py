#!/usr/bin/env python3
"""One-time migration: move ``paper_type=poster`` rows out of each conference's
``talks.csv`` into a dedicated ``posters.csv``.

Posters now live in their own per-conference ``posters.csv`` (same 18-column
schema), keeping the hand-curated ``talks.csv`` free of the far-more-numerous
poster rows and guaranteeing a single canonical file per poster (so the importer
never generates colliding ``{VENUE}{YEAR}-poster-{index}`` keys).

For each affected conference this script:
  1. Reads ``talks.csv``.
  2. Removes every ``paper_type=poster`` row from ``talks.csv`` and rewrites it.
  3. Writes the *real* poster rows (dropping bare "Poster Session N" schedule
     placeholders — those carry no title/authors) to ``posters.csv``.

QCrypt 2020/2021/2022 only had placeholder poster rows in ``talks.csv``; their
real posters are scraped separately (``scrape_to_csv.py posters``), so this
script just strips the placeholders and writes no ``posters.csv`` for them.
QCrypt 2023/2024/2025 are JSON-sourced: after this runs, ``qcrypt_json_to_csv.py``
regenerates their ``posters.csv`` from the raw JSON.

Idempotent: a second run finds no poster rows in ``talks.csv`` and leaves an
existing ``posters.csv`` untouched.

Usage: python3 tools/one_off/migrate_posters_to_posters_csv.py
"""
import csv
import re
from pathlib import Path

CONF_ROOT = Path(__file__).resolve().parents[2] / "data" / "conferences"

DIRS = [
    "qcrypt_2017", "qcrypt_2020", "qcrypt_2021", "qcrypt_2022",
    "qcrypt_2023", "qcrypt_2024", "qcrypt_2025", "qip_2008", "qip_2025",
]

_PLACEHOLDER_RE = re.compile(r"^\s*poster session\b", re.IGNORECASE)


def _is_placeholder(row: dict) -> bool:
    title = (row.get("title") or "").strip()
    return not title or bool(_PLACEHOLDER_RE.match(title))


def migrate(conf_dir: str) -> None:
    d = CONF_ROOT / conf_dir
    talks_path = d / "talks.csv"
    if not talks_path.exists():
        print(f"{conf_dir}: no talks.csv, skipping")
        return

    with talks_path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        fields = reader.fieldnames
        rows = list(reader)

    kept = [r for r in rows if r["paper_type"] != "poster"]
    poster_rows = [r for r in rows if r["paper_type"] == "poster"]
    real_posters = [r for r in poster_rows if not _is_placeholder(r)]
    placeholders = len(poster_rows) - len(real_posters)

    if len(kept) != len(rows):
        with talks_path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=fields)
            writer.writeheader()
            writer.writerows(kept)

    posters_path = d / "posters.csv"
    if real_posters:
        with posters_path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=fields)
            writer.writeheader()
            writer.writerows(real_posters)

    print(
        f"{conf_dir}: talks {len(rows)}->{len(kept)}, "
        f"posters extracted {len(real_posters)} "
        f"({placeholders} placeholders dropped)"
        + ("" if real_posters else " [no posters.csv written]")
    )


if __name__ == "__main__":
    for conf in DIRS:
        migrate(conf)
