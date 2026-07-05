#!/usr/bin/env python3
"""One-off: backfill QCrypt 2016 talk speakers/authors from the local site mirror.

The reusable `tools/scrapers/talks/qcrypt.py` scraper deliberately punts on 2016
(its schedule pages are ad-hoc bgcolor tables / navigation pages), so the 33
contributed/invited/tutorial rows in `data/conferences/qcrypt_2016/talks.csv`
were imported with empty `speakers`/`authors` columns and fail import as
"no authors". Every such row, however, carries a provenance anchor in its `notes`
column of the form:

    Source link: ../<page>#<surname>; yt_match=...

which points into the local mirror at ~/Web/qcrypt.iaqi.org/2016/. On those pages
each talk is marked with `<a name="<surname>">` followed by its title and byline:

  - invited / tutorial pages:  “Title”</strong><br /><em>Full Name, Affiliation</em>
  - contributed pages:          “Title”  by Author A and Author B

This script reads each empty row, resolves its anchor to a byline in the mirror,
and fills `speakers`/`authors` (+ `affiliations` for invited/tutorial). It writes
nothing unless run with --apply; by default it prints a verification table so the
extracted names can be eyeballed against the mirror titles first.

Usage:
    python3 tools/one_off/qcrypt2016_backfill_authors.py            # dry-run table
    python3 tools/one_off/qcrypt2016_backfill_authors.py --apply    # rewrite CSV
"""
from __future__ import annotations

import csv
import html
import os
import re
import sys
from pathlib import Path

CSV_PATH = Path("data/conferences/qcrypt_2016/talks.csv")
MIRROR = Path(os.path.expanduser("~/Web/qcrypt.iaqi.org/2016"))

# notes: "Source link: ../contributed-talks.1.html#alagic; yt_match=1.00"
ANCHOR_RE = re.compile(r"Source link:\s*\.\./([^#\s;]+)#([A-Za-z0-9_-]+)")
STRONG_RE = re.compile(r"<strong>(.*?)</strong>", re.S)
EM_RE = re.compile(r"<em>(.*?)</em>", re.S)
BY_RE = re.compile(r"^(?:</a>|[\s\xa0])*by\s+(.+?)(?:<br|</p>|</strong>|</em>)", re.S | re.I)


def strip_tags(s: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", " ", s)).strip()


def decode_page(page: str) -> str:
    """The notes store URL-encoded filenames (index.html%3Fp=2459.html); the file
    on disk keeps the literal '?' (index.html?p=2459.html)."""
    return page.replace("%3F", "?").replace("%3f", "?")


def block_for_anchor(page_text: str, anchor: str) -> str | None:
    """The HTML slice from this talk's anchor to the next anchor (or +900 chars)."""
    m = re.search(r'name="' + re.escape(anchor) + r'"', page_text)
    if not m:
        return None
    start = m.end()
    nxt = re.search(r'<a name="', page_text[start:])
    end = start + nxt.start() if nxt else start + 900
    return page_text[start:end]


def split_authors(byline: str) -> list[str]:
    """Split 'A, B, and C' / 'A, B and C' / 'A and B' / 'A' into names."""
    byline = byline.strip().rstrip(".")
    byline = re.sub(r",?\s+and\s+", ";", byline)  # Oxford or plain 'and'
    parts = re.split(r"[;,]", byline)
    return [p.strip() for p in parts if p.strip()]


def parse_people(block: str) -> tuple[list[str], list[str], str]:
    """Return (authors, affiliations, title_seen). Affiliations is [] for the
    contributed 'by ...' form (no affiliation given on those pages).

    Layout on the mirror pages, anchored on the <strong> title:
      contributed:      <strong>“Title”</strong>by A, B and C<br/>|</p>
      invited/tutorial: <strong>[Tutorial:] “Title”</strong><br/><em>Name, Affil</em>
    The 'by' byline is checked first and is anchored to the text immediately
    after </strong>, so a combined-talk "<em>Note: … combined …</em>" elsewhere in
    the block can never be mistaken for the author list.
    """
    title_seen = ""
    ms = STRONG_RE.search(block)
    rest = block
    if ms:
        title_seen = strip_tags(ms.group(1))
        title_seen = re.sub(r"^tutorial:\s*", "", title_seen, flags=re.I).strip("“”\" ")
        rest = block[ms.end():]

    # Contributed: "by A, B and C" right after the title.
    mby = BY_RE.match(rest)
    if mby:
        authors = split_authors(strip_tags(mby.group(1)))
        return authors, [], title_seen

    # Invited / tutorial: <em>Full Name, Affiliation</em> (single speaker in 2016).
    em = EM_RE.search(block)
    if em:
        text = strip_tags(em.group(1))
        if not text.lower().startswith("note"):
            name, _, affil = text.partition(",")
            name, affil = name.strip(), affil.strip()
            if name:
                return [name], ([affil] if affil else []), title_seen

    return [], [], title_seen


def load_page(page: str) -> str | None:
    fp = MIRROR / decode_page(page)
    if not fp.exists():
        return None
    return fp.read_text(encoding="utf-8", errors="replace")


def main() -> int:
    apply = "--apply" in sys.argv
    if not CSV_PATH.exists():
        print(f"missing {CSV_PATH}", file=sys.stderr)
        return 2
    if not MIRROR.exists():
        print(f"missing mirror {MIRROR}", file=sys.stderr)
        return 2

    with CSV_PATH.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        fieldnames = reader.fieldnames
        rows = list(reader)

    page_cache: dict[str, str | None] = {}
    filled = 0
    unresolved = []
    print(f"{'CSV title':45} | {'HTML title':45} | authors | affil")
    print("-" * 130)
    for r in rows:
        has_people = (r.get("speakers") or "").strip() or (r.get("authors") or "").strip()
        if has_people:
            continue
        m = ANCHOR_RE.search(r.get("notes", "") or "")
        if not m:
            continue  # filler rows (no source anchor) — left for the skip filter
        page, anchor = m.group(1), m.group(2)
        pt = page_cache.setdefault(page, load_page(page))
        if pt is None:
            unresolved.append((r.get("title", ""), f"page missing: {page}"))
            continue
        block = block_for_anchor(pt, anchor)
        if not block:
            unresolved.append((r.get("title", ""), f"anchor missing: #{anchor}"))
            continue
        authors, affils, title_seen = parse_people(block)
        if not authors:
            unresolved.append((r.get("title", ""), f"no byline at #{anchor}"))
            continue

        csv_title = (r.get("title") or "").strip()
        names = "; ".join(authors)
        r["speakers"] = names if len(authors) == 1 else ""  # single speaker => presenter
        r["authors"] = names
        if affils:
            r["affiliations"] = "; ".join(affils)
        filled += 1
        flag = "" if title_seen.lower()[:20] == csv_title.lower()[:20] else "  <-- TITLE MISMATCH"
        print(f"{csv_title[:45]:45} | {title_seen[:45]:45} | {names} | {'; '.join(affils)}{flag}")

    print("-" * 130)
    print(f"filled: {filled}   unresolved: {len(unresolved)}")
    for t, why in unresolved:
        print(f"  UNRESOLVED: {t[:60]!r} -> {why}")

    if apply and filled:
        with CSV_PATH.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=fieldnames)
            w.writeheader()
            w.writerows(rows)
        print(f"\nWROTE {CSV_PATH}")
    elif not apply:
        print("\n(dry-run; re-run with --apply to write)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
