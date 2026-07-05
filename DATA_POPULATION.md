# Data Population Guide

How conference data (committees, talks, proceedings) gets into QuantumDB.

> **Roadmap vs. mechanics.** This file documents the *mechanics* of the
> pipeline. For the *plan* — which conference-years are complete, partial, or
> missing, and how each gap should be filled — see
> [`docs/DATA_INGESTION_PLAN.md`](docs/DATA_INGESTION_PLAN.md), which is the
> authoritative working document.

## The pipeline

QuantumDB uses a **CSV-as-source-of-truth** model:

```
  scrape (or hand-extract)        import
  ───────────────────────►  CSV  ─────────►  PostgreSQL
                             │
                   data/conferences/<venue>_<year>/
```

1. **CSVs are the source of truth.** Every conference's data lives in
   `data/conferences/<venue>_<year>/` as plain CSV files. To *fix* data, edit
   the CSV and re-import — don't patch the database directly.
2. **Scrapers and the importer are separate.** Scraping produces a CSV;
   importing reads a CSV into the database. They never talk to each other
   directly.
3. **Provenance is tracked.** `data/SOURCES.md` records where each CSV came
   from; row-level `metadata` JSONB records `source_type` per row.

### CSV layout

```
data/conferences/
├── qip_2024/
│   ├── committees.csv      # committee membership
│   ├── talks.csv           # talks / papers
│   └── posters.csv         # accepted posters (paper_type=poster)
├── tqc_2023/
│   ├── committees.csv
│   ├── proceedings.csv     # TQC only — formal LIPIcs proceedings track
│   ├── workshop.csv        # TQC only — workshop track
│   └── posters.csv         # accepted posters
└── ...
```

- QIP / QCrypt use `committees.csv` + `talks.csv` (+ `posters.csv` where posters exist).
- TQC uses `committees.csv` + `proceedings.csv` + `workshop.csv` (no `talks.csv`), + `posters.csv`.
- **`posters.csv`** shares the exact talks-CSV schema (all rows `paper_type=poster`) and imports
  through the same `import_from_csv.py talks` path. Posters live here rather than in `talks.csv`
  because they typically outnumber talks several-fold; keeping the two apart keeps `talks.csv`
  reviewable. It is scraper-owned and overwritten wholesale, so do not hand-edit it — fix the
  parser or source instead.
- Full column schemas for each CSV type are in [`data/README.md`](data/README.md).

## Tooling

The unified scrape + import package lives in `tools/scrapers/`:

```
tools/scrapers/
├── scrape_to_csv.py        # CLI: scrape a conference → CSV  (committees|talks|posters)
├── import_from_csv.py      # CLI: import CSV(s) → database  (committees|talks|business-meetings)
├── committees/             # per-venue committee scrapers + importer
│   ├── qip.py  qcrypt.py  tqc.py
│   ├── runner.py           # scrape orchestration
│   └── importer.py         # DB import logic
├── talks/                  # per-venue talk scrapers + importer
│   ├── qip.py  qcrypt.py  tqc.py
│   ├── runner.py
│   └── importer.py
├── posters/                # accepted-poster scrapers (scrape-only; posters.csv)
│   ├── parsers.py  runner.py
└── business_meetings/      # business-meeting CSV importer (import-only)
    └── importer.py
```

Archived one-off and historical scrapers (QIP 2026 JSON converter, the
TQC 2023–24 BibTeX converter, the old monolithic scrapers, the LIPIcs fetcher)
live under `tools/one_off/` — kept for reference, not part of the live pipeline.

### Prerequisites

```bash
# Stack running (provides the database on localhost:5432)
docker compose up -d

# Python deps for the scrapers
pip install -r tools/scrapers/requirements.txt

# The importer needs DATABASE_URL (or pass --db-url explicitly)
export DATABASE_URL=postgres://quantumdb:quantumdb@localhost:5432/quantumdb
```

## Scraping to CSV

```bash
cd tools/scrapers

# Scrape committees for one conference (from a local HTML mirror under ~/Web)
./scrape_to_csv.py committees --venue QIP --year 2024 --local

# Scrape talks
./scrape_to_csv.py talks --venue QCRYPT --year 2023 --local

# Scrape accepted posters -> posters.csv (registered years only; see below)
./scrape_to_csv.py posters --venue QCRYPT --year 2020 --local
./scrape_to_csv.py posters --venue TQC --year 2024 --local --dry-run   # preview first

# Fetch from the live web instead of a local mirror (omit --local)
./scrape_to_csv.py committees --venue QCRYPT --year 2024

# Point at a specific local file / base directory
./scrape_to_csv.py talks --venue QIP --year 2024 --local-file ~/Web/qip.iaqi.org/2024/program.html
```

Output is written to `data/conferences/<venue>_<year>/<committees|talks|posters>.csv`.
Use `--force` to overwrite an existing file.

### Poster scraping (`posters` subcommand)

Accepted-poster pages differ wildly per year, so the poster scraper maps each `(venue, year)` to a
format-family parser and its local source page(s) in `POSTER_SOURCES`
(`tools/scrapers/posters/runner.py`). To add a year, inspect its page, add/reuse a parser in
`parsers.py`, and register it. Sources may be HTML pages, a teachpress `.bib` export
(TQC 2023/2024), or a PDF (`pdftotext -layout` — needs poppler). Parser unit tests:
`python3 tools/scrapers/posters/test_parsers.py`.

Currently registered: QCrypt 2011/2013/2016/2018/2020/2021/2022 (2017/2023/2024/2025 come from JSON
via `talks/qcrypt_json_to_csv.py`); QIP 2006/2009/2010/2011/2012/2015/2016/2019;
TQC 2019/2020/2021/2023/2024/2025. **Not yet done** (unstructured prose or PDFs needing manual
entry): QIP 2002/2005/2013/2023, QCrypt 2019, QCrypt 2014 (never published).

**Scraper coverage is uneven** — the QCrypt scrapers are year-aware and cover
all years; the QIP talk scraper is currently tailored to recent years. For
conference-years with no usable scraper (old archives, JS-rendered SPAs,
PDF-only programs), CSVs are built by **direct extraction** from a saved local
source, following the verification protocol in `docs/DATA_INGESTION_PLAN.md`.
Either way, the result is the same: a CSV in `data/conferences/`.

## Importing a CSV

```bash
cd tools/scrapers

# Always dry-run first — parses and validates without writing
./import_from_csv.py committees ../../data/conferences/qip_2024/committees.csv --dry-run

# Real import
./import_from_csv.py committees ../../data/conferences/qip_2024/committees.csv

# Talks
./import_from_csv.py talks ../../data/conferences/qcrypt_2023/talks.csv

# Posters (same schema/importer as talks)
./import_from_csv.py talks ../../data/conferences/qcrypt_2023/posters.csv

# Multiple files at once (picks up talks.csv, posters.csv, proceedings.csv, …)
./import_from_csv.py talks ../../data/conferences/tqc_2023/*.csv

# Business-meeting stats (tall CSV: one row per announced fact)
./import_from_csv.py business-meetings ../../data/conferences/qcrypt_2022/business_meeting.csv

# Override the database connection
./import_from_csv.py committees path/to.csv --db-url postgres://user:pass@host/db
```

The importer:
- Resolves the conference by `(venue, year)` — it must already be seeded.
- Finds or creates authors via normalized-name matching (see "Deduplication");
  existing authors are updated in place rather than duplicated.
- Inserts `committee_roles` / `publications` + `authorships` rows. The
  committees importer does explicit find-then-update-or-insert; the talks
  importer generates `canonical_key`s and wraps each row in its own savepoint
  so one bad row doesn't poison the rest of the file.
- Writes a `metadata` JSONB with source info on each row. **Note:** the talks
  importer currently hard-codes `source_type: "conference_website"` for every
  row. The CSV-driven `source_type` convention (`"scraper"` vs
  `"claude_extraction"`) is described in `docs/DATA_INGESTION_PLAN.md` as a
  planned surgical change to `talks/importer.py` — it is **not yet wired up**,
  so verify before relying on `source_type` to distinguish trust classes.

### After a bulk import

Refresh the materialized views:

```bash
docker exec quantumdb-db-1 psql -U quantumdb -d quantumdb -c \
  "REFRESH MATERIALIZED VIEW CONCURRENTLY author_stats;
   REFRESH MATERIALIZED VIEW CONCURRENTLY conference_stats;
   REFRESH MATERIALIZED VIEW CONCURRENTLY coauthor_pairs;"
```

Or hit the auth-protected `GET /admin/refresh-stats` endpoint.

## Prerequisite: conference metadata

The importer matches CSVs to conferences by `(venue, year)`, so the conference
row must exist first. Conference metadata is seeded from:

```
seeds/insert_qip_conferences.sql
seeds/insert_qcrypt_conferences.sql
seeds/insert_tqc_conferences.sql
```

These run automatically on a fresh database (`docker-init.sh` runs everything
in `seeds/` after `migrations/`). To add a not-yet-seeded year, add it to the
relevant seed file (or insert it via the API) before importing its CSVs.

## Data quality

### Name normalization & deduplication

Authors are matched by **normalized name** (`normalize_name()` in
`src/utils/normalize.rs` — Unicode NFKD, accent stripping, lowercasing,
middle-initial folding; the importer mirrors this logic). Before that lookup the
importer resolves **`data/author_aliases.csv`** (columns
`former_name,current_name,variant_type,notes`): a former/variant spelling maps
to its canonical name, so the row is found-or-created under the canonical
identity — even surname changes ("Tobias Eberle" → "Tobias Gehring") the DB has
no other signal for. The printed spelling is preserved in each authorship's
`published_as_name` (and recorded in `author_name_variants`). A new author row is
created only when no alias/normalized/variant match is found.

Because aliases are applied **at ingest**, a fresh rebuild-from-CSV yields no
aliased duplicate rows — `tools/dedup_authors.py` is **not** part of the reload
path (just refresh the materialized views afterward). It is retained for the
**incremental** live-DB path, where it consolidates any pre-existing duplicate
rows and refreshes the views. It does two things:

- **Curated aliases** (`data/author_aliases.csv`) — the same file the importer
  now reads, applied here to merge any legacy rows created before ingest-time
  resolution existed. Matched by exact `full_name`.
- **Normalized-name collapse** — residual duplicates that share a
  `normalized_name` (e.g. "Alex B. Grilo" vs "Alex Bredariol Grilo").

In both cases each authorship's `published_as_name` is preserved (the paper
keeps the name it was published under) and the merged spelling is recorded in
`author_name_variants`.

Find potential duplicates:

```bash
docker exec quantumdb-db-1 psql -U quantumdb -d quantumdb -c "
SELECT normalized_name, COUNT(*), array_agg(full_name)
FROM authors GROUP BY normalized_name HAVING COUNT(*) > 1;"
```

### Source tracking

Imported rows carry a `metadata` JSONB with provenance:

```json
{
  "source_type": "conference_website",
  "source_url": "...",
  "scraped_date": "2026-05-09",
  "notes": "Imported from CSV"
}
```

The *intended* `source_type` convention distinguishes trust classes —
`"scraper"` (re-runnable Python parser) vs `"claude_extraction"` (one-shot
direct extraction) vs the standard `"dblp"` / `"arxiv"` / `"manual_entry"` /
`"orcid"` values. **As currently coded**, the talks importer writes
`"conference_website"` for every row regardless of origin; the CSV-column-driven
convention is planned but not yet implemented. See
`docs/DATA_INGESTION_PLAN.md` for the full design and the exact importer change
required.

## Verification

For any CSV before/after import:

1. Row count matches the source page's published total when stated.
2. Spot-check 3 random rows against the source HTML/PDF.
3. `import_from_csv.py … --dry-run` parses cleanly.
4. After the real import, query the API or DB to confirm the row count
   round-trips:
   ```bash
   curl -s "http://localhost:3000/api/v1/publications?conference_id=<uuid>" | jq length
   ```

## Troubleshooting

### Importer can't find the conference
The `(venue, year)` isn't seeded. Check `SELECT venue, year FROM conferences`
and add the missing row to the relevant `seeds/` file first.

### Connection errors
Confirm the stack is up (`docker compose ps`) and `DATABASE_URL` points at
`localhost:5432` (host) — not `db:5432`, which only resolves inside Docker.

### Scraper produces an empty / wrong CSV
The local mirror may be JS-rendered or PDF-only (common for older years). Check
`docs/DATA_INGESTION_PLAN.md` for that conference-year's known status and
recommended extraction method.
