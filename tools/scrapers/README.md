# QuantumDB scrapers

Scrape committee membership and talk/paper data from conference websites
(or local mirrors) into CSV, then import the CSV into the database.

The canonical CSVs live one level up at
[`/data/conferences/<venue>_<year>/`](../../data/). Edit those directly
to fix data; this directory is the *tooling* that reads/writes them.

## Layout

```
tools/scrapers/
  scrape_to_csv.py         # unified scrape CLI
  import_from_csv.py       # unified import CLI
  base.py                  # shared Scraper ABC (HTTP / local-file fetcher)
  _lib.py                  # shared helpers (URL→local path, archive_url lookup)
  committees/              # committee-specific subpackage
    base.py, qip.py, qcrypt.py, tqc.py
    runner.py              # `scrape_to_csv.py committees ...` body
    importer.py            # `import_from_csv.py committees ...` body
  talks/                   # same shape for talks
    base.py, qip.py, qcrypt.py, tqc.py
    runner.py
    importer.py
```

Both CLIs use a `committees | talks` subcommand; the CSV schemas are
documented in [`/data/README.md`](../../data/README.md).

## Quick start

Install Python deps once:

```bash
pip install -r tools/scrapers/requirements.txt
```

Make sure `DATABASE_URL` is set (the dockerised dev DB, by default):

```bash
export DATABASE_URL=postgres://quantumdb:quantumdb@localhost:5432/quantumdb
```

### Scrape

The scraper reads `archive_*_url` columns from the `conferences` table to
locate the conference page (or the local mirror under `~/Web/` when
`--local` is passed). Output lands in
`/data/conferences/<venue>_<year>/{committees,talks}.csv` by default.

```bash
# Committees
./tools/scrapers/scrape_to_csv.py committees --venue QIP    --year 2024 --local
./tools/scrapers/scrape_to_csv.py committees --venue QCRYPT --year 2023

# Talks
./tools/scrapers/scrape_to_csv.py talks --venue QIP    --year 2024 --local
./tools/scrapers/scrape_to_csv.py talks --venue QCRYPT --year 2023

# Override target dir / overwrite an existing CSV
./tools/scrapers/scrape_to_csv.py talks --venue QIP --year 2024 \
    --output-dir /tmp/scratch --force
```

### Review & edit

Open the CSV in your editor of choice. Lists in cells are
semicolon-separated (e.g. `Alice Quantum;Bob Crypto`).

### Import

```bash
# Dry-run first
./tools/scrapers/import_from_csv.py committees \
    data/conferences/qip_2024/committees.csv --dry-run

# Real import
./tools/scrapers/import_from_csv.py talks \
    data/conferences/qip_2024/talks.csv
```

`--db-url` overrides `DATABASE_URL` if you need to point at a different
database (e.g. a staging copy).

## Adding a new venue/year parser

1. Drop a local mirror at `~/Web/<domain>/<year>/` (or rely on web fetch).
2. Make sure the `conferences` row exists in the DB and has its
   `archive_*_url` column(s) set so `--local` can resolve the page.
3. Edit the relevant venue file under `committees/` or `talks/`,
   implementing `parse_committee_data()` or `parse_talk_data()` for
   that year. The base classes take care of fetching the page,
   deduping, and shaping output.
4. Run the scraper and inspect the CSV. Iterate.

## Historical / one-off scripts

Earlier monolithic scrapers and one-off conversion projects (TQC LIPIcs
fetcher, QIP 2026 JSON converter, the TQC 2023-24 BibTeX/ICS pipeline,
etc.) live under [`tools/one_off/`](../one_off/) for reference. They
were used to bootstrap data and aren't expected to be run again.
