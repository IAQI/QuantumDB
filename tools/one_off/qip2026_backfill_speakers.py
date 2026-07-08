#!/usr/bin/env python3
"""One-off: reconcile QIP 2026 talk speakers against the live detailed schedule.

The original `talks.csv` speaker column was built from a PDF-derived HTML snapshot
(`raw/qip_2026_schedule.html`) which carried PDF artifacts and left 6 talks with a
blank `speaker`. The live detailed schedule
(https://qip.iaqi.org/2026/programme/detailed-schedule/) is an Inertia/Laravel app
that embeds the schedule as a single-quoted `JSON.parse('…')` blob in the page HTML.
Within each session's `translations.en.preview_text`, talks are laid out as a bold
title line followed by an author line where the PRESENTER is the markdown-bolded name:

    13:00-13:30 **Can effective descriptions of bosonic systems be considered complete?**
    Francesco Arzani, Robert Booth, **Ulysse Chabaud**

This script:
  1. flattens every preview_text into a line stream,
  2. anchors each talks.csv row on its (ground-truth) title in that stream and reads
     the presenter(s) as the bold name(s) on the following author line — a couple of
     talks retitled between submission and the schedule are handled via an explicit
     OVERRIDES map,
  3. canonicalizes the identified presenter to the row's own `authors` spelling — the
     schedule sometimes adds nicknames ("Zhiyang (Sunny) He") or keeps mojibake
     ("C¸atli") that would break the importer's author lookup — then fills/fixes the
     speaker column, standardizing the header to `speakers` (plural) so the importer
     reads it.

Report-only by default; pass --write to update the CSV.

Usage:
    python3 tools/one_off/qip2026_backfill_speakers.py [--html PATH] [--write]
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

LIVE_URL = "https://qip.iaqi.org/2026/programme/detailed-schedule/"
CSV_PATH = Path(__file__).resolve().parents[2] / "data/conferences/qip_2026/talks.csv"
TIME_RE = re.compile(r"^\s*\d{1,2}:\d{2}\s*[-–]\s*\d{1,2}:\d{2}")
MERGE_RE = re.compile(r"^\s*Merge:\s*", re.I)
BOLD_RE = re.compile(r"\*\*([^*]+?)\*\*")


def fetch_html(path):
    if path:
        return Path(path).read_text(encoding="utf-8")
    out = subprocess.run(["curl", "-sL", LIVE_URL], capture_output=True, text=True, check=True)
    return out.stdout


def extract_schedule(html):
    """Return the decoded schedule dict from the largest JSON.parse('…') blob."""
    best = None
    for m in re.finditer(r"JSON\.parse\(", html):
        start = m.end()
        q = html[start]
        if q not in "\"'":
            continue
        i, buf = start + 1, []
        while i < len(html):
            c = html[i]
            if c == "\\":
                buf.append(html[i : i + 2])
                i += 2
                continue
            if c == q:
                break
            buf.append(c)
            i += 1
        body = "".join(buf)
        try:  # rewrap the JS string literal as a JSON string, then decode
            inner = json.loads('"' + body.replace('"', r"\"") + '"')
            obj = json.loads(inner)
        except Exception:
            continue
        if "**" in inner and (best is None or len(inner) > best[0]):
            best = (len(inner), obj)
    if not best:
        sys.exit("ERROR: could not locate the schedule JSON.parse blob")
    return best[1]


def strip_bold(s):
    return BOLD_RE.sub(lambda m: m.group(1), s).strip()


def norm_title(s):
    s = strip_bold(s)
    s = re.sub(r"\[[^\]]*\]", " ", s)   # drop "[remote]" and similar annotations
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^a-z0-9]+", " ", s.lower())
    return " ".join(s.split())


# Spacing-diacritic characters that PDF extraction leaves stranded mid-name
# ("C¸atli", "Manˇcinska", "M¨obus"). Delete them so adjacent letters rejoin.
ARTIFACT_CHARS = "´¨ˇ¸˜ˆ`^"


def _fold(s):
    s = re.sub(r"\([^)]*\)", " ", s)            # drop "(Sunny)" style nicknames
    s = s.replace("ß", "ss")               # German ß → ss (not NFKD-decomposable)
    s = "".join(c for c in s if c not in ARTIFACT_CHARS)
    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if not unicodedata.combining(c)).lower()


def name_tokens(s):
    """Accent/artifact-folded, paren-stripped alnum tokens of a personal name."""
    return [t for t in re.sub(r"[^a-z0-9]+", " ", _fold(s)).split() if t]


def name_key(s):
    """Compact alnum-only key of a name (spaces/punct removed) for fuzzy equality."""
    return re.sub(r"[^a-z0-9]+", "", _fold(s))


def split_authors(cell):
    return [a.strip() for a in re.split(r"[;]", cell or "") if a.strip()]


def match_author(bold_name, authors):
    """Pick the author whose name best matches the schedule's bold presenter.

    Returns (author_string, shared_token_count, key_ok). A family-name (last-token)
    match or a compact-key containment is required to accept, so it survives
    nicknames, initials and mojibake. Callers treat a family-only match (shared < 2
    and not key_ok) as a name conflict rather than a spelling variant. Returns
    (None, 0, False) if no author plausibly matches.
    """
    bt = name_tokens(bold_name)
    if not bt:
        return None, 0, False
    bkey = name_key(bold_name)
    best, best_shared, best_keyok = None, -1, False
    for a in authors:
        at = name_tokens(a)
        if not at:
            continue
        shared = len(set(bt) & set(at))
        akey = name_key(a)
        # compact-key containment handles ß/mojibake that split a family token
        # ("Koßmann"→"kossmann", "C¸atli"→"catli"); family match is the weaker signal.
        key_ok = bkey in akey or akey in bkey
        family_ok = bt[-1] == at[-1] or key_ok
        if family_ok and (shared > best_shared or (shared == best_shared and key_ok)):
            best, best_shared, best_keyok = a, shared, key_ok
    if best is None:
        return None, 0, False
    return best, best_shared, best_keyok


def collect_lines(schedule):
    """Flatten all preview_texts into a single stream of parsed lines.

    Each entry: {"ntitle": normalized-title-candidate, "bolds": [names],
    "text": stripped}. We keep every non-empty line so titles can be anchored to
    ground-truth CSV titles and the presenter read from the following line(s).
    """
    lines = []
    for _date, blocks in schedule.items():
        if not isinstance(blocks, list):
            continue
        for b in blocks:
            en = (b.get("translations") or {}).get("en") or {}
            p = en.get("preview_text") or ""
            if "**" not in p:
                continue
            for raw in p.splitlines():
                core = MERGE_RE.sub("", TIME_RE.sub("", raw)).strip()
                if not core:
                    continue
                lines.append({"ntitle": norm_title(core),
                              "bolds": [x.strip() for x in BOLD_RE.findall(core)],
                              "text": strip_bold(core)})
            lines.append({"sep": True})  # session boundary
    return lines


def token_jaccard(a, b):
    sa, sb = set(a.split()), set(b.split())
    return len(sa & sb) / len(sa | sb) if (sa or sb) else 0.0


def title_match(csv_nt, sched_nt):
    """Conservative title equivalence (avoids short-substring false positives)."""
    if not csv_nt or not sched_nt:
        return False
    if csv_nt == sched_nt:
        return True
    short, long = sorted((csv_nt, sched_nt), key=len)
    sw = short.split()
    # extended title: the shorter is a prefix of the longer and is itself substantial
    if len(sw) >= 5 and long.startswith(short):
        return True
    # same, but compared with spaces removed (handles "General resource"/"Generalresource")
    cs, cl = short.replace(" ", ""), long.replace(" ", "")
    if len(cs) >= 30 and cl.startswith(cs):
        return True
    return token_jaccard(csv_nt, sched_nt) >= 0.75


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--html", help="path to a saved copy of the live schedule page")
    ap.add_argument("--write", action="store_true", help="write talks.csv (default: report only)")
    args = ap.parse_args()

    schedule = extract_schedule(fetch_html(args.html))
    lines = collect_lines(schedule)

    with CSV_PATH.open() as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames)
        rows = list(reader)

    # QIP CSVs historically used a singular `speaker` header, but the talks importer
    # only reads `speakers` (plural) — so presenters from a singular column never reach
    # presenter_author_id. Read from whichever exists and standardize the output to
    # `speakers` so the identified presenters actually import.
    spk_col = "speaker" if "speaker" in fieldnames else "speakers"
    for r in rows:
        r["speaker_val"] = (r.get(spk_col) or "").strip()

    csv_title_set = {norm_title(r["title"]) for r in rows}

    # Talks retitled between submission (talks.csv) and the live schedule, so the title
    # can't anchor. Presenter(s) read directly off the schedule author line (bolded).
    OVERRIDES = {
        # schedule: "Parallel Spooky Pebbling Makes Regev Factoring More Practical"
        norm_title("Parallel Spooky Pebble Games and Regev's Factoring Algorithm"):
            ["Gregory D. Kahanamoku-Meyer"],
        # schedule: "Sequential quantum processes with group symmetry and simulation of
        # random unitaries" — two bold presenters
        norm_title("Efficient implementation of sequential quantum processes with group symmetry"):
            ["Dmitry Grinko", "Satoshi Yoshida"],
    }

    def presenters_at(idx):
        """Bold presenter name(s) for the talk whose title anchors at line idx.

        Excludes bold names that are themselves talk titles; handles author line on
        the same line as the title, and titles that wrap across lines.
        """
        ln = lines[idx]
        same = [b for b in ln["bolds"] if norm_title(b) not in csv_title_set]
        if same:
            return same
        for j in range(idx + 1, min(idx + 7, len(lines))):
            l2 = lines[j]
            if l2.get("sep") or l2["ntitle"] in csv_title_set:
                break  # next talk / session boundary — do not leak across it
            if l2["bolds"]:
                return l2["bolds"]
        return []

    def find_presenters(row):
        """Anchor on the CSV title; return list of scheduled presenter names (raw)."""
        rt = norm_title(row["title"])
        if rt in OVERRIDES:
            return OVERRIDES[rt]
        best_i, best_j = None, 0.0
        for i, ln in enumerate(lines):
            if ln.get("sep"):
                continue
            if title_match(rt, ln["ntitle"]):
                j = 1.0 if rt == ln["ntitle"] else token_jaccard(rt, ln["ntitle"])
                if j > best_j:
                    best_j, best_i = j, i
        return presenters_at(best_i) if best_i is not None else []

    filled = corrected = unchanged = unmatched = flagged = 0
    real_changes, spelling_changes, flags, misses = [], [], [], []
    for r in rows:
        cur = r["speaker_val"]
        raws = find_presenters(r)
        if not raws:
            if not cur:
                unmatched += 1
                misses.append(r["title"])
            continue
        authors = split_authors(r["authors"])
        canon_names, bad = [], []
        for raw in raws:
            canon, shared, key_ok = match_author(raw, authors)
            # Accept the author spelling only on a confident match (given+family, or a
            # compact-key match through mojibake). A family-only match (e.g. schedule
            # "John Bostanci" vs author "Can Bostanci") is a name conflict, not a
            # spelling variant — flag it and keep the schedule name / current value.
            if canon is not None and (shared >= 2 or key_ok):
                if canon not in canon_names:
                    canon_names.append(canon)
            else:
                bad.append(raw)
        if bad:
            flagged += 1
            flags.append((r["title"], raws, authors))
            if not canon_names:
                continue
        new = "; ".join(canon_names)
        raw_disp = "; ".join(raws)
        if not cur:
            filled += 1
            real_changes.append(("FILL", r["title"], cur, new, raw_disp))
            r["speaker_val"] = new
        elif name_tokens(cur.replace(";", " ")) == name_tokens(new.replace(";", " ")):
            if cur != new:  # same person(s), cleaner spelling
                spelling_changes.append((r["title"], cur, new))
                r["speaker_val"] = new
            unchanged += 1
        else:
            corrected += 1
            real_changes.append(("FIX", r["title"], cur, new, raw_disp))
            r["speaker_val"] = new

    print("\n=== GENUINE presenter fills/changes ===")
    for kind, title, old, new, raw in real_changes:
        via = "" if raw == new else f"  (schedule: {raw!r})"
        print(f"[{kind}] {title[:58]!r}: {old!r} -> {new!r}{via}")
    print(f"\n=== spelling-only normalizations ({len(spelling_changes)}) ===")
    for title, old, new in spelling_changes:
        print(f"  {title[:58]!r}: {old!r} -> {new!r}")
    if flags:
        print(f"\n=== FLAGGED: some schedule presenter not among authors ({len(flags)}) ===")
        for title, sp, authors in flags:
            print(f"  {title[:55]!r}: schedule={sp} authors={authors}")
    if misses:
        print(f"\n=== still UNMATCHED blanks ({len(misses)}) ===")
        for t in misses:
            print(f"  {t}")
    print(f"\nSummary: fill={filled} fix={corrected} spelling={len(spelling_changes)} "
          f"unchanged={unchanged} unmatched-blank={unmatched} flagged={flagged}")

    if args.write:
        # Standardize the header to `speakers` (plural) so the talks importer reads it.
        out_fields = ["speakers" if c == spk_col else c for c in fieldnames]
        for r in rows:
            r["speakers"] = r["speaker_val"]
            r.pop("speaker_val", None)
            if spk_col != "speakers":
                r.pop(spk_col, None)
        with CSV_PATH.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=out_fields, extrasaction="ignore",
                               lineterminator="\n")  # match the repo's LF line endings
            w.writeheader()
            w.writerows(rows)
        renamed = "" if spk_col == "speakers" else f" (renamed column {spk_col!r} -> 'speakers')"
        print(f"\nWROTE {CSV_PATH}{renamed}")
    else:
        print("\n(report only; pass --write to update talks.csv)")


if __name__ == "__main__":
    main()
