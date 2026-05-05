# TQC 2023-24 BibTeX to CSV Conversion

This directory contains tools for converting TQC 2023 and 2024 talk data from BibTeX format to CSV format for import into QuantumDB.

## Source Data

- **Input**: `tqc-publications-23-24.bib` - BibTeX file containing TQC 2023 and 2024 publications
  - 92 Talk entries (TQC 2024)
  - 14 Conference entries (TQC 2023 - proceedings track)
  - 59 Workshop entries (TQC 2023 - workshop track)
  - 723 Poster entries (excluded from conversion)
- **Input**: Google Calendar ICS feed - **Complete** TQC 2023 scheduling information
  - Downloaded from: `https://calendar.google.com/calendar/ical/8vggdde35g9dplrr2r9fqcjink@group.calendar.google.com/public/basic.ics`
  - 113 total events from TQC 2023 (July 24-28, 2023)
  - 79 actual talk events after filtering (keynotes, workshops, proceedings talks with A/B parallel tracks)
  - Contains speaker names and arXiv IDs in summaries/descriptions
  - **Successfully covers all 73 talks from BibTeX** - 100% match rate!
  - Note: The 6 extra calendar talks (79 vs 73 from BibTeX) may be tutorials, keynotes, or other presentations not in the proceedings/workshop data

## Conversion Script

### `convert_tqc_to_csv.py` - Unified BibTeX and Calendar Converter

**All-in-one script** that handles the complete conversion workflow:

**Features:**
1. **BibTeX Parsing**
   - Extracts Talk, Conference, and Workshop entries (excludes Posters)
   - Parses all BibTeX fields (title, authors, year, URL, abstract, keywords)
   - Cleans LaTeX formatting from titles and abstracts
   - Extracts arXiv IDs from URLs

2. **Calendar Integration**
   - Downloads fresh calendar data from Google Calendar ICS feed
   - Uses `icalendar` library for robust parsing
   - Extracts event date/time, speaker names, arXiv IDs
   - Filters out non-talk events (posters, sessions, social events)
   - Handles both TQC 2023 and TQC 2024 automatically

3. **Smart Matching**
   - Matches calendar events to BibTeX talks using arXiv IDs and title similarity
   - Merges schedule information (date, time, speakers) into talk records
   - Handles multiple calendar formats:
     - TQC 2023: "A) Speaker Name - Title"
     - TQC 2024: "A: Title | Speaker1, Speaker2, ..."
   - **TQC 2023**: 100% match rate (73/73 talks)
   - **TQC 2024**: 100% match rate (92/92 talks)

4. **Timezone Handling**
   - Converts UTC times to local conference time
   - TQC 2023 (Lisbon): UTC+1
   - TQC 2024 (Okinawa): UTC+9
   - All times displayed in local conference timezone

5. **CSV Output**
   - Outputs CSV files in standard format matching `import_from_csv.py`
   - Abstract column placed last to avoid cluttering review
   - Speaker field shows presenter (not all authors)
   - Ready for direct database import

**Requirements:**
```bash
pip3 install icalendar
```

**Usage:**
```bash
python3 convert_tqc_to_csv.py
```

**Output:**
- `../scraped_data/tqc_2023_talks_with_schedule.csv` (73 talks, 100% matched)
- `../scraped_data/tqc_2024_talks_with_schedule.csv` (92 talks, 100% matched)

## Output Files

CSV files are written to `../scraped_data/`:

- `tqc_2023_talks_with_schedule.csv` - **73 talks with complete schedule (100% match rate)**
  - 14 Conference entries (proceedings track - published in LIPIcs)
  - 59 Workshop entries (workshop track)
  - All talks matched with calendar date/time/speaker

- `tqc_2024_talks_with_schedule.csv` - **92 talks with complete schedule (100% match rate)**
  - 92 Talk entries (workshop-style conference)
  - All talks matched with calendar date/time/speaker

## CSV Format

**Standard columns** (matching `import_from_csv.py` format):
1. `venue` - Conference venue ("TQC")
2. `year` - Conference year (2023 or 2024)
3. `paper_type` - Paper type ("regular" for all TQC talks)
4. `title` - Talk title (LaTeX formatting cleaned)
5. `speakers` - Presenter name from calendar if matched, otherwise semicolon-separated authors from BibTeX
6. `authors` - Semicolon-separated list from BibTeX (all authors)
7. `affiliations` - Empty (not available from BibTeX)
8. `arxiv_ids` - arXiv ID if available
9. `session_name` - Day/track from BibTeX keywords (e.g., "Tuesday", "Proceedings")
10. `scheduled_date` - Talk date from calendar (YYYY-MM-DD) if matched
11. `scheduled_time` - Talk start time from calendar (HH:MM:SS) if matched
12. `duration_minutes` - Empty (not available)
13. `presentation_url` - Empty
14. `video_url` - Empty
15. `youtube_id` - Empty
16. `award` - Empty
17. `notes` - Entry type and proceedings track info

**Reference columns** (for traceability):
- `_entry_id` - BibTeX entry ID
- `_entry_type` - BibTeX entry type (Conference/Workshop/Talk)
- `_url` - Original URL from BibTeX
- `_howpublished` - Publication type from BibTeX

**Note:** `abstract` - Placed last to avoid cluttering CSV review

## Statistics

### TQC 2023 (73 talks)

- **Entry types**:
  - Conference (proceedings track): 14 talks
  - Workshop (workshop track): 59 talks
- Note: TQC 2023 had both a proceedings track (published in LIPIcs) and a workshop track

### TQC 2024 (92 talks)

- **All Talk entries** (workshop-style conference)
- **With arXiv IDs**: 54 talks (58.7%)
- **Without arXiv IDs**: 38 talks (41.3%)
- **Day distribution**: Tuesday (23), Thursday (23), Monday (17), Wednesday (12), Friday (6)
- **Proceedings tracks**: 11 talks marked with "Proceedings" in keywords

### Total

- **165 talks** across TQC 2023 and TQC 2024
- **723 poster entries** (not included in CSV output)

## Import to Database

After generating the CSV files, import them into QuantumDB:

```bash
cd /Users/chris/Github/QuantumDB/tools/scrape_talks

# Import TQC 2023 (73 talks, 100% matched with schedule)
python3 import_from_csv.py scraped_data/tqc_2023_talks_with_schedule.csv

# Import TQC 2024 (92 talks, 100% matched with schedule)
python3 import_from_csv.py scraped_data/tqc_2024_talks_with_schedule.csv
```

**Post-import steps:**

Set the `is_proceedings_track` flag:
- TQC 2023: Conference entries (`_entry_type = 'Conference'`) → `is_proceedings_track = TRUE`
- TQC 2023: Workshop entries (`_entry_type = 'Workshop'`) → `is_proceedings_track = FALSE`
- TQC 2024: All Talk entries → `is_proceedings_track = FALSE`
  - Check talks with "Proceedings" in `session_name` for possible proceedings track publications

## Field Interpretation

### entry_type
- **Talk**: Standard talk entry (TQC 2024)
- **Conference**: Proceedings track talk (TQC 2023, published in LIPIcs)
- **Workshop**: Workshop track talk (TQC 2023, not in proceedings)

### keywords
- **TQC 2024**: Day of week (Monday, Tuesday, Wednesday, Thursday, Friday) and sometimes "Proceedings"
- **TQC 2023**: Generally empty for Conference/Workshop entries

### howpublished
- **TQC 2023**: Often contains "Talk and Proceedings" for Conference entries
- **TQC 2024**: Generally empty

For database import:
- Use `entry_type` to determine `is_proceedings_track`: Conference → TRUE, Workshop/Talk → FALSE (unless "Proceedings" in keywords)
- Use `keywords` to infer `talk_date` if the conference program has date-to-day mappings
- Set `paper_type = 'regular'` for all talks
