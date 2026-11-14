#!/usr/bin/env python3
"""One-off: clear `speakers` columns that just repeat the full author list.

Many talk CSVs (mostly TQC 2013-2025 proceedings/workshop, plus QIP 2020) were
seeded with `speakers` = every author, as a placeholder: the source named no
presenter. While the importer only honoured a single speaker this did no harm
(several speakers resolved to "no presenter"). Now that a talk can have several
presenters (migration 20261114000000_multiple_presenters), those rows would
mark every author as a presenter, so they are cleared here.

A row is cleared when it has two or more authors and its `speakers` list equals
its `authors` list. Rows where a source really does name every author as a
presenter are kept (KEEP below).

Report-only by default; pass --write to update the CSVs (line endings kept).

Usage:
    python3 tools/one_off/clear_placeholder_speakers.py [--write]
"""
from __future__ import annotations

import argparse
import csv
import io
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
NOTE = "presenter=unknown (speakers was the full author list)"

# (conference dir, title) of rows whose source names every author as a presenter.
KEEP = {
    # Industry panel: every panellist spoke (https://qcrypt.net/2026/speakers/).
    ("qcrypt_2026", "Quantum Satellite Infrastructure and Applications"),
    # The QIP 2026 poster page underlines both names as presenters.
    ("qip_2026", "Lifting the maximally-entangledness assumption in robust self-testing"),
}


def split(value: str | None) -> list[str]:
    return [s.strip() for s in (value or "").split(";") if s.strip()]


def add_note(notes: str) -> str:
    parts = [p.strip() for p in notes.split(";") if p.strip()]
    if NOTE not in parts:
        parts.append(NOTE)
    return "; ".join(parts)


def process(path: Path, write: bool) -> tuple[int, int]:
    raw = path.read_bytes()
    eol = "\r\n" if b"\r\n" in raw else "\n"
    rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8"), newline="")))
    if not rows or "speakers" not in rows[0]:
        return 0, 0
    conf = path.parent.name
    cleared = kept = 0
    for r in rows:
        authors, speakers = split(r.get("authors")), split(r.get("speakers"))
        if len(authors) < 2 or speakers != authors:
            continue
        if any(conf == c and r["title"].startswith(t) for c, t in KEEP):
            kept += 1
            continue
        r["speakers"] = ""
        if "notes" in r:
            r["notes"] = add_note(r["notes"] or "")
        cleared += 1
    if write and cleared:
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=list(rows[0].keys()), lineterminator=eol)
        w.writeheader()
        w.writerows(rows)
        path.write_bytes(buf.getvalue().encode("utf-8"))
    return cleared, kept


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--write", action="store_true", help="update the CSV files")
    args = ap.parse_args()
    total_cleared = total_kept = 0
    for path in sorted((ROOT / "data/conferences").glob("*/*.csv")):
        cleared, kept = process(path, args.write)
        if cleared or kept:
            print(f"{path.relative_to(ROOT)}: {cleared} cleared, {kept} kept")
        total_cleared += cleared
        total_kept += kept
    print(f"Total: {total_cleared} cleared, {total_kept} kept"
          + ("" if args.write else " (report only; pass --write)"))


if __name__ == "__main__":
    main()
