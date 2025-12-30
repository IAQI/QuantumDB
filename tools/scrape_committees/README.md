# Committee Scraper Tool

Scrapes committee membership data from archived conference websites and populates the QuantumDB database.

## Features

- Scrapes Program Committee (PC), Organizing Committee (OC), and Steering Committee (SC) data
- Uses archived URLs stored in the `conferences` table
- Extracts member names, affiliations, and positions
- Uses name normalization to find or create authors
- Records source provenance in JSONB metadata
- Supports dry-run mode for testing
- Idempotent - can be re-run safely with `--force`

## Usage

### Using Local Files (Recommended for Development)

If you have local copies of archived websites in `~/Web/`:

```bash
# Dry run with local files
cargo run -p scrape_committees -- --local --dry-run

# Scrape all conferences from local files
cargo run -p scrape_committees -- --local

# Scrape specific venue from local files
cargo run -p scrape_committees -- --local --venue QIP --year 2024

# Use custom local directory
cargo run -p scrape_committees -- --local --local-dir ~/my-web-archive
```

**Expected directory structure:**
```
~/Web/
├── web.archive.org/
│   └── web/
│       └── 20230515120000/
│           └── https:/
│               └── 2024.qipconference.org/
│                   └── committee/
│                       └── index.html
```

The tool automatically converts archive.org URLs to local file paths.

### Using Archive.org (Production)

```bash
# Dry run - preview what would be scraped
cargo run -p scrape_committees -- --dry-run

# Scrape all conferences with archive URLs
cargo run -p scrape_committees

# Scrape specific venue
cargo run -p scrape_committees -- --venue QIP

# Scrape specific year
cargo run -p scrape_committees -- --year 2024

# Force re-scrape existing data
cargo run -p scrape_committees -- --force
```

### From tools directory

```bash
cd tools/scrape_committees
cargo run -- --venue QCRYPT --dry-run
```

## How It Works

1. **Query Database**: Finds conferences with `archive_pc_url`, `archive_organizers_url`, or `archive_steering_url` set
2. **Fetch HTML**: Downloads archived web pages using `reqwest`
3. **Parse Members**: Extracts committee members using HTML selectors
4. **Parse Details**: Attempts to extract:
   - Member name (cleaned of titles like Dr., Prof.)
   - Affiliation (from parentheses or comma-separated)
   - Position (chair, co_chair, area_chair, member)
   - Role title (e.g., "General Chair", "Program Chair")
5. **Name Normalization**: Uses `quantumdb::utils::normalize::normalize_name()` for matching
6. **Find or Create Authors**: Looks up existing authors by normalized name, creates new ones if needed
7. **Insert Committee Roles**: Batch inserts with transaction, including metadata:
   ```json
   {
     "source_type": "archive_org",
     "source_url": "https://web.archive.org/...",
     "scraped_date": "2025-12-30",
     "original_text": "Alice Quantum (MIT)"
   }
   ```

## Architecture

### Generic Parser

The current implementation uses a **generic HTML parser** that works across different conference website structures:

- Tries multiple CSS selectors: `ul li`, `ol li`, `.committee-member`, `table tr`, etc.
- Looks for common patterns: "Name (Affiliation)" or "Name, Affiliation"
- Detects positions from keywords: "General Chair", "Co-Chair", "Area Chair"
- Deduplicates by normalized name

### Future: Conference-Specific Parsers

For better accuracy, implement scrapers in `src/scrapers/`:

```
src/
├── main.rs
└── scrapers/
    ├── mod.rs
    ├── qip.rs       # QIP-specific parsing logic
    ├── qcrypt.rs    # QCrypt-specific parsing logic
    └── tqc.rs       # TQC-specific parsing logic
```

Each scraper would know the specific HTML structure of that conference's archived sites.

## Database Schema

Inserts into `committee_roles` table:

```sql
CREATE TABLE committee_roles (
    conference_id   UUID REFERENCES conferences(id),
    author_id       UUID REFERENCES authors(id),
    committee       committee_type,  -- OC, PC, SC, Local
    position        committee_position,  -- chair, co_chair, area_chair, member
    role_title      TEXT,  -- e.g., "General Chair"
    affiliation     TEXT,  -- Affiliation at time of service
    metadata        JSONB, -- Source tracking
    ...
);
```

## Error Handling

- **Connection errors**: Retries with exponential backoff (future)
- **Parse errors**: Logs warning and continues with next URL
- **Duplicate keys**: Uses `ON CONFLICT DO NOTHING` for idempotency
- **Transaction failures**: Rolls back entire conference, logs error

## Logging

Uses `tracing` for structured logging:

```bash
# Enable debug logging
RUST_LOG=debug cargo run --bin scrape_committees

# Log only scraper messages
RUST_LOG=scrape_committees=info cargo run --bin scrape_committees
```

## Testing

```bash
# Test with dry-run
cargo run --bin scrape_committees -- --venue QIP --year 2024 --dry-run

# Verify results in database
psql quantumdb -c "SELECT * FROM committee_roles WHERE conference_id IN (SELECT id FROM conferences WHERE venue='QIP' AND year=2024);"
```

## Limitations

### Current Generic Parser

- **Pattern matching**: May miss members in unusual HTML structures
- **Affiliation extraction**: Simple regex, may be inaccurate
- **Position detection**: Keyword-based, may miss nuanced roles
- **Deduplication**: By normalized name only, doesn't handle name variants

### Future Improvements

1. **Conference-specific parsers**: Better accuracy for each conference's HTML structure
2. **Retry logic**: Handle temporary network failures
3. **Progress tracking**: Store scrape status per conference
4. **Parallel scraping**: Scrape multiple conferences concurrently
5. **Better affiliation parsing**: Machine learning or NLP for entity extraction
6. **Manual review**: Flag ambiguous entries for human verification
7. **Incremental updates**: Only scrape new conferences since last run

## Troubleshooting

### No members found
- Check that archive URLs are valid and accessible
- Try scraping manually with curl: `curl <url>`
- Enable debug logging to see HTML structure: `RUST_LOG=debug`

### Wrong affiliations
- Generic parser uses simple pattern matching
- Consider implementing conference-specific parser
- Manually correct in database and add to `author_name_variants`

### Duplicate authors
- Name normalization may not catch all variants
- Check `authors` table for similar names
- Manually merge duplicates and add name variants

## Integration with QuantumDB

The scraper reuses QuantumDB library code:

```rust
use quantumdb::utils::normalize::normalize_name;
```

This ensures consistency between:
- Committee scraper name matching
- Author search in API
- Name variant generation
- Publication authorship matching

## Local File Benefits

- **10-100x faster** than fetching from archive.org
- **No rate limiting** concerns
- **Reproducible** scraping during development
- **Offline** development capability
- **Consistent** results without network variability

## Next Steps

1. Add archive URLs to conferences table
2. Download archived pages to `~/Web/`
3. Run scraper with `--local --dry-run` to test parsing
4. Implement venue-specific parsers for better accuracy
5. Run scraper with `--local` to populate database
