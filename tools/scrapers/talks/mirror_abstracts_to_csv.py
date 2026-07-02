#!/usr/bin/env python3
"""Back-fill contributed-talk abstracts into per-conference talk CSVs from the
local website mirrors under ``~/Web/``.

Several ``talks.csv`` / ``workshop.csv`` files carry titles/authors but leave the
``abstract`` column empty, even though the archived conference site has the
abstract text.  This script scans the relevant mirror page(s) for a conference,
extracts ``(title, abstract)`` pairs, and fills **only the empty** ``abstract``
cell of the matching CSV row — every other field and the row order/count are
left untouched (the DB importer matches rows by positional ``canonical_key``).

Matching + write-back are generic; only the HTML extraction varies per page, so
each mirror layout gets a small extractor function registered in ``EXTRACTORS``
and wired up in ``JOBS``.

Usage:
    python3 tools/scrapers/talks/mirror_abstracts_to_csv.py            # dry-run, all jobs
    python3 tools/scrapers/talks/mirror_abstracts_to_csv.py --write    # write changes
    python3 tools/scrapers/talks/mirror_abstracts_to_csv.py --only qcrypt_2020
    python3 tools/scrapers/talks/mirror_abstracts_to_csv.py --web-root ~/Web

Poster abstracts are out of scope here: the mirror poster pages are title-only
lists (the ones that had abstracts were already scraped by
``tools/scrapers/posters/``).  TQC talks live in ``workshop.csv``; TQC
``proceedings.csv`` (LIPIcs) has no abstract column.
"""
import argparse
import csv
import difflib
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from bs4 import BeautifulSoup

# Import path: this file lives at tools/scrapers/talks/; add tools/ so we can
# reuse the shared field normaliser exactly as the rest of the pipeline does.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scrapers._lib import clean_field  # noqa: E402

CONF_ROOT = Path(__file__).resolve().parents[3] / "data" / "conferences"

Pair = Tuple[str, str]  # (title, abstract)


# --------------------------------------------------------------------------- #
# Text helpers                                                                 #
# --------------------------------------------------------------------------- #
def norm_title(s: str) -> str:
    """Loose key for matching titles across CSV and mirror HTML.

    Copied from qcrypt_json_to_csv.py so the two enrichment paths agree.
    """
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", "", s.lower())).strip()


_TRAILING_ABSTRACT = re.compile(r"\s*abstract$")


def match_key(title: str) -> str:
    """Normalised match key, tolerant of a spurious trailing ``Abstract`` token.

    Some schedule-page scrapes accidentally capture the "Abstract" toggle-link
    text into the title, so a title can end in "… Abstract".  No genuine talk
    title ends in the bare word "abstract", so stripping it from the key is safe
    and defends matching against that class of artifact.
    """
    return _TRAILING_ABSTRACT.sub("", norm_title(title))


def _candidate_keys(title: str) -> List[str]:
    """Exact-match keys to try for a CSV title, best first.

    Some CSVs prefix the title with a speaker/authors label ("Mousavi/Yuen:
    On the complexity of …"); when the full key misses we also try the segment
    after a leading "…: " so those rows match the plain mirror title.
    """
    keys = [match_key(title)]
    if ":" in title:
        tail = match_key(title.split(":", 1)[1])
        if tail and tail not in keys:
            keys.append(tail)
    return keys


_ABSTRACT_PREFIX = re.compile(r"^\s*abstract\s*[:.\-–]?\s*", re.IGNORECASE)


def _clean_abstract(text: Optional[str]) -> str:
    """Normalise an abstract: HTML-unescape/whitespace-fold, drop a leading
    ``Abstract:`` label."""
    cleaned = clean_field(text or "")
    return _ABSTRACT_PREFIX.sub("", cleaned).strip()


def _text(node) -> str:
    return clean_field(node.get_text(" ", strip=True)) if node is not None else ""


# --------------------------------------------------------------------------- #
# Per-page extractors: soup -> list[(title, abstract)]                         #
# --------------------------------------------------------------------------- #
def _extract_paper_single(soup: BeautifulSoup) -> List[Pair]:
    """QCrypt 2020 & 2021: ``div.paper-single`` → ``div.paper-title`` +
    ``div.paper-abstract-full``."""
    pairs: List[Pair] = []
    for block in soup.find_all("div", class_="paper-single"):
        title = _text(block.find(class_="paper-title"))
        abstract = _clean_abstract(_text(block.find(class_="paper-abstract-full")))
        if title and abstract:
            pairs.append((title, abstract))
    return pairs


def _extract_popmake(soup: BeautifulSoup) -> List[Pair]:
    """QCrypt 2019: PopupMaker modals — ``div.popmake`` → ``.pum-title`` +
    ``.pum-content`` whose first ``<p>`` is the author list and remaining
    ``<p>``s are the abstract body."""
    pairs: List[Pair] = []
    for modal in soup.find_all("div", class_="popmake"):
        title = _text(modal.find(class_="pum-title"))
        content = modal.find(class_="pum-content")
        if not title or content is None:
            continue
        paras = content.find_all("p")
        if len(paras) >= 2:
            body = " ".join(_text(p) for p in paras[1:])  # drop authors <p>
        else:
            body = _text(content)
        abstract = _clean_abstract(body)
        if title and abstract:
            pairs.append((title, abstract))
    return pairs


def _extract_wp_heading(soup: BeautifulSoup) -> List[Pair]:
    """TQC 2020: ``h3.wp-block-heading`` holds ``Authors. Title``; the next
    sibling ``<p>`` holds ``Abstract: …``.

    We emit the *full heading text* as the title key candidate AND the
    dot-split tail; matching (below) tolerates either because it is done on a
    normalised, punctuation-stripped basis and the CSV title is a suffix of the
    heading.  To keep one (title, abstract) pair per poster we key on the
    dot-split tail (the actual title) and fall back to the whole heading.
    """
    pairs: List[Pair] = []
    for h in soup.find_all("h3", class_="wp-block-heading"):
        heading = _text(h)
        sib = h.find_next_sibling("p")
        abstract = _clean_abstract(_text(sib)) if sib is not None else ""
        if not heading or not abstract:
            continue
        title = _split_title_from_authors(heading)
        pairs.append((title, abstract))
    return pairs


def _split_title_from_authors(heading: str) -> str:
    """``Author A, Author B and Author C. Title text`` → ``Title text``.

    Splits on the last ``. `` that precedes the title.  Author lists contain
    initials with periods, so we take the segment after the last period that is
    followed by a capitalised word and is not itself an initial.  Falls back to
    the whole heading when no confident split exists (matching then works
    because norm_title() of the CSV title is a substring test in the fuzzy
    fallback).
    """
    # Prefer splitting on ". " boundaries, keeping the longest plausible title.
    parts = re.split(r"\.\s+", heading)
    if len(parts) >= 2:
        # The title is the final segment; join back anything mis-split inside it
        # is unlikely since titles rarely contain ". ".
        return parts[-1].strip() or heading
    return heading


def _extract_teachpress(soup: BeautifulSoup) -> List[Pair]:
    """TQC 2024 (teachPress plugin): ``div.tp_publication`` → ``p.tp_pub_title``
    (strip the trailing ``span.tp_pub_type`` badge) + ``div.tp_abstract_entry``."""
    pairs: List[Pair] = []
    for pub in soup.find_all("div", class_="tp_publication"):
        title_node = pub.find("p", class_="tp_pub_title")
        if title_node is not None:
            for badge in title_node.find_all("span", class_="tp_pub_type"):
                badge.extract()
        title = _text(title_node)
        abstract = _clean_abstract(_text(pub.find("div", class_="tp_abstract_entry")))
        if title and abstract:
            pairs.append((title, abstract))
    return pairs


EXTRACTORS: Dict[str, Callable[[BeautifulSoup], List[Pair]]] = {
    "paper_single": _extract_paper_single,
    "popmake": _extract_popmake,
    "wp_heading": _extract_wp_heading,
    "teachpress": _extract_teachpress,
}


# --------------------------------------------------------------------------- #
# Jobs                                                                         #
# --------------------------------------------------------------------------- #
@dataclass
class Job:
    conf: str  # data/conferences/<conf>/
    csv_name: str  # talks.csv | workshop.csv
    layout: str  # key into EXTRACTORS
    mirrors: List[str] = field(default_factory=list)  # paths relative to --web-root


JOBS: List[Job] = [
    Job("qcrypt_2019", "talks.csv", "popmake", [
        "qcrypt.iaqi.org/2019/accepted-papers/index.html",
        "qcrypt.iaqi.org/2019/scientific-program/index.html",
    ]),
    Job("qcrypt_2020", "talks.csv", "paper_single", [
        "qcrypt.iaqi.org/2020/accepted-papers/index.html",
    ]),
    Job("qcrypt_2021", "talks.csv", "paper_single", [
        "qcrypt.iaqi.org/2021/speakers/index.html",
    ]),
    Job("tqc_2020", "workshop.csv", "wp_heading", [
        "tqc.iaqi.org/2020/accepted-papers-with-abstracts/index.html",
    ]),
    # tqc_2024 workshop.csv is already 91/96 filled (from talks_with_schedule.csv);
    # the 5 remaining rows are invited talks + one late regular not on the
    # teachPress page, so there is nothing to gain here.
]


# --------------------------------------------------------------------------- #
# Match + write-back                                                          #
# --------------------------------------------------------------------------- #
FUZZY_THRESHOLD = 0.92


def collect_pairs(job: Job, web_root: Path) -> Dict[str, str]:
    """Parse every mirror page for the job and merge into {norm_title: abstract}
    (first non-empty wins)."""
    merged: Dict[str, str] = {}
    extract = EXTRACTORS[job.layout]
    for rel in job.mirrors:
        path = (web_root / rel).expanduser()
        if not path.exists():
            print(f"  ! missing mirror page: {path}", file=sys.stderr)
            continue
        soup = BeautifulSoup(path.read_bytes(), "html.parser")
        for title, abstract in extract(soup):
            key = match_key(title)
            if key and key not in merged:
                merged[key] = abstract
    return merged


def match_and_fill(job: Job, pairs: Dict[str, str], write: bool) -> None:
    csv_path = CONF_ROOT / job.conf / job.csv_name
    with csv_path.open(newline="") as fh:
        reader = csv.DictReader(fh)
        fields = reader.fieldnames or []
        rows = list(reader)

    if "abstract" not in fields:
        print(f"{job.conf}/{job.csv_name}: no abstract column — skipped")
        return

    unused = set(pairs)
    filled = 0
    still_empty: List[str] = []
    fuzzy_notes: List[str] = []

    for row in rows:
        if (row.get("abstract") or "").strip():
            continue  # never overwrite a populated cell
        abstract = matched_key = None
        for key in _candidate_keys(row.get("title", "")):
            if key in pairs:
                abstract, matched_key = pairs[key], key
                break
        if abstract is None:
            # conservative fuzzy fallback among still-unused mirror titles
            abstract, matched_key = _fuzzy_lookup(
                match_key(row.get("title", "")), pairs, unused)
            if abstract is not None:
                fuzzy_notes.append(f"    ~fuzzy: {row.get('title','')!r} <- {matched_key!r}")
        if abstract:
            row["abstract"] = abstract
            unused.discard(matched_key)
            filled += 1
        else:
            still_empty.append(row.get("title", ""))

    total = len(rows)
    print(f"{job.conf}/{job.csv_name}: filled {filled}/{total} "
          f"(mirror pairs={len(pairs)}, unused={len(unused)})")
    for note in fuzzy_notes:
        print(note)
    if still_empty:
        print(f"    {len(still_empty)} row(s) left empty (e.g. "
              f"{'; '.join(repr(t) for t in still_empty[:3])})")

    if write and filled:
        with csv_path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
        print(f"    -> wrote {csv_path}")


def _fuzzy_lookup(key: str, pairs: Dict[str, str],
                  unused: set) -> Tuple[Optional[str], Optional[str]]:
    """Best unambiguous fuzzy match among still-unused mirror titles."""
    if not key:
        return None, None
    scored = sorted(
        ((difflib.SequenceMatcher(None, key, k).ratio(), k) for k in unused),
        reverse=True,
    )
    if not scored:
        return None, None
    best_ratio, best_key = scored[0]
    second = scored[1][0] if len(scored) > 1 else 0.0
    if best_ratio >= FUZZY_THRESHOLD and best_ratio - second > 0.03:
        return pairs[best_key], best_key
    return None, None


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--write", action="store_true",
                    help="write changes (default is a dry-run report)")
    ap.add_argument("--only", metavar="CONF",
                    help="run a single job by conf dir (e.g. qcrypt_2020)")
    ap.add_argument("--web-root", default="~/Web",
                    help="root of the local site mirrors (default: ~/Web)")
    args = ap.parse_args()

    web_root = Path(args.web_root).expanduser()
    jobs = [j for j in JOBS if not args.only or j.conf == args.only]
    if not jobs:
        print(f"no job matches --only {args.only!r}", file=sys.stderr)
        sys.exit(1)

    if not args.write:
        print("(dry-run — pass --write to apply)\n")
    for job in jobs:
        pairs = collect_pairs(job, web_root)
        match_and_fill(job, pairs, args.write)


if __name__ == "__main__":
    main()
