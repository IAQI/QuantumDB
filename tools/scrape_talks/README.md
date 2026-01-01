# Talks Scraper - Invited & Tutorial Talks

Scrapes invited talks, tutorial talks, and keynotes from conference program/schedule pages. Uses a **CSV file workflow** for manual verification before importing into the database.

## Quick Start

### 1. Scrape to CSV File

```bash
# Scrape from local HTML file (recommended for development)
./scrape_to_csv.py --venue QCRYPT --year 2024 --local

# Scrape from web
./scrape_to_csv.py --venue QCRYPT --year 2024

# Custom output directory
./scrape_to_csv.py --venue QCRYPT --year 2024 --local --output-dir ./my_data

# Overwrite existing file
./scrape_to_csv.py --venue QCRYPT --year 2024 --local --force
```

Output: `scraped_data/qcrypt_2024_talks.csv`

### 2. Review and Edit CSV File

```bash
# View the CSV file
cat scraped_data/qcrypt_2024_talks.csv

# Edit manually if needed
code scraped_data/qcrypt_2024_talks.csv
# or use Excel, Numbers, LibreOffice, etc.
```

The CSV format:
```csv
venue,year,paper_type,title,speakers,authors,affiliations,abstract,arxiv_ids,presentation_url,video_url,youtube_id,session_name,award,notes
QCRYPT,2024,invited,"Quantum Networks","Alice Quantum","Alice Quantum","MIT","Abstract here...","2401.12345",,,,"Invited Talks",,
QCRYPT,2024,tutorial,"Intro to QKD","Bob Crypto;Charlie Keys","Bob Crypto;Charlie Keys","Caltech;Oxford","Tutorial abstract","2312.99999",https://slides.com/...,,,"Tutorial Session",,
```

**Note**: Lists (speakers, authors, affiliations, arxiv_ids) are semicolon-separated.

### 3. Import to Database

```bash
# Dry run first to see what would be imported
./import_from_csv.py scraped_data/qcrypt_2024_talks.csv --dry-run

# Actually import
./import_from_csv.py scraped_data/qcrypt_2024_talks.csv
```

## Architecture

### Modular Scrapers

Each conference type has its own scraper module in `scrapers/`:

- **`scrapers/base.py`** - Base scraper class with common functionality
- **`scrapers/qcrypt.py`** - QCrypt scraper (works for schedule pages from qcrypt.iaqi.org)
- **`scrapers/qip.py`** - QIP scraper (needs customization per year)
- **`scrapers/tqc.py`** - TQC scraper (needs customization per year)

### CSV Workflow

1. **Scrape** → Data goes into local CSV file
2. **Review** → Manually verify/fix data in spreadsheet editor
3. **Import** → Script creates/matches authors and creates publications + authorships

This allows you to:
- Fix parsing errors before they hit the database
- Handle name variants and affiliations manually
- Add missing metadata (arXiv IDs, video links, etc.)
- Skip invalid/duplicate entries
- Keep a record of the raw scraped data

## CSV Schema

### Field Details

- **venue**: QCRYPT, QIP, or TQC (uppercase)
- **year**: Conference year (integer)
- **paper_type**: invited, tutorial, or keynote (lowercase)
- **title**: Talk/paper title
- **speakers**: Semicolon-separated speaker names (e.g., "Alice;Bob")
- **authors**: Semicolon-separated author names (optional, defaults to speakers if empty)
- **affiliations**: Semicolon-separated affiliations matching author/speaker order
- **abstract**: Talk abstract (optional)
- **arxiv_ids**: Semicolon-separated arXiv IDs (e.g., "2401.12345;2312.54321") (optional)
- **presentation_url**: URL to slides/presentation (optional)
- **video_url**: URL to video recording (optional)
- **youtube_id**: YouTube video ID extracted from video_url (optional)
- **session_name**: Session/track name from schedule (optional)
- **award**: Award information if applicable (optional)
- **notes**: Any parsing notes or source URL (optional)

### Required Fields

Only these fields are required:
- venue
- year
- paper_type
- title

All other fields are optional and can be left empty.

### List Field Format

Fields that contain lists use semicolons as separators:
- `speakers`: "Alice Quantum;Bob Crypto"
- `authors`: "Alice Quantum;Bob Crypto;Charlie Keys"
- `affiliations`: "MIT;Caltech;Oxford"  (must match order of authors/speakers)
- `arxiv_ids`: "2401.12345;2312.54321"

## Customizing Scrapers

Different conferences (and different years of the same conference) often have different HTML structures. To customize:

### 1. Download Local HTML

```bash
cd ~/Web
wget -r -np -k https://qcrypt.iaqi.org/2024/schedule/index.html
```

### 2. Inspect Structure

Open the HTML file and identify:
- How sessions are organized (headings, divs, articles)
- How invited/tutorial talks are marked
- Where speaker names and affiliations appear
- How abstracts, arXiv links, video links are included

### 3. Update Scraper

Edit the appropriate scraper in `scrapers/` (e.g., `qcrypt.py`) and refine the `parse_talk_data()` method:

```python
def parse_talk_data(self) -> List[Dict[str, Any]]:
    talks = []
    # Your parsing logic here
    # Look for invited/tutorial sessions
    # Extract title, speakers, abstract, links
    return talks
```

### 4. Test

```bash
./scrape_to_csv.py --venue QCRYPT --year 2024 --local --force
cat scraped_data/qcrypt_2024_talks.csv
```

Iterate until the scraper accurately extracts the data.

## Database Import

The import script (`import_from_csv.py`):

1. **Reads CSV** and groups talks by paper_type
2. **Generates canonical_key** for each talk (format: `{VENUE}{YEAR}-{paper_type}-{index}`)
3. **Finds or creates conference** by venue and year
4. **Parses semicolon-separated lists** (speakers, authors, affiliations, arXiv IDs)
5. **Creates/updates publication** record in database
6. **For each author**:
   - Normalizes name
   - Searches for existing author (including name variants)
   - Creates new author if not found
   - Updates affiliation if provided
7. **Creates authorships** linking authors to publication with position
8. **Adds source metadata** (JSONB) tracking CSV file, scrape date, etc.

## Verification Queries

After importing, verify data quality:

```sql
-- Count talks by type per conference
SELECT c.venue, c.year, p.paper_type, COUNT(*) as count
FROM publications p
JOIN conferences c ON p.conference_id = c.id
WHERE p.paper_type IN ('invited', 'tutorial', 'keynote')
GROUP BY c.venue, c.year, p.paper_type
ORDER BY c.year DESC, c.venue;

-- View imported talks with authors
SELECT p.title, p.paper_type,
       array_agg(a.full_name ORDER BY au.author_position) as authors
FROM publications p
JOIN conferences c ON p.conference_id = c.id
JOIN authorships au ON p.id = au.publication_id
JOIN authors a ON au.author_id = a.id
WHERE c.venue = 'QCRYPT' AND c.year = 2024
  AND p.paper_type IN ('invited', 'tutorial', 'keynote')
GROUP BY p.id, p.title, p.paper_type
ORDER BY p.paper_type, p.title;

-- Check for talks without authors (should be empty)
SELECT p.title, c.venue, c.year
FROM publications p
JOIN conferences c ON p.conference_id = c.id
LEFT JOIN authorships au ON p.id = au.publication_id
WHERE p.paper_type IN ('invited', 'tutorial', 'keynote')
  AND au.id IS NULL;

-- Verify canonical_key uniqueness (should be empty)
SELECT canonical_key, COUNT(*)
FROM publications
GROUP BY canonical_key
HAVING COUNT(*) > 1;
```

## Requirements

```bash
pip install -r requirements.txt
```

Required packages:
- `beautifulsoup4` - HTML parsing
- `requests` - HTTP fetching
- `asyncpg` - PostgreSQL async driver
- `python-dotenv` - Environment variables

## Database Setup

Ensure these tables exist (created by migrations):
- `conferences` - Conference metadata with archive URLs
- `publications` - Papers/talks with paper_type enum ('invited', 'tutorial', 'keynote', etc.)
- `authors` - Author records with name normalization
- `author_name_variants` - Alternative name spellings
- `authorships` - Links authors to publications

## Tips

- **Start with local files**: Faster iteration, no rate limiting, works offline
- **One conference at a time**: Easier to verify data quality
- **Check for duplicates**: Review canonical_keys to ensure uniqueness
- **Use dry-run**: Always test import before committing (`--dry-run`)
- **Manual cleanup**: CSV review step is crucial for data quality
- **Archive URLs**: Schedule pages from qcrypt.iaqi.org are more stable than live conference sites

## Differences from Committee Scraper

1. **Source pages**: Schedule/program pages instead of committee pages
2. **CSV schema**: Different fields (title, abstract, arXiv IDs vs committee_type, position)
3. **List fields**: Semicolon-separated for multiple speakers, authors, affiliations
4. **Database tables**: Creates publications + authorships instead of committee_roles
5. **canonical_key**: Unique identifier format {VENUE}{YEAR}-{paper_type}-{index}
6. **Metadata tracking**: Stored in publications.metadata and authorships.metadata JSONB fields

## Workflow Example

```bash
# 1. Scrape QCrypt 2024 talks
cd tools/scrape_talks
./scrape_to_csv.py --venue QCRYPT --year 2024 --local

# 2. Review output
cat scraped_data/qcrypt_2024_talks.csv
# Edit in your favorite editor to fix any issues

# 3. Test import
./import_from_csv.py scraped_data/qcrypt_2024_talks.csv --dry-run

# 4. Import to database
./import_from_csv.py scraped_data/qcrypt_2024_talks.csv

# 5. Verify in database
psql quantumdb -c "
SELECT p.title, p.paper_type, array_agg(a.full_name ORDER BY au.author_position) as authors
FROM publications p
JOIN conferences c ON p.conference_id = c.id
JOIN authorships au ON p.id = au.publication_id
JOIN authors a ON au.author_id = a.id
WHERE c.venue = 'QCRYPT' AND c.year = 2024
  AND p.paper_type IN ('invited', 'tutorial', 'keynote')
GROUP BY p.id, p.title, p.paper_type;
"
```

## Troubleshooting

**No talks found**:
- Check the HTML structure of the schedule page
- Update the scraper's `parse_talk_data()` method
- Try different heading patterns or CSS selectors

**Wrong data extracted**:
- Inspect the local HTML file to understand the structure
- Add logging in the scraper to see what's being matched
- Refine the parsing logic

**Duplicate authors created**:
- Name normalization handles most cases automatically
- Use `author_name_variants` table for known aliases
- Manual cleanup may be needed for complex name variations

**Import fails**:
- Check that conference exists in database first
- Verify CSV format (especially semicolon-separated lists)
- Use `--dry-run` to test before actual import
- Check database logs for specific error messages
