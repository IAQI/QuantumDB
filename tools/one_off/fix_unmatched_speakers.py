#!/usr/bin/env python3
"""One-off: fix `speakers` values that match none of the talk's authors.

Since the importer started warning about speakers who are not authors
(migration 20261114000000_multiple_presenters), a re-import listed 18 such
speakers. Most are spelling variants of an author's name, or the BibTeX-style
author list ("X and Y") copied into `speakers`. The last five were checked by
hand in the recordings (Speaker Picker, 2026-11-14): three are real non-author
presenters (kept, with a note), one is a name variant of the same person, and
one row had a moderator label in its author field.

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

# (csv path, title prefix, current speakers, new speakers, note to add)
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
    # Checked by hand in the recordings (Speaker Picker, 2026-11-14).
    ("qip_2022/talks.csv", "Test of Quantumness with Small-Depth Quantum Circuits", "Zhenning Liu",
     "Zhenning Liu", "presenter=manual_video_check (merged with Gheorghiu-Liu; Liu presented, not an author of this paper)"),
    ("qip_2023/talks.csv", "Inevitability of knowing less than nothing", "Ludovico Lami",
     "Ludovico Lami", "presenter=manual_video_check (stand-in, not an author)"),
    ("qip_2023/talks.csv", "Unitary property testing lower bounds by polynomials", "Can Bostanci",
     "Can Bostanci", "presenter=manual_video_check (stand-in, not an author)"),
    # John Bostanci and Can Bostanci are the same person, who goes by Can
    # (alias added to data/author_aliases.csv).
    ("qip_2026/talks.csv", "Local transformations of bipartite entanglement are rigid", "John Bostanci",
     "Can Bostanci", "presenter=manual_video_check (John Bostanci = Can Bostanci)"),
]

# Rows whose author list itself was wrong:
# (csv path, title prefix, current authors, new authors, new speakers, note to add)
AUTHOR_FIXES = [
    # The author field held the label "Animated by Philippe Grangier". Per the
    # recording, the four panellists all spoke and Grangier moderated.
    ("qcrypt_2014/talks.csv", "Conference and Roundtable", "Animated by Philippe Grangier",
     "Gilles Brassard;Charles H. Bennett;Peter Shor;Artur Ekert",
     "Gilles Brassard;Charles H. Bennett;Peter Shor;Artur Ekert",
     "moderator=Philippe Grangier; presenter=manual_video_check (panel: all four spoke)"),
]


def add_note(notes: str, note: str | None) -> str:
    if not note:
        return notes
    parts = [p.strip() for p in notes.split(";") if p.strip()]
    for part in (p.strip() for p in note.split(";")):
        if part not in parts:
            parts.append(part)
    return "; ".join(parts)


def find(rows: list[dict], rel: str, title: str) -> dict:
    hits = [r for r in rows if r["title"].startswith(title)]
    assert len(hits) == 1, (rel, title, len(hits))
    return hits[0]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--write", action="store_true", help="update the CSV files")
    args = ap.parse_args()
    files = sorted({f[0] for f in FIXES} | {f[0] for f in AUTHOR_FIXES})
    applied = already = 0
    for rel in files:
        path = ROOT / "data/conferences" / rel
        raw = path.read_bytes()
        eol = "\r\n" if b"\r\n" in raw else "\n"
        rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8"), newline="")))
        changed = False
        for frel, title, old, new, note in FIXES:
            if frel != rel:
                continue
            r = find(rows, rel, title)
            notes = add_note(r.get("notes") or "", note)
            if r["speakers"] == new and notes == (r.get("notes") or ""):
                already += 1
                continue
            assert r["speakers"] in (old, new), (rel, title, r["speakers"])
            print(f"{rel}: {title[:55]!r}: speakers {r['speakers']!r} -> {new!r}")
            r["speakers"], r["notes"] = new, notes
            applied += 1
            changed = True
        for frel, title, old_authors, authors, speakers, note in AUTHOR_FIXES:
            if frel != rel:
                continue
            r = find(rows, rel, title)
            if r["authors"] == authors and r["speakers"] == speakers:
                already += 1
                continue
            assert r["authors"] == old_authors, (rel, title, r["authors"])
            print(f"{rel}: {title[:55]!r}: authors {old_authors!r} -> {authors!r}")
            r["authors"], r["speakers"] = authors, speakers
            r["notes"] = add_note(r.get("notes") or "", note)
            applied += 1
            changed = True
        if args.write and changed:
            buf = io.StringIO()
            w = csv.DictWriter(buf, fieldnames=list(rows[0].keys()), lineterminator=eol)
            w.writeheader()
            w.writerows(rows)
            path.write_bytes(buf.getvalue().encode("utf-8"))
    print(f"{applied} changed, {already} already fixed"
          + ("" if args.write else " (report only; pass --write)"))


if __name__ == "__main__":
    main()
