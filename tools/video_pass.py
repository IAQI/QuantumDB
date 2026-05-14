#!/usr/bin/env python3
"""Video pass — correct the `speakers` column from YouTube video metadata.

Per conference, this tool:
  1. finds the conference's YouTube videos (via tools/video_channels.json, or
     by deriving the channel from `video_url` rows already in the CSV),
  2. fetches each video's title + description with `yt-dlp`,
  3. fuzzy-matches videos to talk rows by title,
  4. reads the real speaker out of the video title/description and — when it
     resolves to exactly one of the talk's listed authors — corrects the
     `speakers` column (also re-verifying rows that already had a video),
  5. (re)populates `video_url` / `youtube_id`, tags `notes` with provenance,
  6. prints a review report.

The script edits CSVs only. Dry-run by default; pass --write to apply. DB
re-import stays the separate `tools/scrapers/import_from_csv.py` step.

Usage:
    python tools/video_pass.py qip 2023            # dry run, one conference
    python tools/video_pass.py qip 2023 --write     # apply
    python tools/video_pass.py --all                # dry run, every conference
    python tools/video_pass.py --all --write --report /tmp/video_pass.txt
"""
import argparse
import csv
import hashlib
import json
import re
import subprocess
import sys
import time
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from scrapers._lib import normalize_name  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data" / "conferences"
REGISTRY_PATH = Path(__file__).resolve().parent / "video_channels.json"
CACHE_DIR = Path(__file__).resolve().parent / ".video_cache"

YT_DLP = "yt-dlp"
YT_EXTRACTOR_ARGS = "youtube:player_client=web_safari,android_creator,ios"

# Confident-match floor: rows at/above this get video_url + speaker edits.
DEFAULT_CONFIDENT = 0.62
# Weak-match band: reported only, nothing written.
DEFAULT_WEAK = 0.45

# Video titles that are clearly not single talks.
NON_TALK_RE = re.compile(
    r"\b(business meeting|rump session|poster session|opening|closing|"
    r"panel|welcome|day \d|session \d|keynote panel|q ?& ?a|townhall|"
    r"town hall|introduction|tutorial day)\b",
    re.IGNORECASE,
)

TITLE_STOPWORDS = {
    "a", "an", "the", "of", "for", "and", "on", "in", "to", "with", "from",
    "via", "is", "are", "be", "by", "as", "at", "or",
}
CONFERENCE_TAG_RE = re.compile(r"^(qip|qcrypt|tqc)\d{0,4}$", re.IGNORECASE)

# Strip a leading conference tag like "QIP2023 |", "TQC 2024 -", "[2024]",
# "Day 3:" from a video title before pattern matching.
TAG_PREFIX_RE = re.compile(
    r"^\s*(?:\[?\d{4}\]?|qip\s*\d{0,4}|qcrypt\s*\d{0,4}|tqc\s*\d{0,4}|"
    r"day\s*\d+)\s*[:\|\-–—]\s*",
    re.IGNORECASE,
)

# Title-shape patterns for SPEAKER EXTRACTION. Every `name` capture is only a
# *candidate* — it must pass looks_like_name() and then validate against the
# talk's author list. Dash/colon separators require surrounding spaces so a
# hyphen inside a word ("state-preparation", "Quantum Max-Cut") never triggers.
TITLE_PATTERNS = [
    re.compile(r"^\s*(?P<name>[^|:]{2,60}?)\s+[-–—]\s+(?P<rest>.+)$"),   # Speaker - Title
    re.compile(r"^\s*(?P<rest>.+?)\s+[-–—]\s+(?P<name>[^|:]{2,60}?)\s*$"),  # Title - Speaker
    re.compile(r"^\s*(?P<rest>.+?)\s*\|\s*(?P<name>[^|]{2,60}?)\s*$"),    # Title | Speaker
    re.compile(r"^\s*(?P<name>[^|]{2,60}?)\s*\|\s*(?P<rest>.+)$"),        # Speaker | Title
    re.compile(r"^\s*(?P<rest>.+?)\s*\((?P<name>[^()]{2,60}?)\)\s*$"),    # Title (Speaker)
    re.compile(r"^\s*(?P<name>[A-Z][^:]{1,58}?):\s+(?P<rest>.+)$"),       # Speaker: Title
]

# Lowercase name particles allowed mid-name ("van", "de", …).
NAME_PARTICLES = {
    "van", "von", "der", "den", "de", "del", "della", "di", "da", "dos",
    "du", "le", "la", "bin", "al", "ter", "ten",
}

# Description "Speaker:" line — the strongest signal.
DESC_SPEAKER_RE = re.compile(
    r"(?:speaker|presented by|presenter|talk by|speaker is)\s*[:\-]?\s*"
    r"([^\n,;|]{2,60})",
    re.IGNORECASE,
)


# ─── yt-dlp helpers ─────────────────────────────────────────────────────────

def _run_yt_dlp(args):
    """Run yt-dlp with the anti-bot extractor args; return parsed JSON lines."""
    cmd = [YT_DLP, "--extractor-args", YT_EXTRACTOR_ARGS, *args]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip().splitlines()[-1] if proc.stderr else "yt-dlp failed")
    return proc.stdout


def fetch_playlist(source_url, refresh=False):
    """Stage A: flat-enumerate a playlist/channel. Returns [{id, title}, ...]."""
    CACHE_DIR.mkdir(exist_ok=True)
    key = hashlib.sha1(source_url.encode()).hexdigest()[:16]
    cache = CACHE_DIR / f"playlist_{key}.json"
    if cache.exists() and not refresh:
        data = json.loads(cache.read_text())
    else:
        out = _run_yt_dlp(["--flat-playlist", "--dump-single-json", source_url])
        data = json.loads(out)
        cache.write_text(json.dumps(data))
    entries = data.get("entries") or []
    result = []
    for e in entries:
        if not e or not e.get("id"):
            continue
        result.append({"id": e["id"], "title": e.get("title") or ""})
    return result


def fetch_video(video_id, refresh=False, sleep=1.5):
    """Stage B: full per-video metadata. Returns dict or None on failure."""
    CACHE_DIR.mkdir(exist_ok=True)
    cache = CACHE_DIR / f"video_{video_id}.json"
    if cache.exists() and not refresh:
        return json.loads(cache.read_text())
    try:
        out = _run_yt_dlp([
            "--skip-download", "--dump-json",
            f"https://www.youtube.com/watch?v={video_id}",
        ])
        data = json.loads(out)
        slim = {
            "id": data.get("id", video_id),
            "title": data.get("title") or "",
            "description": data.get("description") or "",
            "channel_id": data.get("channel_id") or "",
            "channel_url": data.get("channel_url") or "",
            "upload_date": data.get("upload_date") or "",
            "playlist_id": data.get("playlist_id") or "",
        }
        cache.write_text(json.dumps(slim))
        time.sleep(sleep)
        return slim
    except Exception as exc:  # noqa: BLE001 — isolate per-video failures
        print(f"    ! fetch failed for {video_id}: {exc}", file=sys.stderr)
        return None


# ─── registry + discovery ───────────────────────────────────────────────────

def load_registry():
    return json.loads(REGISTRY_PATH.read_text())


YT_ID_RE = re.compile(
    r"(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/)([A-Za-z0-9_-]{11})"
)


def extract_youtube_id(url):
    if not url:
        return None
    m = YT_ID_RE.search(url)
    return m.group(1) if m else None


def discover_sources_from_csv(rows, refresh, sleep):
    """Fallback: derive a channel/playlist from existing video_url rows."""
    ids = []
    for r in rows:
        vid = (r.get("youtube_id") or "").strip() or extract_youtube_id(r.get("video_url", ""))
        if vid:
            ids.append(vid)
    if not ids:
        return []
    from collections import Counter
    channels, playlists = Counter(), Counter()
    for vid in ids[:5]:
        meta = fetch_video(vid, refresh=refresh, sleep=sleep)
        if not meta:
            continue
        if meta.get("channel_url"):
            channels[meta["channel_url"]] += 1
        if meta.get("playlist_id"):
            playlists[f"https://www.youtube.com/playlist?list={meta['playlist_id']}"] += 1
    if playlists:
        return [playlists.most_common(1)[0][0]]
    if channels:
        ch = channels.most_common(1)[0][0].rstrip("/")
        return [f"{ch}/videos"]
    return []


# ─── matching ───────────────────────────────────────────────────────────────

def title_tokens(s):
    s = normalize_name(s)  # diacritic-fold + lowercase (also drops 1-letter tokens)
    toks = re.findall(r"[a-z0-9]+", s)
    return {
        t for t in toks
        if t not in TITLE_STOPWORDS
        and not CONFERENCE_TAG_RE.match(t)
        and not re.fullmatch(r"\d{4}", t)
        and len(t) > 1
    }


def strip_tag_prefix(title):
    prev = None
    while prev != title:
        prev = title
        title = TAG_PREFIX_RE.sub("", title).strip()
    return title


def title_score(csv_title, video_title):
    """Jaccard over title tokens. Uses the FULL video title — title_tokens
    already drops conference-tag tokens + years, so a trailing speaker name
    only adds a couple of noise tokens to the union rather than corrupting
    the comparison (an earlier 'strip the Speaker - wrapper' approach broke
    on hyphenated title words)."""
    a = title_tokens(csv_title)
    b = title_tokens(video_title)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def looks_like_name(s, min_words=2):
    """True if `s` is plausibly a person name: `min_words`-5 words, each
    starting uppercase (or a known lowercase particle), no digits."""
    s = s.strip().strip("([)]")
    if not s or any(ch.isdigit() for ch in s):
        return False
    words = s.split()
    if not (min_words <= len(words) <= 5):
        return False
    for w in words:
        wc = w.strip("([)].,")
        if not wc:
            return False
        if wc[0].isupper() or wc.lower() in NAME_PARTICLES:
            continue
        return False
    return True


def clean_candidate(s):
    """Normalise an extracted speaker candidate: split a glued initial
    ('R.Kothari' -> 'R. Kothari'), trim surrounding punctuation/quotes."""
    s = s.strip().strip("\"'“”").strip()
    s = re.sub(r"\b([A-Z])\.([A-Z][a-z])", r"\1. \2", s)  # R.Kothari -> R. Kothari
    return s.strip()


def split_multi(name):
    """Split a candidate naming several people on +, &, ' and ', or commas."""
    parts = re.split(r"\s*(?:\+|&|/|,|\band\b)\s*", name)
    return [p.strip() for p in parts if p.strip()]


def author_overlap(authors, video_text):
    """How many of `authors` have their family name appear as a token in the
    video title+description. Word-boundary tokenized so glued punctuation
    ("(Stacey Jeffery)" -> "jeffery") doesn't hide a match."""
    vt_tokens = set(re.findall(r"[a-z0-9]+", normalize_name(video_text)))
    n = 0
    for au in authors:
        fam = normalize_name(au).split()
        if fam and fam[-1] in vt_tokens:
            n += 1
    return n


def match_videos_to_talks(rows, videos, confident, weak):
    """Greedy global best-first. Returns dict row_index -> (video, score)."""
    pairs = []
    for ri, r in enumerate(rows):
        ctitle = r.get("title", "")
        authors = [a.strip() for a in (r.get("authors") or "").split(";") if a.strip()]
        for vi, v in enumerate(videos):
            if NON_TALK_RE.search(v["title"]):
                continue
            ts = title_score(ctitle, v["title"])
            if ts < weak:
                continue
            vtext = v["title"] + " " + v.get("description", "")
            ao = author_overlap(authors, vtext)
            score = ts + 0.15 * min(ao, 2)
            pairs.append((score, ts, ao, ri, vi))
    pairs.sort(reverse=True)
    used_rows, used_vids, assigned = set(), set(), {}
    for score, ts, ao, ri, vi in pairs:
        if ri in used_rows or vi in used_vids:
            continue
        used_rows.add(ri)
        used_vids.add(vi)
        # ts (pure title Jaccard, 0-1) is what gets written as yt_match;
        # `score` (with author-overlap bonus) is only the ranking key.
        assigned[ri] = (videos[vi], ts, score >= confident)
    return assigned, used_vids


# ─── speaker extraction ─────────────────────────────────────────────────────

def speaker_candidates(video):
    """Ordered list of (candidate_name, source) — description first (the
    strongest signal), then title-shape patterns. Multi-name chunks are
    split; each candidate is cleaned and must look like a person name."""
    raw = []
    desc = video.get("description", "")
    if desc:
        m = DESC_SPEAKER_RE.search(desc[:500])
        if m:
            raw.append((m.group(1), "video_desc"))
    core = strip_tag_prefix(video.get("title", ""))
    for pat in TITLE_PATTERNS:
        m = pat.match(core)
        if m and m.groupdict().get("name"):
            raw.append((m.group("name"), "video_title"))

    seen, out = set(), []
    for chunk, src in raw:
        # description "Speaker:" lines may legitimately give just a surname
        min_words = 1 if src == "video_desc" else 2
        for piece in split_multi(chunk):
            cand = clean_candidate(piece)
            if not looks_like_name(cand, min_words=min_words):
                continue
            key = normalize_name(cand)
            if key and key not in seen:
                seen.add(key)
                out.append((cand, src))
    return out


def match_candidate_to_author(candidate, authors):
    """Return (matched_author_as_in_csv, confidence).

    confidence in {'exact', 'family_only', 'ambiguous', 'none'}.
    """
    nc = normalize_name(candidate)
    if not nc:
        return None, "none"
    norm = {}
    for a in authors:
        norm.setdefault(normalize_name(a), a)
    # exact
    if nc in norm:
        return norm[nc], "exact"
    nc_toks = nc.split()
    # multi-word subset either direction
    subset_hits = []
    for na, orig in norm.items():
        na_toks = na.split()
        if nc_toks and (set(nc_toks) <= set(na_toks) or set(na_toks) <= set(nc_toks)):
            subset_hits.append(orig)
    if len(subset_hits) == 1:
        return subset_hits[0], "family_only"
    if len(subset_hits) > 1:
        return None, "ambiguous"
    # family-name-only: candidate is a single token, or match on last token
    cand_fam = nc_toks[-1] if nc_toks else nc
    fam_hits = [orig for na, orig in norm.items() if na.split() and na.split()[-1] == cand_fam]
    if len(fam_hits) == 1:
        return fam_hits[0], "family_only"
    if len(fam_hits) > 1:
        return None, "ambiguous"
    return None, "none"


# ─── notes tokens ───────────────────────────────────────────────────────────

# keys this script owns; replaced rather than duplicated
OWNED_NOTE_KEYS = ("yt_match", "speaker_source", "speaker_verified", "video_pass")


def update_notes(existing, updates):
    """Merge `updates` (dict key->value) into a '; '-separated notes string,
    replacing tokens whose key this script owns, preserving everything else."""
    tokens = [t.strip() for t in (existing or "").split(";") if t.strip()]
    kept = []
    for t in tokens:
        key = t.split("=", 1)[0].strip() if "=" in t else None
        if key in OWNED_NOTE_KEYS and key in updates:
            continue  # drop; will be re-added from updates
        kept.append(t)
    for k, v in updates.items():
        kept.append(f"{k}={v}")
    return "; ".join(kept)


# ─── per-CSV processing ─────────────────────────────────────────────────────

def process_csv(csv_path, sources, confident, weak, refresh, sleep, write):
    with open(csv_path, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)
    if not rows or "speakers" not in fieldnames:
        return None

    # enumerate + fetch videos
    seen_ids, videos = set(), []
    for src in sources:
        try:
            entries = fetch_playlist(src, refresh=refresh)
        except Exception as exc:  # noqa: BLE001
            print(f"    ! playlist fetch failed for {src}: {exc}", file=sys.stderr)
            continue
        for e in entries:
            if e["id"] in seen_ids:
                continue
            seen_ids.add(e["id"])
            meta = fetch_video(e["id"], refresh=refresh, sleep=sleep)
            videos.append(meta or {"id": e["id"], "title": e["title"], "description": ""})

    assigned, used_vids = match_videos_to_talks(rows, videos, confident, weak)

    report = {
        "csv": csv_path, "n_videos": len(videos), "n_rows": len(rows),
        "corrections": [], "verified": [], "ambiguous": [],
        "speaker_not_in_authors": [], "no_speaker": [], "multi_speaker": [],
        "weak": [], "videos_no_talk": [], "talks_no_video": [], "non_talk": [],
    }
    today = date.today().isoformat()

    for ri, row in enumerate(rows):
        match = assigned.get(ri)
        if not match:
            pt = row.get("paper_type", "")
            report["talks_no_video"].append((f"[{pt}] " if pt else "") + row.get("title", ""))
            continue
        video, ts, confident_hit = match
        if not confident_hit:
            report["weak"].append((row.get("title", ""), video["title"], round(ts, 2)))
            continue

        authors = [a.strip() for a in (row.get("authors") or "").split(";") if a.strip()]
        cur_speakers = (row.get("speakers") or "").strip()
        updates = {"yt_match": f"{ts:.2f}", "video_pass": today}
        new_video_url = f"https://www.youtube.com/watch?v={video['id']}"

        # resolve a speaker
        resolved, conf, src = None, "none", None
        for cand, csrc in speaker_candidates(video):
            r_name, r_conf = match_candidate_to_author(cand, authors)
            if r_conf in ("exact", "family_only"):
                resolved, conf, src = r_name, r_conf, csrc
                break
            if r_conf == "ambiguous" and conf == "none":
                conf = "ambiguous"
        # raw candidate that matched nothing — surface it
        raw_cands = [c for c, _ in speaker_candidates(video)]

        if resolved:
            if ";" in cur_speakers:
                report["multi_speaker"].append((row.get("title", ""), cur_speakers, resolved))
            elif normalize_name(resolved) == normalize_name(cur_speakers):
                updates["speaker_verified"] = "video"
                report["verified"].append((row.get("title", ""), resolved))
            else:
                updates["speaker_source"] = src
                report["corrections"].append(
                    (row.get("title", ""), cur_speakers, resolved, src, conf, round(ts, 2))
                )
                row["speakers"] = resolved
        elif conf == "ambiguous":
            report["ambiguous"].append((row.get("title", ""), raw_cands))
        elif raw_cands:
            report["speaker_not_in_authors"].append((row.get("title", ""), raw_cands, authors))
        else:
            report["no_speaker"].append((row.get("title", ""), video["title"]))

        # always (re)populate the video link on a confident match
        row["video_url"] = new_video_url
        row["youtube_id"] = video["id"]
        row["notes"] = update_notes(row.get("notes", ""), updates)

    # videos that matched no talk (and weren't non-talk)
    for vi, v in enumerate(videos):
        if vi in used_vids:
            continue
        if NON_TALK_RE.search(v["title"]):
            report["non_talk"].append(v["title"])
        else:
            report["videos_no_talk"].append(v["title"])

    if write:
        with open(csv_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)

    return report


# ─── reporting ──────────────────────────────────────────────────────────────

def print_report(rep, out):
    def w(line=""):
        print(line, file=out)
    rel = rep["csv"].relative_to(REPO_ROOT)
    w(f"\n=== VIDEO PASS: {rel} ===")
    w(f"Videos enumerated: {rep['n_videos']}   |   Rows in CSV: {rep['n_rows']}")

    def section(label, items, fmt):
        if not items:
            return
        w(f"\n{label} — {len(items)}")
        for it in items:
            w("  " + fmt(it))

    section("CORRECTIONS (speakers changed)", rep["corrections"],
            lambda it: f"{it[0][:70]!r}\n      {it[1]!r} -> {it[2]!r}  ({it[3]}, {it[4]}, yt_match={it[5]})")
    section("VERIFIED (speakers confirmed unchanged)", rep["verified"],
            lambda it: f"{it[1]:30}  {it[0][:60]}")
    section("AMBIGUOUS (video names a surname shared by 2+ authors)", rep["ambiguous"],
            lambda it: f"{it[0][:60]}  candidates={it[1]}")
    section("SPEAKER-NOT-IN-AUTHORS (video names someone not in author list)", rep["speaker_not_in_authors"],
            lambda it: f"{it[0][:55]}  video_says={it[1]}  authors={it[2]}")
    section("NO SPEAKER FOUND in video metadata", rep["no_speaker"],
            lambda it: f"{it[0][:55]}  <- video {it[1][:50]!r}")
    section("MULTI-SPEAKER (kept; video named one of several)", rep["multi_speaker"],
            lambda it: f"{it[0][:55]}  kept={it[1]!r}  video_said={it[2]!r}")
    section("WEAK MATCHES (0.45-0.62, nothing written)", rep["weak"],
            lambda it: f"{it[0][:50]!r}  ~  {it[1][:50]!r}  ({it[2]})")
    section("NON-TALK VIDEOS skipped", rep["non_talk"], lambda it: it[:75])
    section("VIDEOS WITH NO MATCHING TALK", rep["videos_no_talk"], lambda it: it[:75])
    section("TALKS WITH NO MATCHING VIDEO", rep["talks_no_video"], lambda it: it[:75])

    w(f"\nSUMMARY: {len(rep['corrections'])} corrections, "
      f"{len(rep['verified'])} verified, {len(rep['ambiguous'])} ambiguous, "
      f"{len(rep['speaker_not_in_authors'])} speaker-not-in-authors, "
      f"{len(rep['weak'])} weak, {len(rep['videos_no_talk'])} unmatched videos, "
      f"{len(rep['talks_no_video'])} talks without video.")


# ─── conference resolution ──────────────────────────────────────────────────

def resolve_conf_dir(venue, year):
    """Case-insensitive lookup of data/conferences/<venue>_<year>."""
    target = f"{venue.lower()}_{year}"
    for d in DATA_DIR.iterdir():
        if d.is_dir() and d.name.lower() == target:
            return d
    return None


def conference_csvs(conf_dir):
    return [p for name in ("talks.csv", "proceedings.csv", "workshop.csv")
            if (p := conf_dir / name).exists()]


def run_one(venue, year, registry, args, out):
    conf_dir = resolve_conf_dir(venue, year)
    if not conf_dir:
        print(f"  no data dir for {venue} {year}", file=out)
        return
    csvs = conference_csvs(conf_dir)
    if not csvs:
        print(f"  no talk CSVs in {conf_dir.name}", file=out)
        return

    key = f"{venue.lower()}_{year}"
    entry = registry.get(key)
    sources = entry["sources"] if entry else []
    if not sources:
        # fallback: derive from existing video_url rows in the first CSV
        with open(csvs[0], encoding="utf-8", newline="") as f:
            first_rows = list(csv.DictReader(f))
        sources = discover_sources_from_csv(first_rows, args.refresh_cache, args.sleep)
        if sources:
            print(f"  {venue} {year}: no registry entry — discovered {sources} "
                  f"(consider adding to video_channels.json)", file=out)
        else:
            print(f"  {venue} {year}: no channel known and no existing videos — skipped", file=out)
            return

    for csv_path in csvs:
        rep = process_csv(csv_path, sources, args.confident, args.weak,
                          args.refresh_cache, args.sleep, args.write)
        if rep:
            print_report(rep, out)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("venue", nargs="?", help="QIP / QCRYPT / TQC")
    ap.add_argument("year", nargs="?", type=int)
    ap.add_argument("--all", action="store_true",
                    help="process every conference dir with a known/derivable channel")
    ap.add_argument("--write", "--commit", dest="write", action="store_true",
                    help="apply changes to the CSV(s) (default: dry run)")
    ap.add_argument("--report", type=Path, help="also write the report to this file")
    ap.add_argument("--refresh-cache", action="store_true",
                    help="ignore the yt-dlp metadata cache and refetch")
    ap.add_argument("--sleep", type=float, default=1.5,
                    help="seconds between per-video yt-dlp calls (default 1.5)")
    ap.add_argument("--confident", type=float, default=DEFAULT_CONFIDENT,
                    help=f"confident-match score floor (default {DEFAULT_CONFIDENT})")
    ap.add_argument("--weak", type=float, default=DEFAULT_WEAK,
                    help=f"weak-match score floor (default {DEFAULT_WEAK})")
    args = ap.parse_args()

    if not args.all and (not args.venue or not args.year):
        ap.error("give <venue> <year>, or --all")

    registry = load_registry()
    out_files = [sys.stdout]
    report_fh = None
    if args.report:
        report_fh = open(args.report, "w", encoding="utf-8")
        out_files.append(report_fh)

    class Tee:
        def write(self, s):
            for fh in out_files:
                fh.write(s)
        def flush(self):
            for fh in out_files:
                fh.flush()
    out = Tee()

    mode = "WRITE" if args.write else "DRY RUN"
    print(f"# video_pass — {mode}", file=out)

    try:
        if args.all:
            confs = []
            for d in sorted(DATA_DIR.iterdir()):
                if not d.is_dir():
                    continue
                m = re.match(r"([a-zA-Z]+)_(\d{4})$", d.name)
                if m:
                    confs.append((m.group(1).upper(), int(m.group(2))))
            for venue, year in confs:
                run_one(venue, year, registry, args, out)
        else:
            run_one(args.venue.upper(), args.year, registry, args, out)
    finally:
        if report_fh:
            report_fh.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
