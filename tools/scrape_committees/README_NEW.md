# Committee Scraper - Modular Version

Scrapes program committee and organizing committee data from conference websites. Uses a **local JSON file workflow** for manual verification before importing into the database.

## Quick Start

### 1. Scrape to JSON File

```bash
# Scrape from local HTML file (recommended)
./scrape_to_json.py --venue QCRYPT --year 2023 --local

# Scrape from web
./scrape_to_json.py --venue QCRYPT --year 2023

# Custom output directory
./scrape_to_json.py --venue QCRYPT --year 2023 --local --output-dir ./my_data

# Overwrite existing file
./scrape_to_json.py --venue QCRYPT --year 2023 --local --force
```

Output: `scraped_data/qcrypt_2023_committees.json`

### 2. Review and Edit JSON File

```bash
# View the JSON file
cat scraped_data/qcrypt_2023_committees.json | jq .

# Edit manually if needed
code scraped_data/qcrypt_2023_committees.json
```

The JSON format:
```json
{
  "venue": "QCRYPT",
  "year": 2023,
  "scraped_at": "2025-12-30T...",
  "member_count": 45,
  "members": [
    {
      "committee_type": "program",
      "position": "chair",
      "full_name": "Alice Smith",
      "affiliation": "MIT",
      "notes": null
    },
    ...
  ]
}
```

### 3. Import to Database

```bash
# Dry run first to see what would be imported
./import_from_json.py scraped_data/qcrypt_2023_committees.json --dry-run

# Actually import
./import_from_json.py scraped_data/qcrypt_2023_committees.json
```

## Architecture

### Modular Scrapers

Each conference type has its own scraper module in `scrapers/`:

- **`scrapers/base.py`** - Base scraper class with common functionality
- **`scrapers/qcrypt.py`** - QCrypt scraper (works well for 2016-2024)
- **`scrapers/qip.py`** - QIP scraper (needs customization per year)
- **`scrapers/tqc.py`** - TQC scraper (needs customization per year)

### Staging Table Workflow

1. **Scrape** → Data goes into local JSON file
2. **Review** → Manually verify/fix data in JSON editor
3. **Import** → Script creates/matches authors and creates committee roles

This allows you to:
- Fix parsing errors before they hit the database
- Handle name variants and affiliations manually
- Skip invalid/duplicate entries
- Keep a record of the raw scraped data
- Version control the JSON files if desired

## Customizing Scrapers

Different conferences (and different years of the same conference) often have different HTML structures. To customize:

### 1. Download Local HTML

```bash
cd ~/Web
wget -r -np -k https://2023.qcrypt.net/committees/
```

### 2. Inspect Structure

Open the HTML file and identify:
- How committee sections are marked (headings, class names)
- How member info is structured (lists, divs, etc.)
- Where names, affiliations, and roles appear

### 3. Update Scraper

Edit the appropriate scraper in `scrapers/` and implement `parse_committee_data()`:

```python
def parse_committee_data(self) -> List[Dict[str, str]]:
    members = []
    # Your parsing logic here
    return members
```

Each dict should have:
- `committee_type`: 'program', 'steering', or 'local_organizing'
- `position`: 'chair', 'co-chair', or 'member'
- `full_name`: Person's full name
- `affiliation`: University/organization (optional)
- `notes`: Any additional info (optional)

### 4. Test

```bash
python3 scrape_to_staging.py --venue QCRYPT --year 2023 --local --force
```

## Legacy Tool

The original `scrape_committees.py` script is still available for direct database insertion without staging. It's more complex and does everything in one pass. Use the new `scrape_to_staging.py` + `import_from_staging.py` workflow for better control.

## Requirements

```bash
pip install -r requirements.txt
```

Required packages:
- `asyncpg` - PostgreSQL async driver
- `beautifulsoup4` - HTML parsing
- `aiohttp` - Async HTTP (for web scraping)
- `python-dotenv` - Environment variables

## Database Setup

The staging table is created by migration `20251231000000_create_committee_staging_table.sql`. It includes:

- `committee_staging` - Main staging table
- `committee_staging_unverified` - View of unverified data
- `committee_staging_ready` - View of verified but not imported data

## Tips

- **Start with local files**: Faster iteration, no rate limiting
- **One conference at a time**: Easier to verify
- **Check for duplicates**: Name variants can create multiple authors
- **Use dry-run**: Always test import before committing
- **Mark incrementally**: Verify small batches of records at a time
