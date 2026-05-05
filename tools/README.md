# QuantumDB tools

Where things live:

- **`/data/conferences/`** (top level of the repo) — the canonical CSVs.
  Edit these to fix author names, affiliations, talks, committees, etc.
  See `/data/README.md` for schemas and the contributor guide.
- **`tools/scrape_committees/`** — scrapers + import script for committee data.
- **`tools/scrape_talks/`** — scrapers + import script for talks/papers data.
- **`tools/generate_token.sh`** — generate a Bearer token for the API.
- **`tools/reset-db.sh`** — reset the local dev database.

## Workflows

### Recent conferences (with JSON from the program committee)

For QIP 2026 and similar, where you have a JSON dump from the submission system:

```bash
cd tools/scrape_talks/qip2026
python3 convert_json_to_csv.py qip2026-data.json \
  ../../../data/conferences/qip_2026/raw/papers_compact.csv

# Enrich with the published schedule:
python3 parse_schedule.py \
  ../../../data/conferences/qip_2026/raw/qip_2026_schedule.html \
  ../../../data/conferences/qip_2026/raw/papers_compact.csv \
  ../../../data/conferences/qip_2026/talks.csv
```

Then import:

```bash
cd tools/scrape_talks
./import_from_csv.py ../../data/conferences/qip_2026/talks.csv
```

### Historical conferences (web scraping)

```bash
cd tools/scrape_talks
./scrape_to_csv.py --venue QIP --year 2025 --local
# Writes to /data/conferences/qip_2025/talks.csv

./import_from_csv.py ../../data/conferences/qip_2025/talks.csv
```

The same pattern works for committees:

```bash
cd tools/scrape_committees
./scrape_to_csv.py --venue QIP --year 2025 --local
./import_from_csv.py ../../data/conferences/qip_2025/committees.csv
```

## Notes

- All scrapers default `--output-dir` to `<repo>/data/conferences/`. Pass an
  explicit `--output-dir` if you want to save somewhere else (e.g. for a
  staged review).
- Import scripts take any path as a positional argument; the new layout is
  not enforced, just preferred.
- See `/data/SOURCES.md` for the per-conference list of source URLs and
  parser notes.
