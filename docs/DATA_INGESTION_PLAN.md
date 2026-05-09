# Conference data ingestion plan

_Last updated: 2026-05-09 (Phase 1 progress: QIP 2008/2009/2014/2016/2017/2018/2019/2023/2026 done; QIP 2020/2022 deferred. TQC 2008-2017/2019-2025 done (2008-2010 partial); TQC 2006/2007/2018 unrecoverable from local archive. QCrypt 2025 seeded.)._

## Phase 0 status: completed (2026-05-08)

The three "anomalies" flagged for Phase 0 were investigated:

- **QIP 2004 talks.csv (471 rows)** — not an anomaly. The CSV parses to
  34 rows when read with the `csv` module; the 471 was a `wc -l` artifact
  from multiline-quoted abstracts. Inventory table miscounted.
- **QCrypt 2017 talks.csv (203 rows, only 43 with schedule)** — not an
  anomaly. 203 rows is real and correct: 4 tutorials + 8 invited + 32
  regular + 159 posters. All 203 have schedule data; the "43" figure
  was wrong.
- **TQC 2023/2024 workshop.csv missing** — fixed. Output of
  `tools/one_off/tqc2023-24/convert_tqc_to_csv.py` was sitting in
  `data/conferences/tqc_{2023,2024}/raw/talks_with_schedule.csv` but
  never promoted. Now written as proper `workshop.csv` files (59 rows
  for 2023; 92 rows for 2024). Both have full schedule + speaker
  coverage and near-complete abstracts. `SOURCES.md` updated.

Lesson for future audits: always parse CSVs with the `csv` module, not
`wc -l`, for accurate row counts.

## Context

QuantumDB tracks committees and talks for QIP (1998–), QCrypt (2011–), and
TQC (2013–). This document is the working plan for filling out the data,
covering:

1. Inventory of which conferences are complete vs partial vs missing for
   committees, talks, schedule data, and video links (per the audit run
   on 2026-05-08).
2. Per-gap method recommendation. Three options on the table:
   - **Python scraper** (existing per-venue parsers under `tools/scrapers/`)
   - **Claude direct extraction** (Claude reads local HTML/PDF and writes
     CSV directly, with a verification protocol to prevent hallucination)
   - **Defer / not feasible** (no usable source)
3. Source-tracking convention so DB rows carry which method produced
   them (re-runnable scraper vs one-shot AI extraction).
4. Deferred future track: YouTube playlist mining for `video_url`,
   `youtube_id`, and `presenter_author_id` inference.

## Tipping-point heuristic (scraper vs claude-direct)

Use a **Python scraper** when at least 2 of these hold:

- The same parser will work for ≥3 years/venues
- ≥50 records on the page
- Clean, regular HTML (lists/tables, predictable tags)
- Recurring conference (still happening; will be re-run)

Otherwise use **Claude direct extraction**, with this guardrail:

- Always work from a saved local file (no live URLs)
- Pin a verifiable count up front ("page lists N talks → CSV must have N")
- Demand a structural pass first (headings + counts before extraction)
- Spot-check 3 random rows by line number against the source
- Cross-reference one external source where possible (DBLP, arXiv)
- Never infer fields — leave blank if not on the page
- Record source path in the CSV's `metadata.source_url` and the commit msg

## Source-tracking convention

When a CSV is produced by a deterministic Python parser vs. by Claude
reading the source directly, that distinction needs to survive into the
database so future auditors can tell which rows belong to which trust
class. Mechanism (uses existing schema, no migration needed):

### Layer 1: row metadata (`metadata.source_type` JSONB on `authorships` / `committee_roles`)

Distinct values:

| Value | Meaning |
|-------|---------|
| `"scraper"` | Produced by `tools/scrapers/{committees,talks}/<venue>.py`. Re-runnable from the same input. |
| `"claude_extraction"` | Claude read the local archive (HTML/PDF/text) and emitted the row directly. One-shot; verification trail required. |
| `"conference_website"` | Existing legacy value used by the talks importer for all rows. Will be retained for already-imported data; new imports use `"scraper"` or `"claude_extraction"`. |
| `"dblp"` / `"arxiv"` / `"manual_entry"` / `"orcid"` | Existing values, unchanged. |

Sample populated metadata for a Claude-extracted row:

```json
{
  "source_type": "claude_extraction",
  "source_url": "file:///Users/chris/Web/qip.iaqi.org/2018/programs/program.pdf",
  "scraped_date": "2026-05-08",
  "notes": "extracted from PDF via Claude; verification: 47 rows match published count"
}
```

### Layer 2: CSV schema

Add **one optional column** to both `talks.csv` and `committees.csv`:

- `source_type` — if present and non-empty, the importer copies it into
  `metadata.source_type`. If absent or blank, defaults to `"scraper"`
  (matches current de-facto behavior for everything imported via the
  Python pipeline).

No new columns for `source_url` / `extraction_date` etc. — those go
into JSONB metadata at import time, populated either from the CSV's
`notes` field or from importer defaults (already the case).

### Layer 3: `data/SOURCES.md`

One line per conference/track noting the method, e.g.

```
- QIP 2018 talks: claude_extraction from PDFs at ~/Web/qip.iaqi.org/2018/programs/
- QIP 2024 talks: scraper (tools/scrapers/talks/qip.py) from ~/Web/qip.iaqi.org/2024/
- QCrypt 2024 talks: scraper (tools/scrapers/talks/qcrypt.py) from ~/Web/qcrypt.iaqi.org/2024/
```

### Importer changes (small, surgical)

- `tools/scrapers/talks/importer.py:349-354` — currently hard-codes
  `'source_type': 'conference_website'`. Change to: read
  `talk.get('source_type')` from the CSV row; default to `"scraper"`
  if missing.
- `tools/scrapers/committees/importer.py` — equivalent change in
  `import_member` (currently the importer doesn't write metadata at
  all for committees beyond the existing `affiliation` field — confirm
  scope before editing).
- No CSV write-side change needed: scrape runners already write the
  default-`"scraper"` rows by omitting the column. Claude-direct CSVs
  populate `source_type` explicitly per row.

### Why this layering

- **Trust gradient queries**: `SELECT count(*) FROM authorships WHERE metadata->>'source_type' = 'claude_extraction'` immediately shows the AI-extracted footprint.
- **Bulk re-verification**: if one Claude-extracted batch is later found to be wrong, you can find and re-do exactly that batch.
- **Reversible**: defaults preserve current behavior; nothing breaks for already-imported data.
- **No directory or filename split**: keeps the `data/conferences/<venue>_<year>/` layout uniform.

## CSV content scope

**Core principle**: each CSV captures everything that the source page
(or local mirror, or PDF) directly states. Nothing more.

| Field | Policy |
|-------|--------|
| `title` | Required. Always present in the source. |
| `speakers` | Required when stated. |
| `authors` | Capture when listed separately from speakers. If only "speakers" is stated, leave `authors` blank — the importer falls back to `speakers` for authorship rows. |
| `affiliations` | Capture only what's on the page; never infer from external lookups. |
| `abstract` | **Capture whenever available** — high-value content. Many archived sites include abstracts on talk-detail pages or accordion panels. Worth a second pass through the source if abstracts exist on per-talk pages but the initial scrape grabbed only the program list. |
| `arxiv_ids` | Capture **only when explicitly linked from the talk's source page** (e.g. an `<a href="https://arxiv.org/abs/...">` next to the title, or a "preprint:" line). **Never** search arXiv to find a probable preprint — that's where AI hallucination risk is highest. Multiple IDs are fine (semicolon-separated; the schema is an array). |
| `presentation_url` | Capture when slides PDF is linked. |
| `video_url` / `youtube_id` | Capture when video is linked from the source page. (Bulk video enrichment is a separate, deferred track — see YouTube section.) |
| `session_name` | Capture when the program groups talks under named sessions. |
| `award` | Capture when stated (e.g. "Best Student Paper"). |
| `scheduled_date` / `scheduled_time` / `duration_minutes` | Capture from the program when shown. ISO date / 24h time. |
| `notes` | Free-form. Use sparingly — for one-off provenance notes ("extracted from PDF p. 4") or quirks. |

### Why "never search arXiv"

A talk title and an arXiv preprint title are often nearly identical but
not exactly identical, and the same group can have multiple closely
related preprints. Letting Claude (or a script) "find the arXiv ID for
this talk" is exactly the hallucination mode we want to prevent —
it produces *plausible* IDs that may attribute the wrong paper. Only
record the ID if it's printed on or linked from the source page.

If we later want bulk arXiv enrichment, that becomes a separate
verification-heavy track (similar to YouTube enrichment), with the
same protocol: deterministic matching with confidence scores, manual
review for low-confidence rows, never silent inference.

### Multiple arXiv IDs per talk

The schema already supports it (`arxiv_ids` is an array). When a talk
covers a series of papers and the source page lists multiple, capture
all in the CSV cell, semicolon-separated:
`2401.12345;2401.67890`. Don't pick one as "primary".

### When to do a deep pass on abstracts

If the initial scrape only grabs program-listing pages but per-talk
detail pages exist (Indico-based sites, QIP 2026 Craft CMS, QCrypt
WordPress), it's worth a second pass to pull abstracts from the detail
pages. This roughly doubles the source-fetching work but is the most
valuable content addition.

## Inventory tables

CSV row counts exclude the header. Talk-row sub-counts are
`(rows / sched_date populated / sched_time populated / video_url / youtube_id)`.
Committees count is row count.

### QIP (1998–2026 seeded; no proceedings/workshop tracks)

| Year | Committees | Talks (rows / date / time / video / yt) | Status |
|------|-----------:|----------------------------------------|--------|
| 1998 | 14 | 27 (27/27/0/0) | ✓ |
| 1999 | 13 | 25 (25/25/0/0) | ✓ |
| 2000 |  2 | 28 (28/28/0/0) | committees thin |
| 2001 |  3 | 28 (28/28/0/0) | committees thin |
| 2002 |  2 | 35 (20/20/0/0) | committees thin |
| 2003 |  – | – | not seeded? archive missing |
| 2004 | 27 | 34 (0/34/0/0) | ✓ row count correct (471 was `wc -l` artifact); no abstracts |
| 2005 |  3 | 33 (33/33/0/0) | committees thin |
| 2006 | 27 | 40 (40/40/0/0) | ✓ |
| 2007 | 16 | 38 (34/34/0/0) | ✓ |
| 2008 | 26 | 78 (42/42/0/0) | ✓ talks scheduled (10 inv + 30 reg + 2 tut + 36 posters); posters lack times by design |
| 2009 | 32 | 65 (0/0/0/0) | no schedule |
| 2010 | 32 | 40 (40/40/38/0) | ✓ |
| 2011 | 37 | 58 (58/58/41/0) | ✓ |
| 2012 | 32 | 50 (46/46/29/0) | ✓ |
| 2013 | 35 | 44 (43/44/41/0) | ✓ |
| 2014 | 43 | 45 (45/45/0/0) | ✓ schedule from cgi-bin/talks/allprint.pl.html; +4 missing invited speakers added |
| 2015 | 48 | 45 (45/45/41/0) | WIP per git diff |
| 2016 | 53 | 53 (53/53/0/0) | ✓ schedule from scientific-program.html; +8 tutorials +3 invited added |
| 2017 | 47 | 67 (67/67/0/0) | ✓ 4 tut + 3 inv + 6 ple + 54 reg; from index.html (plan note "MISSING" was wrong) |
| 2018 | 55 | 70 (70/70/0/0) | ✓ 8 tut + 3 inv + 5 ple + 54 reg; from QuTech HTML + Accepted-Talks PDF |
| 2019 | 46 | 7 (7/0/0/0) | partial only — 7 rows ≠ full programme |
| 2020 | 79 | **0** | TALKS MISSING — **deferred** (SPA: index.html is empty, no extractable program) |
| 2021 | 46 | 113 (113/108/0/0) | ✓ |
| 2022 | 71 | **0** | TALKS MISSING |
| 2023 | 79 | 118 (117/117/108/0) | ✓ schedule from Indico timetable; +8 tutorials +1 invited added; 1 row (Liu Copy-Protection) lacks slot in archived JSON |
| 2024 | 85 | 131 (20/16/0/0) | partial schedule |
| 2025 |  – | – | not seeded |
| 2026 | 154 | 158 (152/152/0/0) | ✓ JSON-backed talks; 6 talks missing schedule; posters pending separate JSON |

### QCrypt (2011–2024 seeded; 2025/2026 not seeded; no proceedings/workshop)

| Year | Committees | Talks (rows / date / time / video / yt) | Status |
|------|-----------:|----------------------------------------|--------|
| 2011 | 27 | 30 (30/30/25/0) | ✓ |
| 2012 | 35 | 31 (31/31/29/0) | ✓ |
| 2013 | 44 | 46 (46/46/34/34) | ✓ |
| 2014 | 38 | 41 (41/41/37/37) | ✓ |
| 2015 | 41 | 40 (40/40/0/0) | no video |
| 2016 | 39 | 37 (37/37/0/0) | no video |
| 2017 | 43 | 203 (203/43/43/43) | ✓ 44 talks + 159 posters; posters legitimately lack scheduled_time |
| 2018 | 46 | 38 (38/38/37/0) | no yt id |
| 2019 | 43 | 41 (41/41/0/0) | no video |
| 2020 | 50 | 46 (46/46/0/0) | no video |
| 2021 | 63 | 44 (44/44/0/0) | no video |
| 2022 | 53 | 46 (46/46/0/0) | no video |
| 2023 | 50 | 47 (47/47/0/0) | no video |
| 2024 | 49 | 50 (50/50/0/0) | no video |
| 2025 | – | – | not seeded |
| 2026 | – | – | not seeded |

QCrypt is the most complete venue. Schedule data is essentially 100%.
Video URLs only for 2011–2014; YouTube playlist enrichment would
fill 2013 onward.

### TQC (2006–2025 seeded; uses proceedings.csv + workshop.csv, no talks.csv)

| Year | Committees | Proc | Workshop (rows / date / time / video / yt) | Status |
|------|-----------:|-----:|--------------------------------------------|--------|
| 2006 | – | – | – | **deferred** — local archive shell-only (Wayback links to kecl.ntt.co.jp) |
| 2007 | – | – | – | **deferred** — same as 2006 |
| 2008 | 24 | – | 20 (20/20/0/0) | ✓ 6 invited + 14 contributed; LNCS 5106 post-proc not in CSV |
| 2009 |  0 | – | 13 (0/0/0/0) | ✓ partial: 13 speakers from sparse archive; no committees, no schedule |
| 2010 | 37 | – |  5 (0/0/0/0) | ✓ partial: committees + 5 invited speakers; talk roster unrecoverable |
| 2011 | 36 | 17 (17 sched) | 6 (6/6/0/0) | ✓ full: PC 24 + OC 8 + SC 4; LNCS 6745 post-proc; 6 invited |
| 2012 | 24 | 16 (16 sched) | 8 (8/8/0/0) | ✓ full: PC 17 + OC 2 + SC 5; LNCS 7582 post-proc; 8 invited |
| 2013 | 34 | 22 (20 sched) |  8 (8/8/0/0)   | ✓ all 3 CSVs; +5 invited in workshop |
| 2014 | 30 | 18 (18 sched) |  4 (4/4/0/0)   | ✓ all 3 CSVs; +3 invited in workshop |
| 2015 | 36 | 16 (16 sched) | 12 (12/12/0/0) | ✓ all 3 CSVs; +4 invited in workshop |
| 2016 | 38 |  9 (9 sched)  | 21 (21/21/0/0) | ✓ all 3 CSVs; +4 invited in workshop |
| 2017 | 53 | 10 (6 sched)  | 32 (32/32/0/0) | ✓ schedule done; 4 proc papers without workshop counterpart unmatched |
| 2018 |  0 | 10 (0 sched)  | 0 | committees + workshop unrecoverable (Wix SPA shell) |
| 2019 | 42 | 10 (8 sched)  | 48 (44/44/0/0) | ✓ TQC + NISQ workshop talks merged |
| 2020 | 42 | 12 (12 sched) | 47 (47/47/0/0) | ✓ all entries scheduled (online conf) |
| 2021 | 51 | 10 (10 sched) | 85 (82/82/0/0) | ✓ lightning-talk era; pre-recorded |
| 2022 | 50 | 12 (12 sched) | 48 (48/48/0/0) | ✓ workshop built fresh from PDFs |
| 2023 | 55 | 14 (0 sched)  | 59 (59/59/0/0) | ✓ workshop has schedule; proc still lacks (TODO: copy from workshop) |
| 2024 | 61 | 12 (0 sched)  | 92 (92/92/0/0) | ✓ workshop has schedule; proc still lacks (TODO) |
| 2025 | 76 | 12 (12 sched) | 90 (90/90/0/0) | ✓ all entries scheduled |

TQC has zero schedule and zero video data anywhere in workshop.csv.
Pre-2013 (2006–2012) committee/proceedings data is not in the CSV tree
even though those years are seeded as conferences in the DB.

## Local mirror & parser support (cross-reference)

| Venue/year | Local mirror | Mirror quality | Parser support |
|---|---|---|---|
| QIP 2017 | yes (181 MB, registration only) | unusable — no program archived | none |
| QIP 2018 | yes (177 MB, programs in PDFs) | PDF-only | none |
| QIP 2020 | yes (880 KB, SPA) | unusable — JS-rendered | none |
| QIP 2021 | yes | GOOD — `monday.html`–`friday.html` static | WIP parser planned in memory |
| QIP 2022 | per memory: "manually collected" | unclear | none |
| QIP 2023 | yes (70 MB, Indico) | FAIR — list pages static, detail pages JS | none |
| QIP 2024 | yes (34 MB, HotCRP) | GOOD | none — current talks.csv has 131 rows |
| QIP 2026 | yes (6.9 MB, Craft CMS) | GOOD | yes (current parser hard-coded for 2026) |
| QCrypt 2011–2024 | yes (all years) | GOOD across the board | yes (year-aware) |
| TQC 2013–2024 (proc) | n/a (LIPIcs API) | structured | yes (LIPIcs fetcher) |
| TQC 2017/19/20/21/25 (workshop) | partial | sparse | none |
| TQC 2023–2024 | BibTeX + calendar inputs already exist | structured | one-off converter |

Note: QCrypt parser already supports all years (year-aware URLs +
`_PATH_OVERRIDES`); QIP parser is currently hard-coded to 2026 URLs.

## Execution order

1. **Phase 0 — Anomaly cleanup**: ✅ done (2026-05-08). All three
   suspected anomalies were misdiagnoses (`wc -l` artifacts, posters
   without `scheduled_time`, output-path mismatch). See top of file.
2. **Phase 1 — Gap-fill (CSVs)**: per-gap table, treating each row as a
   discrete deliverable. One conference-year per CSV pass.
3. **Phase 2 — YouTube enrichment**: deferred indefinitely. Captured in
   the "YouTube enrichment (deferred)" section below for future pickup;
   not part of current work.

## Recommended methods per gap

Coloring: **scraper** = use existing/extend Python parser (rows tagged
`source_type=scraper` at import); **claude-direct** = Claude reads local
source and writes CSV with the verification protocol (rows tagged
`source_type=claude_extraction`); **defer** = no usable source.

### QIP

| Year | Gap | Method | Notes |
|------|-----|--------|-------|
| 2003 | not seeded | defer | no archive |
| 2004 | talks.csv ✓ (34 rows); abstracts mostly empty + a few title/abstract concatenations | claude-direct cleanup later | parser bug in `_parse_2004_abstracts_section` left some rows with merged title+abstract (e.g. rows 13, 14, 28); low priority |
| 2008 | done (78 rows: 42 scheduled talks + 36 posters) | claude-direct from QIP2008_files/Program.pdf | invited titles filled, +2 tutorials added; posters left unscheduled per convention |
| 2009 | no schedule (65 talks) | claude-direct | small batch, one-off |
| 2014 | done (45 rows w/ schedule) | claude-direct | extracted from cgi-bin/talks/allprint.pl.html |
| 2015 | WIP (45 rows, modified locally) | finish current WIP | already in progress |
| 2016 | done (53 rows w/ schedule, incl tutorials) | claude-direct | extracted from scientific-program.html + tutorial-program.html |
| 2017 | done (67 rows w/ schedule) | claude-direct from index.html | "TALKS MISSING" plan note was wrong — index.html had full Schedule & Videos block incl. parallel tracks; presenters resolved via slide-PDF filenames |
| 2018 | done (70 rows w/ schedule) | claude-direct | from QuTech HTML schedule page + QIP-2018-Accepted-Talks PDF; 5 plenaries, Penington=Best Student Paper |
| 2019 | only 7 of ~50 talks | claude-direct | re-extract from whichever archive exists |
| 2020 | TALKS MISSING (SPA) — **deferred** | needs Wayback / DBLP fetch | local archive's index.html is empty (0 lines); only static CSS/JS remain. Defer until external source fetched. |
| 2021 | 113 talks ✓ but no video | done; revisit via YouTube enrichment | parser plan in memory is now stale (data already imported?) — verify before extending |
| 2022 | TALKS MISSING — **deferred** | needs Wayback / DBLP | no local archive at `~/Web/qip.iaqi.org/2022/`; only `previousqips.html` line "QIP 2022: Pasadena, CA, USA (Caltech)" exists. Conference was virtual (COVID). Defer until an external source is fetched. |
| 2023 | done (118 rows w/ schedule) | claude-direct | Indico timetable JSON had full 7-day schedule in one file (`event/13076/timetable/index.html`); 1 row missing slot in archived JSON |
| 2024 | 131 talks but only 20 have dates | claude-direct | re-extract schedule from HotCRP mirror |
| 2025 | not seeded | seed conference + scraper or claude-direct | once archive is available |
| 2026 | 158 talks ✓ (JSON-backed via `tools/one_off/qip2026/`); 6 missing schedule; posters pending | JSON conversion (existing pipeline) + website schedule refresh | Talks come from `qip2026-data.json` (158 papers) — fully reliable. Posters will arrive as separate JSON later. Schedule extraction from `qip_2026_schedule.html` is the only un-reliable bit; needs a re-scrape if the website has been updated since the snapshot, plus claude-direct fill for the 6 unscheduled talks. |

### QCrypt

QCrypt is essentially complete for committees + talks 2011–2024. The
main remaining gap is **video URLs** (only 2011–2014 have them) and
**YouTube IDs** (only 2013, 2014, 2017). Recommended path: a separate
YouTube enrichment pass (deferred — see below), not re-scraping HTML.

| Year | Gap | Method |
|------|-----|--------|
| 2011–2024 | sparse video / yt fields | YouTube enrichment (deferred) |
| 2025 | not seeded | seed when archive is published |
| 2026 | not seeded | (call for papers presumably out) |

### TQC

| Year | Gap | Method | Notes |
|------|-----|--------|-------|
| 2006–2012 | not in CSV tree at all (despite being seeded) | claude-direct, best-effort from local mirrors | per audit, some 2006/2007 mirrors exist on disk but are very thin (7–16 files); extract whatever's available, accept gaps |
| 2013, 2016 | committees missing | claude-direct from any available archive | |
| 2018 | committees + workshop missing | claude-direct or defer — small mirror | |
| 2017/19/20/21/25 | workshop has rows, zero schedule/video metadata | claude-direct from local mirror | |
| 2022/23/24 | workshop.csv missing entirely | check `tools/one_off/tqc2023-24/` output — BibTeX conversion was supposedly done; the CSV may just need to be moved into place | |
| All years | no video / yt anywhere | YouTube enrichment if a TQC channel exists (deferred) | |

## Tipping-point summary applied here

- **Keep the scrapers** for QCrypt (year-aware, all 14 years, recurring
  conference) and the QIP 2026+ template (recurring).
- **Don't write new per-year QIP parsers** for 2008/2009/2014/2016/2018/
  2022/2023 talks. These are one-offs in stable archive form. Use
  Claude-direct with the verification protocol; it's cheaper than parser
  work and the data won't change.

## YouTube enrichment (deferred — captured for future pickup)

**Decision: defer indefinitely.** Documented here so the design is
preserved when the work is picked up later. Not part of the current
ingestion pass.

Goal: populate `video_url`, `youtube_id`, and infer `presenter_author_id`.

### Sources

- **QCrypt** — channel `@qcryptconference239`, playlists per year.
  <https://www.youtube.com/@qcryptconference239/playlists>
- **QIP** — TBD; check IAQI's channel listings.
- **TQC** — TBD; some years have recordings, channel unclear.

### Method

1. **Fetch playlist metadata** with `yt-dlp --flat-playlist --print '%(id)s\t%(title)s\t%(channel)s'` — no API key needed, no scraping. Saves to a per-year JSON/TSV.
2. **Match videos to publications** by fuzzy title:
   - Use `src/utils/normalize.rs::normalize_for_loose_match` style logic on both video title and CSV `title`.
   - Score with Jaccard or token-sort ratio; require ≥0.85 to auto-accept.
   - Lower scores go to a manual-review queue.
3. **Infer presenter** from the video title pattern. Common formats:
   - `"Speaker Name – Talk Title"` (em-dash separator)
   - `"Talk Title | Speaker Name"`
   - `"[Year] Speaker Name: Title"`

   Parse with a few alternative regexes; the speaker-side is matched
   against the publication's `authors` list. Only set
   `presenter_author_id` when there's a confident author match;
   otherwise stash the inferred name in `metadata.presenter_inferred`
   for human review.
4. **Update CSV in place** rather than DB-direct, so the workflow
   stays "edit CSV → import" and preserves the source-of-truth model.

### Verification protocol for YouTube enrichment

- Show fuzzy-match score with each proposed pairing; reject low confidence.
- Spot-check by clicking through 5 random video URLs to confirm content.
- Cross-check video count against expected talk count per playlist
  (most QCrypt playlists ~ contributed-talk count).
- Never overwrite an existing non-null `video_url` without explicit
  flag; treat the human-curated 2011–2014 entries as ground truth.

## Verification plan (overall)

For any CSV produced (whether by scraper or by Claude direct):

1. Total row count matches the source page's published total when stated.
2. Spot-check 3 random rows against source HTML/PDF.
3. `import_from_csv.py {committees|talks} <csv> --dry-run` parses cleanly.
4. After real import, hit `/api/v1/publications?conference_id=...` to
   confirm row count round-trips.

For Claude-extracted CSVs specifically, **also**:

5. Confirm `source_type=claude_extraction` is set on every row.
6. Confirm `source_url` (in metadata or in `notes` for now) points at a
   local file path that exists.
7. Sanity-query post-import:
   ```sql
   SELECT venue, year, count(*) FROM publications p
   JOIN authorships a ON a.publication_id = p.id
   WHERE a.metadata->>'source_type' = 'claude_extraction'
   GROUP BY 1, 2;
   ```
   to confirm the AI-extracted footprint matches expectations.

## Resolved decisions (2026-05-08 conversation)

- **Anomalies investigated first** before any new ingestion (Phase 0).
- **QIP 2017 / 2020**: best-effort titles-only CSVs from whatever
  external source is available (Wayback, DBLP, social).
- **YouTube enrichment**: deferred indefinitely; design preserved above.
- **TQC 2006–2012**: best-effort from local mirrors, accept gaps.
- **CSV source-tracking column**: `source_type` added with values
  `scraper` / `claude_extraction`; importer reads from CSV with default
  `"scraper"`.
- **QIP 2008 WIP**: finish the existing in-flight parser (poster
  parsing is mostly written); validate against source HTML; commit.
  Departs from the strict claude-direct heuristic for this one year
  because the parser work is already most of the way done.
- **Batch size for claude-direct passes**: one conference-year per CSV
  pass. Keeps spot-checks tractable and a wrong batch contained.
- **CSV content scope**: capture every field present on the source
  page; never infer or look up missing fields elsewhere. See "CSV
  content scope" section above for the per-field policy on abstracts,
  arxiv IDs, etc.
</content>
</invoke>