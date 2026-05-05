# QuantumDB tools

Where things live:

- **`/data/conferences/`** (top level of the repo) — the canonical CSVs.
  Edit these to fix author names, affiliations, talks, committees, etc.
  See `/data/README.md` for schemas and the contributor guide.
- **`tools/scrapers/`** — unified scraper + importer (committees + talks).
  See `tools/scrapers/README.md`.
- **`tools/one_off/`** — historical / one-off conversion scripts kept for
  reference (e.g. the QIP 2026 JSON pipeline, TQC LIPIcs fetcher,
  monolithic historical scrapers).
- **`tools/generate_token.sh`** — generate a Bearer token for the API.
- **`tools/reset-db.sh`** — reset the local dev database.

## Workflow

```bash
cd tools/scrapers

# Scrape (committees | talks)
./scrape_to_csv.py committees --venue QIP    --year 2024 --local
./scrape_to_csv.py talks      --venue QCRYPT --year 2023 --local

# Import (committees | talks); paths default to /data/conferences/<slug>/
./import_from_csv.py committees ../../data/conferences/qip_2024/committees.csv --dry-run
./import_from_csv.py talks      ../../data/conferences/qcrypt_2023/talks.csv
```

## Notes

- Scrapers default `--output-dir` to `<repo>/data/conferences/`. Pass an
  explicit `--output-dir` if you want to save somewhere else (e.g. a
  staged review).
- The import CLI accepts any path; the canonical layout is preferred but
  not enforced.
- See `/data/SOURCES.md` for per-conference source URLs and parser notes.
