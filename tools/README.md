# QuantumDB Data Import Tools

This directory contains tools for importing conference data into QuantumDB.

## Directory Structure

- **`scrape_committees/`** - Committee member scrapers for all conferences
- **`scrape_talks/`** - Talk/paper scrapers for historical conferences
  - **`qip2026/`** - QIP 2026 data and processing tools (JSON, schedule, converters)

## Workflows

### Recent Conferences (with JSON from Program Committee)

For recent conferences like QIP 2026, where you have JSON data from the submission system:

1. **Convert JSON to CSV**:
   ```bash
   cd scrape_talks/qip2026
   python3 convert_json_to_csv.py qip2026-data.json ../scraped_data/qip_2026_papers.csv
   ```

2. **Download and parse schedule** (if available):
   ```bash
   # Download schedule HTML from conference website to qip2026/
   # Then enrich CSV with speaker and timing information:
   python3 parse_schedule.py \
     qip_2026_schedule.html \
     ../scraped_data/qip_2026_papers.csv \
     ../scraped_data/qip_2026_papers_final.csv
   ```

3. **Import to database**:
   ```bash
   cd ..
   ./import_from_csv.py scraped_data/qip_2026_papers_final.csv
   ```

### Historical Conferences (web scraping)

For older conferences, use the scrapers in `scrape_talks/scrapers/`:

1. **Scrape talks from web**:
   ```bash
   cd scrape_talks
   ./scrape_to_csv.py --venue QIP --year 2025
   ```

2. **Import to database**:
   ```bash
   ./import_from_csv.py scraped_data/qip_2025_talks.csv
   ```

### Committee Data (all conferences)

Committee scrapers work for both recent and historical conferences:

```bash
cd scrape_committees
./scrape_to_csv.py --venue QIP --year 2026
./import_from_csv.py scraped_data/qip_2026_committee.csv
```

## Notes

- **JSON workflow** is for conferences where you have access to program committee data exports
  - Store data and tools in subdirectories like `scrape_talks/qip2026/`
- **Scraping workflow** is for archived conferences with public web pages
- Both workflows produce CSV files that use the same import script
