#!/usr/bin/env python3
"""Merge QCrypt raw JSON (accepted papers + posters) into the per-conference
talks.csv.

The conference website exports two JSON files per year under
``data/conferences/<conf>/raw/``:

* ``accepted-papers-<year>.json`` — accepted contributed talks (with abstracts
  and per-author affiliations the CSV is usually missing).
* ``posters-<year>.json`` — the poster session (not otherwise in the CSV).

For each year this script:

1. Enriches matching contributed-talk rows with the abstract (and the aligned
   authors/affiliations) from the accepted-papers file, only filling fields the
   CSV left blank — curated values are never overwritten.
2. Regenerates the conference's ``posters.csv`` wholesale from the posters file
   (any ``paper_type=poster`` rows still in ``talks.csv`` are stripped out), so
   the script is idempotent and posters live in exactly one file.

Usage: python3 tools/scrapers/talks/qcrypt_json_to_csv.py
"""
import csv
import json
import re
from pathlib import Path

CONF_ROOT = Path(__file__).resolve().parents[3] / "data" / "conferences"

# (directory, accepted-papers json, posters json)
YEARS = [
    ("qcrypt_2023", "accepted-papers-2023.json", "posters-2023.json"),
    ("qcrypt_2024", "accepted-papers-2024.json", "posters-2024.json"),
    ("qcrypt_2025", "accepted-papers-2025.json", "posters-2025.json"),
]


def norm_title(s: str) -> str:
    """Loose key for matching titles across the two sources."""
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", "", s.lower())).strip()


def author_strings(authors):
    """Return (names, affiliations) as parallel ;-separated cells.

    affiliations is "" when no author carries one, otherwise a parallel list
    (blank entries kept so order matches authors)."""
    names, affs = [], []
    for a in authors:
        name = " ".join(p for p in (a.get("first"), a.get("last")) if p).strip()
        names.append(name)
        affs.append((a.get("affiliation") or "").strip())
    aff_cell = ";".join(affs) if any(affs) else ""
    return ";".join(names), aff_cell


def process(conf_dir: str, accepted_file: str, posters_file: str):
    d = CONF_ROOT / conf_dir
    csv_path = d / "talks.csv"
    accepted = json.loads((d / "raw" / accepted_file).read_text())
    posters = json.loads((d / "raw" / posters_file).read_text())

    with csv_path.open(newline="") as fh:
        reader = csv.DictReader(fh)
        fields = reader.fieldnames
        rows = list(reader)

    venue = rows[0]["venue"]
    year = rows[0]["year"]

    # 1. enrich talks, dropping any existing poster rows
    acc = {norm_title(p["title"]): p for p in accepted}
    kept, enriched = [], 0
    for row in rows:
        if row["paper_type"] == "poster":
            continue  # regenerated below
        kept.append(row)
        p = acc.get(norm_title(row["title"]))
        if not p:
            continue
        names, affs = author_strings(p.get("authors", []))
        touched = False
        if not row["abstract"].strip() and p.get("abstract"):
            row["abstract"] = p["abstract"].strip()
            touched = True
        if not row["affiliations"].strip() and affs:
            row["authors"] = names  # identical names; keeps affiliation order aligned
            row["affiliations"] = affs
            touched = True
        enriched += touched

    # 2. regenerate poster rows from the posters file
    poster_rows = []
    for p in posters:
        names, affs = author_strings(p.get("authors", []))
        row = {c: "" for c in fields}
        row.update(
            venue=venue,
            year=year,
            paper_type="poster",
            title=p["title"].strip(),
            authors=names,
            affiliations=affs,
            abstract=(p.get("abstract") or "").strip(),
        )
        poster_rows.append(row)

    # talks.csv keeps only non-poster rows (posters live in posters.csv now)
    with csv_path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(kept)

    # posters.csv is regenerated wholesale from the posters JSON (idempotent)
    posters_path = d / "posters.csv"
    with posters_path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(poster_rows)

    print(
        f"{conf_dir}: {len(kept)} talks ({enriched} enriched) -> talks.csv, "
        f"{len(poster_rows)} posters -> posters.csv"
    )


if __name__ == "__main__":
    for args in YEARS:
        process(*args)
