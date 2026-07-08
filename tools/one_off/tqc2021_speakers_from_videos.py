#!/usr/bin/env python3
"""One-off: set TQC 2021 talk presenters identified from the YouTube recordings.

TQC 2021 talks were pre-recorded; each video opens with a title card that marks the
presenter (a name shown prominently / underlined / bolded, or an explicit "joint work
with …" that names the speaker). The workshop.csv `speakers` column had been seeded
with the full author list (so no single presenter was known). By viewing the opening
frames of every talk video, the presenter was read off each title card.

This script embeds that video-derived mapping (youtube_id -> presenter, confidence)
and writes the HIGH-confidence presenters into the `speakers` column, canonicalized to
the row's own author spelling so the talks importer resolves presenter_author_id. Rows
whose confidence is MEDIUM (presenter inferred from first-author + webcam, no explicit
slide marker) or LOW (unresolved: no marker / merged talk) are left untouched and
listed for manual review.

Report-only by default; pass --write to update workshop.csv.

Usage:
    python3 tools/one_off/tqc2021_speakers_from_videos.py [--write]
"""
from __future__ import annotations

import argparse
import csv
import re
import unicodedata
from pathlib import Path

CSV_PATH = Path(__file__).resolve().parents[2] / "data/conferences/tqc_2021/workshop.csv"

# youtube_id -> (presenter, confidence, note). Derived from the title card of each
# talk's TQC 2021 YouTube recording. All HIGH presenters were verified to be authors.
PRESENTERS = {
    '-M0SR9yYGKM': ('Yihui Quek', 'HIGH', ''),
    '07UBj43fXUQ': ('Harold Nieuwboer', 'HIGH', ''),
    '0H2fNE1SAI4': ('Marc-Olivier Renou', 'HIGH', 'name+email footer'),
    '191tRyIo-QA': ('Tamara Kohler', 'HIGH', ''),
    '2vu7Ddm_jzU': ('Leonardo Banchi', 'HIGH', ''),
    '4CXgFzCrOeo': ('Zi-Wen Liu', 'HIGH', ''),
    '4WEuHYunBFo': ('Kun Wang', 'HIGH', 'underlined'),
    '4kmwNB1_6UE': ('Senrui Chen', 'HIGH', 'bolded'),
    '52Y_oU54bGo': ('Aleksander Kubica', 'HIGH', 'underlined'),
    '6VK9eWm4Iss': ('Linghang Kong', 'HIGH', ''),
    '8CYRrtMspDM': ('Carlos Ortiz Marrero', 'HIGH', ''),
    '98W9mdXZbFM': ('Changpeng Shao', 'HIGH', 'highlighted'),
    '9iFNUpJfFE4': ('Aleksander Marcin Kubicki', 'HIGH', 'bolded'),
    '9nWoBsD0grY': ('Daniel Stilck França', 'HIGH', ''),
    'DjHRT_YDWOY': ('Yoshifumi Nakata', 'HIGH', ''),
    'GBsyJT3mAPo': ('Carlo Maria Scandolo', 'HIGH', 'underlined (pilot)'),
    'GzcbGrcCoF8': ("Marcel Dall'Agnol", 'HIGH', 'bolded'),
    'I4yQzHvVPrU': ('Paul Webster', 'HIGH', 'underlined'),
    'IA64rVWZ1cQ': ('Minh Tran', 'HIGH', 'name-card intro (pilot)'),
    'J0BhRQBUieA': ('Michael Beverland', 'HIGH', ''),
    'JlBiSf4hjDk': ('Subhasree Patro', 'HIGH', ''),
    'K_8PHNn6t4s': ('Jonas Helsen', 'HIGH', ''),
    'Oc-pz1MHQXM': ('Ryuji Takagi', 'HIGH', ''),
    'P3h3sLyfS74': ('Patricia Contreras Tejada', 'HIGH', ''),
    'PnLaYEuKKnw': ('Hyejung Hailey Jee', 'HIGH', ''),
    'QASnfBvIhUQ': ('Andrew Guo', 'HIGH', ''),
    'RKIeAr2OCYs': ('Yihui Quek', 'HIGH', '"on behalf of" others (pilot)'),
    'StrYxvte6Ck': ('Lisa Hänggli', 'HIGH', ''),
    'V-0IZrVAWrY': ('Daniel Stilck França', 'HIGH', ''),
    'VV94XBmGCQI': ('Jin-Peng Liu', 'HIGH', ''),
    'VVTH8-Zlqg0': ('Albert H. Werner', 'HIGH', 'first/darker on card'),
    'Ycrlc1ySGJI': ('Sepehr Nezami', 'HIGH', 'named presenter'),
    'b1wYoOOLZCI': ('Michael Zurel', 'HIGH', 'underlined'),
    'ee0dtsFN8l8': ('Kun Fang', 'HIGH', ''),
    'fU33FI5hoWU': ('Jiahui Liu', 'HIGH', 'bolded'),
    'g9b1e2foPyM': ('Nikolas Breuckmann', 'HIGH', '"joint work with Jens Eberhardt"'),
    'hr4j-GtD1fc': ('Srijita Kundu', 'HIGH', ''),
    'j8i37Les6Ac': ('Ulysse Chabaud', 'HIGH', 'underlined'),
    'lNgDRvIOZCM': ('Felix Leditzky', 'HIGH', 'underlined'),
    'o1O6XwxNgLM': ('Sarah Jansen', 'HIGH', 'bolded'),
    'pDw8mF_8yzU': ('Michał Oszmaniec', 'HIGH', 'underlined'),
    'qHMghBbJnY0': ('Zahra Baghali Khanian', 'HIGH', 'webcam = first author'),
    'qmjR2Csr0p4': ('Giacomo De Palma', 'HIGH', 'name on title card + webcam (pilot)'),
    'sek9WFGGTxg': ('Mark Wilde', 'HIGH', 'named presenter, "joint with" the others'),
    'tZOs7oT7BsA': ('Pablo Bonilla', 'HIGH', ''),
    'u-mlYuiiAAw': ('Priyanka Mukhopadhyay', 'HIGH', ''),
    'u2mD4Vd7kGQ': ('Arne Heimendahl', 'HIGH', ''),
    'udMif6cGiuk': ('Shelby Kimmel', 'HIGH', 'bolded'),
    'v6bGXZc-Sco': ('Oscar Higgott', 'HIGH', ''),
    'vrp1gcsslXE': ('Chi-Fang Chen', 'HIGH', ''),
    'wU0SDj6RmRU': ('Shima Bab Hadiashar', 'HIGH', ''),
    'xBk_X9gu6Vs': ('Mischa Woods', 'HIGH', 'underlined (pilot)'),
    'xI_6qQp2Imw': ('James Watson', 'HIGH', ''),
    'xeaLXoPLx5A': ('Jonas Helsen', 'HIGH', ''),
    'zX26x2HIg2Q': ('Armanda O. Quintavalle', 'HIGH', ''),
    # MEDIUM: presenter inferred from first-author + webcam, no explicit slide marker.
    '2kt3Yyl2TGo': ('Dominic Berry', 'HIGH', 'confirmed by organizer'),
    'I1_5BcMjsCE': ('Hsin-Yuan Huang', 'HIGH', 'confirmed by organizer'),
    'NJdcuGDeEiM': ('Antonio Pérez-Hernández', 'HIGH', 'confirmed by organizer'),
    'TDm8GACmEwA': ('Simon Burton', 'HIGH', 'confirmed by organizer'),
    'VLpeTWtZZXs': ('Markus Hasenöhrl', 'HIGH', 'confirmed by organizer'),
    'd9o3RiOgvZY': ('Tomotaka Kuwahara', 'HIGH', 'confirmed by organizer'),
    'gxgCndCLVpQ': ('Vishal Katariya', 'HIGH', 'confirmed by organizer'),
    'ieYcZ3qDYYc': ('Alexander Kliesch', 'HIGH', 'confirmed by organizer'),
    'jUYOjC9Z68g': ('Tomas Jochym-O’Connor', 'HIGH', 'confirmed by organizer; toric-code half of the merged talk'),
}

# The merged video jUYOjC9Z68g covers two papers: the toric-code half (row above)
# and "Locally unencoding the color code", which has no youtube_id of its own.
# The organizer confirmed Michael Vasmer presented that second half.
# title -> (presenter, shared_youtube_id).
MERGED_SECOND_HALF = {
    'Locally unencoding the color code': ('Michael Vasmer', 'jUYOjC9Z68g'),
}


def name_tokens(s):
    s = re.sub(r"\([^)]*\)", " ", s).replace("ß", "ss")
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    # fold ł/ø/đ etc. that NFKD leaves intact, to a bare ascii letter where obvious
    s = s.replace("ł", "l").replace("Ł", "l")
    return [t for t in re.sub(r"[^a-z0-9]+", " ", s.lower()).split() if t]


def canonical_author(name, authors):
    """Return the author string best matching `name` (family + given overlap)."""
    nt = name_tokens(name)
    if not nt:
        return None
    best, best_score = None, 0
    for a in authors:
        at = name_tokens(a)
        if not at:
            continue
        shared = len(set(nt) & set(at))
        if nt[-1] == at[-1] and shared > best_score:
            best, best_score = a, shared
    return best


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="update workshop.csv (default: report only)")
    args = ap.parse_args()

    with CSV_PATH.open() as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)

    applied, skipped, mism = [], [], []
    for r in rows:
        # merged-talk second half: give it the shared video + confirmed presenter
        merged = MERGED_SECOND_HALF.get(r["title"])
        if merged:
            presenter, shared_yid = merged
            r["youtube_id"] = shared_yid
            r["video_url"] = f"https://www.youtube.com/watch?v={shared_yid}"
            authors = [a.strip() for a in r["authors"].split(";") if a.strip()]
            canon = canonical_author(presenter, authors) or presenter
            r["speakers"] = canon
            applied.append((shared_yid, canon, r["title"]))
            continue
        yid = (r.get("youtube_id") or "").strip()
        entry = PRESENTERS.get(yid)
        if not entry:
            continue
        presenter, conf, note = entry
        if conf != "HIGH" or not presenter:
            skipped.append((yid, presenter, conf, note, r["title"]))
            continue
        authors = [a.strip() for a in r["authors"].split(";") if a.strip()]
        canon = canonical_author(presenter, authors)
        if canon is None:
            mism.append((yid, presenter, authors, r["title"]))
            continue
        r["speakers"] = canon
        applied.append((yid, canon, r["title"]))

    print(f"=== APPLIED ({len(applied)} HIGH-confidence presenters) ===")
    for yid, canon, title in applied:
        print(f"  {yid}  {canon:<26} | {title[:50]}")
    print(f"\n=== SKIPPED for manual review ({len(skipped)}: MEDIUM/LOW) ===")
    for yid, sp, conf, note, title in skipped:
        print(f"  [{conf}] {yid}  {sp or '(unresolved)':<22} | {title[:42]} | {note}")
    if mism:
        print(f"\n=== presenter NOT matched to any author ({len(mism)}) ===")
        for yid, sp, authors, title in mism:
            print(f"  {yid}  {sp!r} not in {authors}")

    if args.write:
        with CSV_PATH.open("w", newline="") as f:
            # workshop.csv is stored with CRLF line endings — match to keep the diff minimal
            w = csv.DictWriter(f, fieldnames=fieldnames, lineterminator="\r\n")
            w.writeheader()
            w.writerows(rows)
        print(f"\nWROTE {CSV_PATH}")
    else:
        print("\n(report only; pass --write to update workshop.csv)")


if __name__ == "__main__":
    main()
