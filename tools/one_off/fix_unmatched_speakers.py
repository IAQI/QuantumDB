#!/usr/bin/env python3
"""One-off: fix `speakers` values that match none of the talk's authors.

Since the importer started warning about speakers who are not authors
(migration 20261114000000_multiple_presenters), a re-import listed 18 such
speakers. Most are spelling variants of an author's name, or the BibTeX-style
author list ("X and Y") copied into `speakers`; those are fixed here. The rest
are kept as recorded (see REVIEW below).

Report-only by default; pass --write to update the CSVs (line endings kept).

Usage:
    python3 tools/one_off/fix_unmatched_speakers.py [--write]
"""
from __future__ import annotations

import argparse
import csv
import io
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# (csv path, title prefix, current speakers) -> (new speakers, note)
FIXES = [
    # Spelling variants of an author's name: use the author-list spelling.
    ("qip_2019/talks.csv", "A quantitative no-programming theorem", "Aleksander Kubicki",
     "Aleksander Marcin Kubicki", None),
    ("qip_2019/talks.csv", "Quantum singular value transformation and beyond", "András Gilyén",
     "Andras Pal Gilyen", None),
    ("tqc_2023/workshop.csv", "Improved simulation of quantum circuits dominated", "Oliver Reardon",
     "Oliver Reardon-Smith", None),
    ("tqc_2023/workshop.csv", "Quantum theory in finite dimension cannot explain", "Josep Lumbreras Zarapico",
     "Josep Lumbreras", None),
    ("tqc_2023/workshop.csv", "Doubling the order of approximation", "Chien Hung, Cho",
     "Chien-Hung Cho", None),
    ("tqc_2023/workshop.csv", "Single-qubit loss-tolerant quantum position verification", "Llorenç Escolà",
     "Llorenc Escola Farras", None),
    # TQC 2023 merged slot "Christian Bertoni & Mirko Arienzo": two papers, one
    # presenter each; each is an author of only one of them.
    ("tqc_2023/workshop.csv", "Shallow shadows", "Christian Bertoni  &  Mirko Arienzo",
     "Christian Bertoni", "presenter=merged slot with Arienzo's paper"),
    ("tqc_2023/workshop.csv", "Closed-form analytic expressions for shadow estimation", "Christian Bertoni  &  Mirko Arienzo",
     "Mirko Arienzo", "presenter=merged slot with Bertoni's paper"),
    # TQC 2024: the BibTeX author list ("X and Y") was copied into speakers,
    # a placeholder rather than presenter information.
    *[("tqc_2024/workshop.csv", t, s, "", "presenter=unknown (speakers was the BibTeX author list)")
      for t, s in [
          ("Local random quantum circuits form approximate designs", "Shivan Mittal and Nicholas Hunter-Jones"),
          ("Gapped Clique Homology is QMA1-hard", "Robbie King and Tamara Kohler"),
          ("Trained quantum neural networks are Gaussian processes", "Filippo Girardi and Giacomo De Palma"),
          ("An improved Quantum Max Cut approximation via Maximum Matching", "Eunou Lee and Ojas Parekh"),
          ("New Approaches to Complexity via Quantum Graphs", "Eric Culf and Arthur Mehta"),
      ]],
]

# Left as recorded, for a human to check (not changed by this script):
REVIEW = """
- qcrypt_2014 talks.csv, roundtable: authors is "Animated by Philippe Grangier" (moderator label in the author field)
- qip_2022 talks.csv, "Test of Quantumness with Small-Depth Quantum Circuits" (Hirahara, Le Gall row): speaker Zhenning Liu (merged talk?)
- qip_2023 talks.csv, "Inevitability of knowing less than nothing": speaker Ludovico Lami, not an author (stand-in?)
- qip_2023 talks.csv, "Unitary property testing lower bounds by polynomials": speaker Can Bostanci, not an author (stand-in?)
- qip_2026 talks.csv, "Local transformations of bipartite entanglement are rigid": speaker John Bostanci, author Can Bostanci (same person?)
"""


def add_note(notes: str, note: str | None) -> str:
    if not note:
        return notes
    parts = [p.strip() for p in notes.split(";") if p.strip()]
    if note not in parts:
        parts.append(note)
    return "; ".join(parts)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--write", action="store_true", help="update the CSV files")
    args = ap.parse_args()
    by_file: dict[str, list] = {}
    for fix in FIXES:
        by_file.setdefault(fix[0], []).append(fix)
    applied = already = 0
    for rel, fixes in by_file.items():
        path = ROOT / "data/conferences" / rel
        raw = path.read_bytes()
        eol = "\r\n" if b"\r\n" in raw else "\n"
        rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8"), newline="")))
        for _, title, old, new, note in fixes:
            hits = [r for r in rows if r["title"].startswith(title)]
            assert len(hits) == 1, (rel, title, len(hits))
            r = hits[0]
            if r["speakers"] == new:
                already += 1
                continue
            assert r["speakers"] == old, (rel, title, r["speakers"])
            print(f"{rel}: {title[:55]!r}: {old!r} -> {new!r}")
            r["speakers"] = new
            r["notes"] = add_note(r.get("notes") or "", note)
            applied += 1
        if args.write:
            buf = io.StringIO()
            w = csv.DictWriter(buf, fieldnames=list(rows[0].keys()), lineterminator=eol)
            w.writeheader()
            w.writerows(rows)
            path.write_bytes(buf.getvalue().encode("utf-8"))
    print(f"{applied} changed, {already} already fixed"
          + ("" if args.write else " (report only; pass --write)"))
    print("Left for review:" + REVIEW)


if __name__ == "__main__":
    main()
