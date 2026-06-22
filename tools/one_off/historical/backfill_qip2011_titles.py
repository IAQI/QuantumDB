#!/usr/bin/env python3
"""Backfill QIP 2011 talk titles (+ speakers, types) from our static IAQI copy.

The original historical scrape pulled the 2011 timetable but looked for the
title in an <em> tag (the 2010 layout); 2011 wraps titles in <i>, so every
title came back empty. Speakers/authors and arXiv ids were captured fine, and
the existing CSV already has video_url links we must NOT clobber — so this is a
surgical in-place backfill of the title/speaker/paper_type columns only.

Source: ~/Web/qip.iaqi.org/2011/scientificprogramme/index.html
  Each talk is a <td> with direct children:
    <b>authors (plenary|featured markers): </b> <i>title</i> <a>Abstract|Lecture|Watch</a> arXiv link
  Presenter = the underlined <u> name when present, else the sole author.

Matching to the existing CSV: by arXiv id first, then by normalized author-set.
Pure schedule fillers (lunch/break/registration/...) are dropped; notable
non-talks (Public Lecture, Poster session) are kept with a sensible paper_type.

Dry-run by default; pass --apply to rewrite the CSV.
"""
import argparse
import csv
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
CSV_PATH = REPO / "data" / "conferences" / "qip_2011" / "talks.csv"
ARCHIVE = Path.home() / "Web" / "qip.iaqi.org" / "2011" / "scientificprogramme" / "index.html"

# pure fillers -> drop entirely (substring match on the normalized author field)
DROP_KEYWORDS = (
    "lunch", "break", "registration", "welcome", "reception", "coffee",
    "dinner", "excursion", "free time", "free afternoon", "social",
    "business meeting", "rump session", "opening", "closing",
)
# session labels in the archive that are NOT contributed talks (kept out of the
# fuzzy match pool so they can't be assigned to a real talk row)
SESSION_LABEL_RE = re.compile(
    r"^(poster session|public lecture|business meeting|rump session|"
    r"tutorial|opening|closing)", re.IGNORECASE)


def is_filler(author_field):
    n = norm(author_field)
    return any(k in n for k in DROP_KEYWORDS)


def norm(s):
    s = (s or "").lower()
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def fam_set(authors_field):
    """Set of family names (last token) from a ';'-joined author list."""
    out = set()
    for a in (authors_field or "").split(";"):
        toks = norm(a).split()
        if toks:
            out.add(toks[-1])
    return out


def parse_archive():
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(ARCHIVE.read_text(errors="ignore"), "html.parser")
    recs = []
    seen = set()
    for td in soup.find_all("td"):
        kids = [c.name for c in td.children if getattr(c, "name", None)]
        if "b" not in kids or "i" not in kids:
            continue
        b = td.find("b", recursive=False)
        i = td.find("i", recursive=False)
        title = i.get_text(" ", strip=True)
        if not title:
            continue
        # The "(plenary, ...)" / "(featured)" marker is a text node AFTER </b>,
        # before <i>. Read the whole prefix up to the title for type detection.
        prefix = td.get_text(" ", strip=True).split(title, 1)[0].lower()
        ptype = ("plenary" if "plenary" in prefix
                 else "invited" if "featured" in prefix else "regular")
        authors = re.sub(r"\s*\([^)]*\)\s*", " ", b.get_text(" ", strip=True)).strip().rstrip(":").strip()
        u = td.find("u")
        presenter = u.get_text(" ", strip=True) if u else ""
        m = re.search(r"arxiv\.org/abs/([\d.]+)", str(td), re.I)
        arxiv = m.group(1) if m else ""
        key = (arxiv, norm(title))
        if key in seen:
            continue
        seen.add(key)
        recs.append({"title": title, "authors": authors, "presenter": presenter,
                     "type": ptype, "arxiv": arxiv,
                     "is_session": bool(SESSION_LABEL_RE.match(authors))})
    return recs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="rewrite the CSV (default: preview)")
    args = ap.parse_args()

    if not ARCHIVE.exists():
        sys.exit(f"archive not found: {ARCHIVE}")

    arch = parse_archive()
    by_ax = {r["arxiv"]: r for r in arch if r["arxiv"]}
    print(f"archive talk records: {len(arch)} (with arxiv: {len(by_ax)})\n", file=sys.stderr)

    with open(CSV_PATH, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        fields = reader.fieldnames
        rows = list(reader)

    talk_pool = [r for r in arch if not r["is_session"]]
    used = set()
    out_rows = []
    n_fill = n_speaker = n_type = n_drop = n_unmatched = n_keep = 0

    for row in rows:
        author_field = row.get("authors", "")
        nf = norm(author_field)

        # pure schedule filler -> drop
        if is_filler(author_field):
            n_drop += 1
            print(f"  DROP   filler        : {author_field}")
            continue

        # notable non-talks -> keep, set a sensible paper_type + title/speaker
        # (read directly from the archive; container rows, no individual papers)
        if nf.startswith("poster session"):
            label = author_field.strip()  # "Poster session 1" / "... 2"
            row["title"] = label
            row["speaker"] = ""
            row["authors"] = ""
            row["paper_type"] = "poster"
            row["notes"] = "; ".join(t for t in [row.get("notes", ""),
                                                  "organized by Cédric Bény"] if t)
            n_keep += 1
            print(f"  KEEP   poster        : {label!r}")
            out_rows.append(row)
            continue
        if nf.startswith("public lecture"):
            row["title"] = "Information is Quantum"
            row["speaker"] = "Charles Bennett"
            row["authors"] = "Charles Bennett"
            row["paper_type"] = "keynote"
            n_keep += 1
            print(f"  KEEP   keynote       : 'Information is Quantum' (Charles Bennett)")
            out_rows.append(row)
            continue

        rec = None
        for a in (row.get("arxiv_ids") or "").split(";"):
            a = a.strip()
            if a in by_ax and id(by_ax[a]) not in used:
                rec = by_ax[a]
                break
        if rec is None:  # fall back to family-name overlap (talk pool only)
            csv_fams = fam_set(author_field)
            best, score = None, 0
            for r in talk_pool:
                if id(r) in used:
                    continue
                ov = len(csv_fams & fam_set(r["authors"].replace(" and ", ";").replace(",", ";")))
                if ov > score:
                    best, score = r, ov
            if best and score >= 1:
                rec = best

        if rec is None:
            n_unmatched += 1
            print(f"  UNMATCHED            : {author_field[:40]!r}")
            out_rows.append(row)
            continue

        used.add(id(rec))
        if not (row.get("title") or "").strip():
            n_fill += 1
        row["title"] = rec["title"]

        speaker = rec["presenter"]
        if not speaker:
            au = [x.strip() for x in rec["authors"].replace(" and ", ",").split(",") if x.strip()]
            if len(au) == 1:
                speaker = au[0]
        if speaker and norm(speaker) != norm(row.get("speaker", "")):
            n_speaker += 1
            row["speaker"] = speaker

        if rec["type"] != "regular" and row.get("paper_type") != rec["type"]:
            n_type += 1
            row["paper_type"] = rec["type"]

        via = "arxiv" if rec["arxiv"] in (row.get("arxiv_ids") or "") else "fuzzy"
        print(f"  {rec['type']:8} [{via}] {(row.get('speaker') or '')[:18]:20} -> {rec['title'][:52]}")
        out_rows.append(row)

    print(f"\nfilled titles  : {n_fill}")
    print(f"speakers set    : {n_speaker}")
    print(f"types upgraded  : {n_type}")
    print(f"notable kept    : {n_keep}")
    print(f"filler dropped  : {n_drop}")
    print(f"unmatched rows  : {n_unmatched}")
    print(f"archive talks used: {len(used)}/{len(talk_pool)}")
    print(f"rows in -> out  : {len(rows)} -> {len(out_rows)}")

    if args.apply:
        with open(CSV_PATH, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
            w.writeheader()
            w.writerows(out_rows)
        print(f"\nWROTE {CSV_PATH}")
    else:
        print("\n(dry run — pass --apply to write)")


if __name__ == "__main__":
    main()
