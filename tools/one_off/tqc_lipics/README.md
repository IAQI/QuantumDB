# TQC LIPIcs Proceedings Fetcher

Fetches the proceedings track of TQC from [LIPIcs (Dagstuhl)](https://drops.dagstuhl.de/entities/conference/TQC).

LIPIcs is the formal publication venue for the TQC proceedings track. Workshop-track talks are *not* in LIPIcs — they need to be scraped from each year's conference website (see [`scrape_tqc_talks_historical.py`](../scrape_tqc_talks_historical.py)).

## Coverage

TQC publishes proceedings on LIPIcs from **2013 onwards** (volumes 22 through 350). Pre-2013 TQC editions had no formal LIPIcs proceedings.

| Year | LIPIcs volume | Papers (excl. front matter) |
|------|---------------|------------------------------|
| 2013 | 22  | 22 |
| 2014 | 27  | 18 |
| 2015 | 44  | 16 |
| 2016 | 61  | 9  |
| 2017 | 73  | 10 |
| 2018 | 111 | 10 |
| 2019 | 135 | 10 |
| 2020 | 158 | 12 |
| 2021 | 197 | 10 |
| 2022 | 232 | 12 |
| 2023 | 266 | 14 |
| 2024 | 310 | 12 |
| 2025 | 350 | 12 |

## Usage

```bash
# Fetch a single year (uses ./cache/ if present)
python3 fetch_lipics_proceedings.py --year 2023

# Fetch all years 2013–2025
python3 fetch_lipics_proceedings.py --all --force

# Bypass cache (re-download all HTML)
python3 fetch_lipics_proceedings.py --all --no-cache --force
```

## Output

CSV files are written to `../scraped_data/tqc_{year}_proceedings_talks.csv` with the same schema as the workshop CSVs but every row has `is_proceedings_track=TRUE`. Each row also includes:

- `presentation_url` — the LIPIcs PDF URL
- `notes` — DOI plus a "LIPIcs proceedings (Dagstuhl)" tag for traceability
- `session_name` — `Proceedings track (LIPIcs)`

## Cache

Raw HTML is cached at `./cache/tqc_{year}_volume_{volid}.html`. Delete the file (or pass `--no-cache`) to force a fresh fetch.

## Notes

- Authors are stored in LIPIcs as `Family, Given`; the script reverses this so the CSV uses the human-readable `Given Family` order.
- Front matter and the "Complete Volume" entry are filtered out automatically.
- arXiv IDs are not in the volume page metadata. Cross-referencing against [DBLP](https://dblp.org/db/conf/tqc/) or fetching individual paper detail pages can fill in `arxiv_ids` later.
- Affiliation data is not in LIPIcs metadata either — leave blank for now.
