# Data Population Guide

This guide covers populating QuantumDB with conference data from various sources.

## Overview

QuantumDB supports two main data population approaches:

1. **Committee Scraper** - Extracts committee memberships from archived websites
2. **HotCRP Importer** (planned) - Imports publications and authorships from HotCRP JSON exports

Both tools use **direct database access** via SQLx for performance and transactional integrity.

## Prerequisites

```bash
# Ensure database is running
docker compose up -d

# Or local PostgreSQL
brew services start postgresql@15

# Verify migrations are current
sqlx migrate run

# Load conference metadata (if not already done)
psql quantumdb < seeds/insert_qip_conferences.sql
psql quantumdb < seeds/insert_qcrypt_conferences.sql
psql quantumdb < seeds/insert_tqc_conferences.sql
```

## Committee Scraper

### Quick Start

```bash
# Dry run to preview what would be scraped
cargo run -p scrape_committees -- --dry-run

# Scrape all conferences with archive URLs
cargo run -p scrape_committees

# Scrape specific venue
cargo run -p scrape_committees -- --venue QIP

# Scrape specific conference
cargo run -p scrape_committees -- --venue QIP --year 2024

# Force re-scrape (overwrites existing data)
cargo run -p scrape_committees -- --force
```

### What It Does

1. Queries `conferences` table for entries with archive URLs
2. Fetches HTML from `archive_pc_url`, `archive_organizers_url`, `archive_steering_url`
3. Parses committee members using generic HTML selectors
4. Extracts names, affiliations, positions
5. Uses `normalize_name()` to find or create authors
6. Inserts into `committee_roles` with source metadata

### Output Example

```
INFO scrape_committees: Connected to database
INFO scrape_committees: Found 3 conference(s) to scrape
INFO scrape_committees: Processing QIP 2024
INFO scrape_committees: Scraping PC from: https://web.archive.org/web/20240315/qip2024.tw/pc
INFO scrape_committees: Successfully inserted 47 committee members for QIP 2024
```

### Verify Results

```bash
# Check inserted committee members
psql quantumdb -c "
SELECT c.venue, c.year, COUNT(*) as members
FROM committee_roles cr
JOIN conferences c ON cr.conference_id = c.id
GROUP BY c.venue, c.year
ORDER BY c.year DESC, c.venue;
"

# View specific conference committee
psql quantumdb -c "
SELECT a.full_name, cr.committee, cr.position, cr.role_title, cr.affiliation
FROM committee_roles cr
JOIN authors a ON cr.author_id = a.id
JOIN conferences c ON cr.conference_id = c.id
WHERE c.venue = 'QIP' AND c.year = 2024
ORDER BY cr.committee, cr.position;
"
```

## HotCRP Importer (Planned)

HotCRP conference management software can export submission data as JSON. This will be used to populate publications and authorships.

### Planned Usage

```bash
# Import from HotCRP JSON export
cargo run -p import_hotcrp -- qip2024.json

# Dry run mode
cargo run -p import_hotcrp -- --dry-run qip2024.json

# Specify conference
cargo run -p import_hotcrp -- --conference QIP2024 qip2024.json
```

### What It Will Do

1. Parse HotCRP JSON export
2. Extract accepted papers (or all submissions)
3. For each paper:
   - Create publication record
   - Parse author names and affiliations
   - Use `normalize_name()` to find or create authors
   - Create authorship records linking authors to publications
   - Populate metadata JSONB with HotCRP source info

### Expected HotCRP JSON Structure

```json
{
  "submissions": [
    {
      "pid": 123,
      "title": "Quantum Error Correction with...",
      "authors": [
        {
          "first": "Alice",
          "last": "Quantum",
          "email": "alice@example.edu",
          "affiliation": "MIT"
        }
      ],
      "abstract": "We present...",
      "decision": "accept",
      "submission_time": "2024-01-15T10:30:00Z"
    }
  ]
}
```

## Database State Management

### Approach

1. **Migrations** - Schema changes (already in `migrations/`)
2. **Seeds** - Minimal reference data (conference metadata)
3. **Scraped Data** - Bulk imports from tools (committees, publications)
4. **Snapshots** - Periodic backups after major imports

### Creating Snapshots

After running scrapers, create snapshots:

```bash
# Snapshot specific tables
pg_dump quantumdb \
  --data-only \
  --table=authors \
  --table=committee_roles \
  > snapshots/committee_data_$(date +%Y%m%d).sql

# Full database snapshot
pg_dump quantumdb > snapshots/full_db_$(date +%Y%m%d).sql

# Compressed backup
pg_dump quantumdb | gzip > snapshots/quantumdb_$(date +%Y%m%d).sql.gz
```

### Restoring from Snapshot

```bash
# Restore specific tables
psql quantumdb < snapshots/committee_data_20251230.sql

# Restore full database
dropdb quantumdb
createdb quantumdb
sqlx migrate run
psql quantumdb < snapshots/full_db_20251230.sql
```

## Workflow Example

Complete workflow for populating the database:

```bash
# 1. Fresh start
docker compose down -v
docker compose up -d
sleep 5  # Wait for PostgreSQL to start

# 2. Run migrations
sqlx migrate run

# 3. Load conference metadata
psql quantumdb < seeds/insert_qip_conferences.sql
psql quantumdb < seeds/insert_qcrypt_conferences.sql
psql quantumdb < seeds/insert_tqc_conferences.sql

# 4. Verify conferences loaded
psql quantumdb -c "SELECT venue, COUNT(*) FROM conferences GROUP BY venue;"

# 5. Scrape committees (dry run first)
cargo run -p scrape_committees -- --dry-run

# 6. Scrape committees (for real)
cargo run -p scrape_committees

# 7. Create snapshot
mkdir -p snapshots
pg_dump quantumdb --data-only > snapshots/with_committees_$(date +%Y%m%d).sql

# 8. Import HotCRP data (when available)
# cargo run -p import_hotcrp -- qip2024.json

# 9. Refresh materialized views
psql quantumdb -c "REFRESH MATERIALIZED VIEW CONCURRENTLY author_stats;"
psql quantumdb -c "REFRESH MATERIALIZED VIEW CONCURRENTLY conference_stats;"

# 10. Final snapshot
pg_dump quantumdb | gzip > snapshots/quantumdb_complete_$(date +%Y%m%d).sql.gz
```

## Data Quality

### Name Normalization

Both tools use `quantumdb::utils::normalize::normalize_name()` for consistency:

```rust
// Normalizes "François Müller" → "francois muller"
let normalized = normalize_name(raw_name);

// Find existing author
let author = query!("SELECT id FROM authors WHERE normalized_name = $1", normalized)
    .fetch_optional(&pool)
    .await?;
```

### Deduplication

- **Authors**: Matched by normalized name, creates new only if no match
- **Committee Roles**: `ON CONFLICT DO NOTHING` for idempotency
- **Publications**: Unique `canonical_key` prevents duplicates

### Source Tracking

All imported data includes metadata JSONB:

```json
{
  "source_type": "archive_org",
  "source_url": "https://web.archive.org/...",
  "scraped_date": "2025-12-30",
  "notes": "Parsed from committee page"
}
```

This allows:
- Data provenance tracking
- Re-scraping from original sources
- Quality assessment
- Debugging

## Troubleshooting

### Scraper finds no data

```bash
# Check archive URLs are set
psql quantumdb -c "SELECT venue, year, archive_pc_url FROM conferences WHERE archive_pc_url IS NOT NULL;"

# Test URL manually
curl -L "https://web.archive.org/web/20240315/qip2024.tw/pc"

# Enable debug logging
RUST_LOG=debug cargo run -p scrape_committees -- --venue QIP --year 2024 --dry-run
```

### Duplicate authors created

```bash
# Find potential duplicates
psql quantumdb -c "
SELECT normalized_name, COUNT(*), array_agg(full_name)
FROM authors
GROUP BY normalized_name
HAVING COUNT(*) > 1;
"

# Manually merge and add name variants
```

### Connection errors

```bash
# Check database is running
docker compose ps

# Verify DATABASE_URL
echo $DATABASE_URL

# Test connection
psql $DATABASE_URL -c "SELECT 1;"
```

## Performance Tips

### Bulk Imports

For large datasets:

1. Use transactions (already implemented in scrapers)
2. Batch inserts (100-1000 rows per transaction)
3. Disable triggers temporarily (if needed)
4. Refresh materialized views AFTER bulk import, not during

### Parallel Scraping

Currently sequential. Future enhancement:

```bash
# Scrape different venues in parallel
cargo run -p scrape_committees -- --venue QIP &
cargo run -p scrape_committees -- --venue QCRYPT &
cargo run -p scrape_committees -- --venue TQC &
wait
```

## Next Steps

1. **Implement HotCRP importer** - Parse JSON, import publications/authorships
2. **Conference-specific parsers** - Better accuracy for each venue's HTML structure
3. **Manual review UI** - Flag ambiguous entries for human verification
4. **Automated scheduling** - Cron jobs to re-scrape periodically
5. **Data validation** - Sanity checks and quality metrics
