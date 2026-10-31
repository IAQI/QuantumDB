#!/usr/bin/env python3
"""Link QIP 2026 talks to their YouTube recordings and verify speakers.

The QIP 2026 recordings are on the "QIP conference videos" channel
(@QIPconferencevideos; 11 "QIP2026: <TOPIC>" playlists). Every video description is
structured, one block per talk:

    TITLE: <paper title>
    SPEAKER: <name>
    AUTHORS: <a>, <b>, ...

and merged-slot videos (two papers in one 30-min slot) carry a second block prefixed with
its start offset (``14:29 TITLE: ...``). That makes the description a better join key than
the fuzzy title matching in tools/video_pass.py, so this script:

1. reads the per-video metadata cached by ``tools/video_pass.py qip 2026``
   (``tools/.video_cache/video_<id>.json``; run that first, dry run is enough),
2. parses each description into (title, speaker, offset) blocks,
3. matches each block to a ``talks.csv`` row by normalized title,
4. sets ``video_url`` (with ``&t=<s>s`` for a block that starts mid-video) and
   ``youtube_id``; verifies ``speakers`` against SPEAKER and corrects it only when the
   SPEAKER is one of the row's authors (anything else is reported, not applied),
5. appends rows that talks.csv lacks: the 4 tutorials (``raw/tutorials.csv``) and the
   2 invited plenaries (from their video descriptions).

Dry run by default; ``--write`` to apply.
"""
import argparse
import csv
import difflib
import glob
import json
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CONF = ROOT / "data" / "conferences" / "qip_2026"
CACHE = ROOT / "tools" / ".video_cache"
sys.path.insert(0, str(ROOT / "tools"))
from video_pass import update_notes  # noqa: E402

QIP_CHANNEL_ID = "UCiPxtMzEnPyXBxYmkmWcrLg"  # @QIPconferencevideos
OWN_KEYS = ("video_source", "speaker_verified", "speaker_source", "video_offset")


def fold(s):
    s = re.sub(r"\([^)]*\)", " ", s or "")  # drop nicknames: "Zhiyang (Sunny) He"
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    s = s.replace("\\&", "&").replace("\\\\", " ")
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def to_seconds(ts):
    parts = [int(p) for p in ts.split(":")]
    secs = 0
    for p in parts:
        secs = secs * 60 + p
    return secs


BLOCK_RE = re.compile(
    r"(?:^|\n)[ \t]*(?:(?P<ts>\d{1,2}(?::\d{2}){1,2})[ \t]+)?TITLE:[ \t]*(?P<title>[^\n]*)\n"
    r"(?P<rest>(?:[ \t]*(?:SPEAKER|AUTHORS?|Merge)[^\n]*\n?)*)",
)
# Title variants between the video description and the accepted-papers list.
ALIASES = {
    "parallel spooky pebbling makes regev factoring more practical":
        "Parallel Spooky Pebble Games and Regev's Factoring Algorithm",
    "sequential quantum processes with group symmetry and simulation of random unitaries":
        "Efficient implementation of sequential quantum processes with group symmetry",
}


def parse_blocks(video):
    """-> [dict(title, speaker or None, offset)] for one video."""
    out = []
    for m in BLOCK_RE.finditer(video["description"]):
        title, rest = m.group("title").strip(), m.group("rest") or ""
        offset = to_seconds(m.group("ts")) if m.group("ts") else 0
        sp = re.search(r"SPEAKER:[ \t]*([^\n]+)", rest)
        merge = re.search(r"Merge:\s*(.+)", rest) if not title else None
        if merge:  # "Merge: <title>: <authors> | <title>: <authors>" — no speakers given
            for seg in merge.group(1).split(" | "):
                out.append(dict(title=seg.rsplit(":", 1)[0].strip(), speaker=None, offset=0))
            continue
        if not title:  # empty TITLE: fall back to "<Speaker>: <title>" from the video title
            title = video["title"].split(":", 1)[-1].strip()
        title = re.sub(r"^Merge:\s*", "", title)
        out.append(dict(title=title, speaker=(sp.group(1).strip() or None) if sp else None, offset=offset))
    return out


def load_videos():
    """QIP 2026 videos from the video_pass cache (uploaded Oct 2026 on the QIP channel)."""
    vids = []
    for f in glob.glob(str(CACHE / "video_*.json")):
        v = json.loads(Path(f).read_text())
        if v.get("upload_date", "") < "20261001":
            continue
        if v.get("channel_id") != QIP_CHANNEL_ID:
            continue
        vids.append(v)
    return vids


def best_row(title, rows):
    ft = fold(ALIASES.get(fold(title), title))
    for i, r in enumerate(rows):  # one title contained in the other (subtitle variants)
        fr = fold(r["title"])
        if len(ft) > 25 and (ft in fr or fr in ft):
            return i, 1.0
    scored = [(difflib.SequenceMatcher(None, ft, fold(r["title"])).ratio(), i)
              for i, r in enumerate(rows)]
    score, i = max(scored)
    return (i, score) if score >= 0.85 else (None, score)


def yt_url(vid, offset):
    return f"https://www.youtube.com/watch?v={vid}" + (f"&t={offset}s" if offset else "")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    path = CONF / "talks.csv"
    with open(path, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        fields, rows = reader.fieldnames, list(reader)

    videos = load_videos()
    print(f"{len(videos)} QIP 2026 videos in cache")

    # ── extra rows: tutorials + invited plenaries ───────────────────────────
    have = {fold(r["title"]) for r in rows}
    extra = []
    with open(CONF / "raw" / "tutorials.csv", encoding="utf-8", newline="") as f:
        for t in csv.DictReader(f):
            if fold(t["title"]) in have:
                continue
            r = {k: t.get(k, "") for k in fields}
            r["speakers"] = t.get("speaker", "")
            r["notes"] = "source_type=qip_website; tutorial (raw/tutorials.csv)"
            extra.append(r)
    tutorial_video = {}  # tutorial title -> video id ("TUTORIAL: <title>" line)
    for v in videos:
        m = re.search(r"TUTOR[I1l]AL:\s*(.+)", v["description"])
        if m:
            tutorial_video[fold(m.group(1))] = v["id"]
    for v in videos:
        if not v["title"].upper().startswith("INVITED TALK"):
            continue
        d = v["description"]
        title = re.search(r"TITLE:\s*(.+)", d).group(1).strip()
        speaker = re.search(r"SPEAKER:\s*(.+)", d).group(1).strip()
        date = re.search(r"DATE:\s*\w+, (\w+) (\d+), 2026", d)
        time_ = re.search(r"TIME:\s*(\d{2}:\d{2})[–-](\d{2}:\d{2})", d)
        if fold(title) in have:
            continue
        r = {k: "" for k in fields}
        r.update(venue="QIP", year="2026", paper_type="invited", title=title,
                 authors=speaker, speakers=speaker, session_name="Invited plenary",
                 notes="source_type=youtube_description; invited plenary")
        if date:
            r["scheduled_date"] = f"{int(date.group(2))} {date.group(1)}"
        if time_:
            r["scheduled_time"] = time_.group(1)
            h1, m1 = map(int, time_.group(1).split(":"))
            h2, m2 = map(int, time_.group(2).split(":"))
            r["duration_minutes"] = str((h2 * 60 + m2) - (h1 * 60 + m1))
        extra.append(r)
    rows.extend(extra)
    for r in extra:
        print(f"  ADD ROW  [{r['paper_type']}] {r['title'][:60]} — {r['speakers']}")

    # ── tutorial videos ─────────────────────────────────────────────────────
    for r in rows:
        if r["paper_type"] == "tutorial" and fold(r["title"]) in tutorial_video:
            vid = tutorial_video[fold(r["title"])]
            r["video_url"], r["youtube_id"] = yt_url(vid, 0), vid
            r["notes"] = update_notes(r["notes"], {"video_source": "yt_description"})

    # ── talk blocks ─────────────────────────────────────────────────────────
    linked, verified, corrected, not_author, no_row = 0, 0, [], [], []
    hit_rows = set()
    for v in sorted(videos, key=lambda v: v["id"]):
        for b in parse_blocks(v):
            i, score = best_row(b["title"], rows)
            if i is None:
                no_row.append((v["id"], b["title"], round(score, 2)))
                continue
            r = rows[i]
            hit_rows.add(i)
            r["notes"] = "; ".join(t for t in r["notes"].split("; ")
                                   if t.split("=", 1)[0] not in OWN_KEYS)
            r["video_url"], r["youtube_id"] = yt_url(v["id"], b["offset"]), v["id"]
            linked += 1
            upd = {"video_source": "yt_description"}
            if b["offset"]:
                upd["video_offset"] = f"{b['offset']}s (merged-slot video)"
            authors = [a.strip() for a in r["authors"].split(";") if a.strip()]
            sp = b["speaker"]
            cur = r["speakers"].strip()
            match = next((a for a in authors if fold(a) == fold(sp)), None)
            if sp is None:
                pass  # block names no speaker; keep the row's
            elif fold(sp) in {fold(c) for c in cur.split(";")}:  # also keeps co-presenters
                upd["speaker_verified"] = "video"
                verified += 1
            elif match:
                corrected.append((r["title"], cur, match))
                r["speakers"] = match
                upd["speaker_source"] = "video_description"
            else:
                not_author.append((r["title"], cur, sp, authors))
            r["notes"] = update_notes(r["notes"], upd)

    print(f"\n{linked} talk blocks linked, {verified} speakers verified, "
          f"{len(corrected)} corrected, {len(not_author)} SPEAKER not among authors")
    for t, old, new in corrected:
        print(f"  CORRECT  {t[:60]}: {old!r} -> {new!r}")
    for t, cur, sp, authors in not_author:
        print(f"  NOT-AUTHOR {t[:60]}: video says {sp!r}, row speaker {cur!r}, authors {authors}")
    for vid, t, s in no_row:
        print(f"  NO ROW   {vid} {t[:70]} (best {s})")
    missing = [r for i, r in enumerate(rows) if not r["video_url"]]
    print(f"\nrows without video: {len(missing)}")
    for r in missing:
        print(f"  - [{r['paper_type']}] {r['title'][:80]}")

    if args.write:
        with open(path, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows(rows)
        print(f"wrote {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
