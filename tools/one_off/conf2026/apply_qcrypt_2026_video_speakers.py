#!/usr/bin/env python3
"""Apply the video-inferred QCrypt 2026 presenters to talks.csv.

Reads ``data/conferences/qcrypt_2026/raw/video_speakers.json``, which was built by hand from
the YouTube recordings (opening title slide viewed in a browser + auto-captions), and for each
entry whose title matches a talks.csv row:

* sets ``video_url`` / ``youtube_id`` to the entry's video (this settles duplicates and the
  merged #8/#100 slot, where one video covers two rows),
* fills ``speakers`` when the entry names a presenter who is one of the row's authors,
* tags ``notes`` with ``speaker_source=video_<evidence kind>`` plus any entry note.

Rows that already have a different speaker are reported, never overwritten. Run after
``tools/video_pass.py qcrypt 2026 --write``. Dry run by default; ``--write`` to apply.
"""
import argparse
import csv
import json
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CONF = ROOT / "data" / "conferences" / "qcrypt_2026"
sys.path.insert(0, str(ROOT / "tools"))
from video_pass import update_notes  # noqa: E402


OWN_KEYS = {"speaker_source", "speaker_confidence", "video_note"}


def fold(s):
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    entries = json.loads((CONF / "raw" / "video_speakers.json").read_text())["talks"]
    path = CONF / "talks.csv"
    with open(path, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        fields, rows = reader.fieldnames, list(reader)
    by_title = {fold(r["title"]): r for r in rows}

    unmatched, set_sp, conflicts, unknown = [], [], [], []
    for e in entries:
        row = by_title.get(fold(e["title"]))
        if row is None:
            unmatched.append(e["title"])
            continue
        updates = {}
        # drop our own tags first so re-runs stay idempotent
        row["notes"] = "; ".join(t for t in (row.get("notes") or "").split("; ")
                                 if t.split("=", 1)[0] not in OWN_KEYS)
        row["video_url"] = f"https://www.youtube.com/watch?v={e['youtube_id']}"
        row["youtube_id"] = e["youtube_id"]
        sp = e["speaker"]
        authors = [a.strip() for a in row["authors"].split(";") if a.strip()]
        if not sp:
            unknown.append(row["title"])
        elif fold(sp) not in {fold(a) for a in authors}:
            conflicts.append((row["title"], sp, "not among authors"))
        elif row["speakers"].strip() and fold(row["speakers"]) != fold(sp):
            conflicts.append((row["title"], sp, f"row already has {row['speakers']!r}"))
        else:
            # use the row's own spelling of the author's name
            row["speakers"] = next(a for a in authors if fold(a) == fold(sp))
            ev = e["evidence"]
            kind = ("title_slide" if ev.startswith("title_slide") else
                    "captions" if ev.startswith("caption") else "title")
            updates["speaker_source"] = f"video_{kind}"
            updates["speaker_confidence"] = e["confidence"]
            set_sp.append((row["title"], row["speakers"], e["evidence"]))
        if e.get("note"):
            updates["video_note"] = e["note"].replace(";", ",")
        row["notes"] = update_notes(row.get("notes", ""), updates)

    for t, s, ev in set_sp:
        print(f"  speaker  {s:28s} <- {t[:60]}  [{ev}]")
    for t in unknown:
        print(f"  UNKNOWN  {t[:80]}")
    for t, s, why in conflicts:
        print(f"  CONFLICT {s} for {t[:60]}: {why}")
    for t in unmatched:
        print(f"  NO ROW   {t[:80]}")
    print(f"{len(set_sp)} speakers set, {len(unknown)} unknown, {len(conflicts)} conflicts, "
          f"{len(unmatched)} unmatched")

    if args.write:
        with open(path, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows(rows)
        print(f"wrote {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
