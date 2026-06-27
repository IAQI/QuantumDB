# QuantumDB tools

Where things live:

- **`/data/conferences/`** (top level of the repo) — the canonical CSVs.
  Edit these to fix author names, affiliations, talks, committees, etc.
  See `/data/README.md` for schemas and the contributor guide.
- **`tools/scrapers/`** — unified scraper + importer (committees, talks,
  business-meetings). See `tools/scrapers/README.md`.
- **`tools/one_off/`** — historical / one-off conversion scripts kept for
  reference (e.g. the QIP 2026 JSON pipeline, TQC LIPIcs fetcher,
  monolithic historical scrapers).
- **`tools/dedup_authors.py`** — merge duplicate/aliased author rows into one
  canonical identity (curated `data/author_aliases.csv` + normalized-name
  collapse); reassigns authorships/committee roles and refreshes the
  materialized views. Dry-run by default; `--commit` to apply.
- **`tools/video_pass.py`** — harvest `video_url`/`youtube_id` for talks from
  conference YouTube channels (see `tools/video_channels.json` and
  `data/VIDEO_SOURCES.md`).
- **`tools/generate_token.sh`** — generate a Bearer token for the API.
- **`tools/reset-db.sh`** — tear down the dev DB volume and rebuild from
  migrations + seeds.

## Workflow

```bash
cd tools/scrapers

# Scrape (committees | talks)
./scrape_to_csv.py committees --venue QIP    --year 2024 --local
./scrape_to_csv.py talks      --venue QCRYPT --year 2023 --local

# Import (committees | talks | business-meetings); paths default to /data/conferences/<slug>/
./import_from_csv.py committees        ../../data/conferences/qip_2024/committees.csv --dry-run
./import_from_csv.py talks             ../../data/conferences/qcrypt_2023/talks.csv
./import_from_csv.py business-meetings ../../data/conferences/qcrypt_2022/business_meeting.csv
```

## Notes

- Scrapers default `--output-dir` to `<repo>/data/conferences/`. Pass an
  explicit `--output-dir` if you want to save somewhere else (e.g. a
  staged review).
- The import CLI accepts any path; the canonical layout is preferred but
  not enforced.
- See `/data/SOURCES.md` for per-conference source URLs and parser notes.
