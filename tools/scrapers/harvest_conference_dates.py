#!/usr/bin/env python3
"""Harvest conference start/end dates and bake them into the seed SQL.

The ``conferences`` table has ``start_date``/``end_date DATE`` columns, but the
seed files that create the rows historically left them NULL. This script fills
them in.

Primary source: the per-conference schedule CSVs
(``data/conferences/<venue>_<year>/{talks,workshop,proceedings}.csv``) carry an
ISO ``scheduled_date`` column. The conference span is
``start_date = MIN(scheduled_date)`` and ``end_date = MAX(scheduled_date)`` across
those files. QIP tutorial rows carry their (earlier) ``scheduled_date`` too, so
the MIN naturally counts tutorial days as conference days.

For conference-years with no dated CSV rows (or no CSV dir at all), dates come
from ``MANUAL_DATES`` below — harvested from the local static mirrors under
``/Users/chris/Web/{qip,tqc,qcrypt}.iaqi.org/<year>/`` or, where no local copy
exists, from the web (source recorded in the comment beside each entry).

Usage:
    python tools/scrapers/harvest_conference_dates.py            # report table
    python tools/scrapers/harvest_conference_dates.py --emit-sql # print UPDATE stmts
    python tools/scrapers/harvest_conference_dates.py --write-seeds  # patch seed SQL
    python tools/scrapers/harvest_conference_dates.py --check    # diff vs seed SQL
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data" / "conferences"
SEED_FILES = {
    "QIP": REPO_ROOT / "seeds" / "insert_qip_conferences.sql",
    "QCRYPT": REPO_ROOT / "seeds" / "insert_qcrypt_conferences.sql",
    "TQC": REPO_ROOT / "seeds" / "insert_tqc_conferences.sql",
}
SCHEDULE_CSVS = ("talks.csv", "workshop.csv", "proceedings.csv")

# Dir prefix -> DB venue string.
VENUE_FROM_PREFIX = {"qip": "QIP", "qcrypt": "QCRYPT", "tqc": "TQC"}

_MONTHS = {
    m.lower(): i
    for i, m in enumerate(
        [
            "January", "February", "March", "April", "May", "June",
            "July", "August", "September", "October", "November", "December",
        ],
        start=1,
    )
}
_MONTHS.update({m[:3]: i for m, i in list(_MONTHS.items())})

# (venue, year) -> (start_date, end_date, source note). Used for conference-years
# with no dated CSV rows. Dates are inclusive of tutorial/pre-conference days.
MANUAL_DATES: dict[tuple[str, int], tuple[str, str, str]] = {
    # QIP 2003: MSRI Berkeley. Local mirror qip.iaqi.org/2003/index.html:
    # "December 13, 2002 to December 17, 2002" (the 2003 edition was held Dec 2002).
    ("QIP", 2003): ("2002-12-13", "2002-12-17", "mirror"),
    # QIP 2004: Waterloo. Local mirror qip.iaqi.org/2004/details.html: "January 15 - 19, 2004".
    ("QIP", 2004): ("2004-01-15", "2004-01-19", "mirror"),
    # QIP 2022: Caltech/Pasadena. No local mirror. Tutorials Mar 5-6, conference Mar 7-11
    # (tutorial days counted as conference days). Source: caltech.edu news + QIP CfS.
    ("QIP", 2022): ("2022-03-05", "2022-03-11", "web:caltech.edu"),
    # QCrypt 2026: Ottawa (uOttawa CRX). No CSV yet. Source: qcrypt.net/2026/ (Aug 24-28, 2026).
    ("QCRYPT", 2026): ("2026-08-24", "2026-08-28", "web:qcrypt.net"),
    # TQC 2009: IQC Waterloo. Mirror lacks the span; Springer LNCS 5906 records "May 11-13".
    ("TQC", 2009): ("2009-05-11", "2009-05-13", "web:springer"),
    # TQC 2010: Leeds. Local mirror tqc.iaqi.org/2010/announce.html: "April 13-15, 2010".
    ("TQC", 2010): ("2010-04-13", "2010-04-15", "mirror"),
    # TQC 2018: Sydney. Local mirror tqc.iaqi.org/2018/ index: main conference "16-18 July 2018"
    # (satellite workshop Jul 19-20 and Haquathon Jul 14-15 are separate, not counted).
    ("TQC", 2018): ("2018-07-16", "2018-07-18", "mirror"),
    # TQC 2026: Sherbrooke, Quebec. No CSV yet. Source: tqc-conference.org/2026/ (Aug 31-Sep 4).
    ("TQC", 2026): ("2026-08-31", "2026-09-04", "web:tqc-conference.org"),
}


def _parse_date(raw: str, fallback_year: int) -> dt.date | None:
    """Parse a scheduled_date cell. Handles ISO ``YYYY-MM-DD`` and the
    ``DD Month[ YYYY]`` / ``Month DD[, YYYY]`` forms used by qip_2026."""
    s = (raw or "").strip()
    if not s:
        return None
    # ISO first.
    m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})$", s)
    if m:
        y, mo, d = (int(g) for g in m.groups())
        try:
            return dt.date(y, mo, d)
        except ValueError:
            return None
    # "28 January" / "28 January 2026"
    m = re.match(r"^(\d{1,2})\s+([A-Za-z]+)(?:,?\s+(\d{4}))?$", s)
    if m:
        d = int(m.group(1))
        mo = _MONTHS.get(m.group(2).lower())
        y = int(m.group(3)) if m.group(3) else fallback_year
        if mo:
            try:
                return dt.date(y, mo, d)
            except ValueError:
                return None
    # "January 28" / "January 28, 2026"
    m = re.match(r"^([A-Za-z]+)\s+(\d{1,2})(?:,?\s+(\d{4}))?$", s)
    if m:
        mo = _MONTHS.get(m.group(1).lower())
        d = int(m.group(2))
        y = int(m.group(3)) if m.group(3) else fallback_year
        if mo:
            try:
                return dt.date(y, mo, d)
            except ValueError:
                return None
    return None


def derive_from_csvs(conf_dir: Path, year: int) -> tuple[dt.date | None, dt.date | None, int]:
    """Return (min_date, max_date, dated_row_count) across the schedule CSVs."""
    dates: list[dt.date] = []
    for name in SCHEDULE_CSVS:
        path = conf_dir / name
        if not path.exists():
            continue
        with path.open(newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            if reader.fieldnames is None or "scheduled_date" not in reader.fieldnames:
                continue
            for row in reader:
                parsed = _parse_date(row.get("scheduled_date", ""), year)
                if parsed is not None:
                    dates.append(parsed)
    if not dates:
        return None, None, 0
    return min(dates), max(dates), len(dates)


def collect() -> dict[tuple[str, int], dict]:
    """Return {(venue, year): {start, end, count, source}} for every conf dir."""
    out: dict[tuple[str, int], dict] = {}
    for conf_dir in sorted(DATA_DIR.iterdir()):
        if not conf_dir.is_dir():
            continue
        m = re.match(r"^(qip|qcrypt|tqc)_(\d{4})$", conf_dir.name)
        if not m:
            continue
        venue = VENUE_FROM_PREFIX[m.group(1)]
        year = int(m.group(2))
        start, end, count = derive_from_csvs(conf_dir, year)
        source = "csv"
        if start is None and (venue, year) in MANUAL_DATES:
            s, e, note = MANUAL_DATES[(venue, year)]
            start, end = dt.date.fromisoformat(s), dt.date.fromisoformat(e)
            source = f"manual:{note}"
        out[(venue, year)] = {"start": start, "end": end, "count": count, "source": source}
    # Manual-only entries with no CSV dir at all (e.g. QIP 2003, QCrypt 2026).
    for (venue, year), (s, e, note) in MANUAL_DATES.items():
        if (venue, year) not in out:
            out[(venue, year)] = {
                "start": dt.date.fromisoformat(s),
                "end": dt.date.fromisoformat(e),
                "count": 0,
                "source": f"manual:{note}",
            }
    return out


def print_report(data: dict[tuple[str, int], dict]) -> None:
    print(f"{'venue':7} {'year':5} {'start':11} {'end':11} {'#dated':7} source")
    print("-" * 60)
    gaps: list[tuple[str, int]] = []
    for (venue, year) in sorted(data):
        d = data[(venue, year)]
        start = d["start"].isoformat() if d["start"] else "-- MISSING"
        end = d["end"].isoformat() if d["end"] else "--"
        print(f"{venue:7} {year:<5} {start:11} {end:11} {d['count']:<7} {d['source']}")
        if d["start"] is None:
            gaps.append((venue, year))
    if gaps:
        print("\nGAP conference-years with no date (need MANUAL_DATES entry):")
        for venue, year in gaps:
            print(f"  {venue} {year}")


def emit_sql(data: dict[tuple[str, int], dict]) -> None:
    for (venue, year) in sorted(data):
        d = data[(venue, year)]
        if d["start"] is None:
            continue
        print(
            f"UPDATE conferences SET start_date=DATE '{d['start']}', "
            f"end_date=DATE '{d['end']}' WHERE venue='{venue}' AND year={year};"
        )


# --- seed SQL patching --------------------------------------------------------

_COL_OLD = "(venue, year, city, country, country_code"
_COL_NEW = "(venue, year, start_date, end_date, city, country, country_code"


def _date_literal(d: dt.date | None) -> str:
    return f"DATE '{d}'" if d else "NULL"


def patch_seed_text(text: str, venue: str, data: dict[tuple[str, int], dict]) -> tuple[str, list[str]]:
    """Inject start_date/end_date into one seed file's text. Returns (new_text, warnings)."""
    warnings: list[str] = []
    # 1. Column list.
    if _COL_NEW not in text:
        text = text.replace(_COL_OLD, _COL_NEW, 1)

    # 2. Each VALUES tuple: insert two date literals right after the year.
    tuple_re = re.compile(r"\('(QIP|QCRYPT|TQC)',\s*(\d{4}),\s*(?!DATE |NULL, NULL)")

    def repl(m: re.Match) -> str:
        v, y = m.group(1), int(m.group(2))
        d = data.get((v, y))
        if d is None or d["start"] is None:
            warnings.append(f"{v} {y}: no date -> NULL")
            return f"('{v}', {y}, NULL, NULL, "
        return f"('{v}', {y}, {_date_literal(d['start'])}, {_date_literal(d['end'])}, "

    text = tuple_re.sub(repl, text)

    # 3. ON CONFLICT DO UPDATE SET: keep dates fresh on re-seed.
    if "start_date = EXCLUDED.start_date" not in text:
        text = text.replace(
            "    website_url = EXCLUDED.website_url,",
            "    start_date = EXCLUDED.start_date,\n"
            "    end_date = EXCLUDED.end_date,\n"
            "    website_url = EXCLUDED.website_url,",
            1,
        )
    return text, warnings


def write_seeds(data: dict[tuple[str, int], dict]) -> None:
    for venue, path in SEED_FILES.items():
        text = path.read_text(encoding="utf-8")
        new_text, warnings = patch_seed_text(text, venue, data)
        path.write_text(new_text, encoding="utf-8")
        print(f"patched {path.relative_to(REPO_ROOT)}")
        for w in warnings:
            print(f"  warn: {w}")


def check(data: dict[tuple[str, int], dict]) -> int:
    """Compare CSV-derived dates against what's currently in the seed files."""
    rc = 0
    seed_re = re.compile(
        r"\('(QIP|QCRYPT|TQC)',\s*(\d{4}),\s*(DATE '(\d{4}-\d{2}-\d{2})'|NULL),\s*"
        r"(DATE '(\d{4}-\d{2}-\d{2})'|NULL),"
    )
    for venue, path in SEED_FILES.items():
        text = path.read_text(encoding="utf-8")
        seeded = {}
        for m in seed_re.finditer(text):
            seeded[(m.group(1), int(m.group(2)))] = (m.group(4), m.group(6))
        for (v, y), d in sorted(data.items()):
            if v != venue or d["start"] is None:
                continue
            want = (d["start"].isoformat(), d["end"].isoformat())
            got = seeded.get((v, y))
            if got != want:
                print(f"MISMATCH {v} {y}: seed={got} derived={want}")
                rc = 1
    if rc == 0:
        print("seed dates match derived dates")
    return rc


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--emit-sql", action="store_true", help="print UPDATE statements")
    ap.add_argument("--write-seeds", action="store_true", help="patch the seed SQL files")
    ap.add_argument("--check", action="store_true", help="diff derived dates vs seed SQL")
    args = ap.parse_args()

    data = collect()
    if args.emit_sql:
        emit_sql(data)
    elif args.write_seeds:
        write_seeds(data)
    elif args.check:
        return check(data)
    else:
        print_report(data)
    return 0


if __name__ == "__main__":
    sys.exit(main())
