# QuantumDB conference data

This directory holds the source-of-truth CSV files for every conference QuantumDB
tracks (QIP, QCrypt, TQC). The CSVs are produced by the scrapers under `tools/`
and then imported into the database. **If you spot a wrong author, missing
affiliation, or other data error, edit the CSV here and open a PR** — that is
the supported way to contribute corrections.

## Layout

```
data/
  SOURCES.md                             # provenance per conference (which page each CSV came from)
  conferences/
    qip_2024/
      committees.csv
      talks.csv
    qcrypt_2024/
      committees.csv
      talks.csv
    tqc_2025/
      committees.csv
      proceedings.csv                    # TQC formal proceedings track (LIPIcs)
      workshop.csv                       # TQC workshop track
    qip_2026/
      committees.csv
      talks.csv
      raw/                               # raw scraper inputs (json, html, .bib, .ics)
```

One folder per conference instance, named `<venue>_<year>` (lower-case venue).
TQC has both `proceedings.csv` and `workshop.csv` in years where both tracks
ran. A `raw/` subfolder, when present, contains scraper inputs and intermediate
files — you usually don't need to touch these.

## CSV schemas

Lists inside cells are **semicolon-separated** (e.g. `Alice Quantum;Bob Crypto`).
Order in `affiliations` must match the order in `authors`.

### `committees.csv`

| Column          | Description                                                                              |
|-----------------|------------------------------------------------------------------------------------------|
| `venue`         | `QIP`, `QCRYPT`, or `TQC` (upper-case)                                                   |
| `year`          | Conference year                                                                          |
| `committee_type`| `program`, `steering`, `local_organizing`, or `organizing`                                |
| `position`      | `chair`, `co_chair`, or `member`                                                          |
| `full_name`     | Member's full name                                                                       |
| `affiliation`   | Affiliation at time of service (optional)                                                |
| `role_title`    | Free-text label such as `General Chair`, `Program Chair`, `Publicity Chair` (optional)    |

### `talks.csv` (and `proceedings.csv` / `workshop.csv` for TQC)

| Column             | Description                                                                              |
|--------------------|------------------------------------------------------------------------------------------|
| `venue`            | `QIP`, `QCRYPT`, or `TQC` (upper-case)                                                   |
| `year`             | Conference year                                                                          |
| `paper_type`       | `regular`, `poster`, `invited`, `tutorial`, `keynote`, `plenary`, `plenary_short`, `plenary_long` |
| `title`            | Paper / talk title                                                                       |
| `speakers`         | `;`-separated speaker names (who actually presented)                                     |
| `authors`          | `;`-separated author names (defaults to `speakers` when empty)                           |
| `affiliations`     | `;`-separated affiliations matching the order of `authors`                               |
| `abstract`         | Abstract text (optional)                                                                 |
| `arxiv_ids`        | `;`-separated arXiv IDs                                                                  |
| `presentation_url` | URL to slides (optional)                                                                 |
| `video_url`        | URL to video recording (optional)                                                        |
| `youtube_id`       | YouTube video ID extracted from `video_url` (optional)                                   |
| `session_name`     | Session / track name from the schedule (optional)                                        |
| `award`            | Award information if applicable (optional)                                               |
| `notes`            | Parsing notes or source URL (optional)                                                   |
| `scheduled_date`   | Date the talk was given, `YYYY-MM-DD` (optional)                                         |
| `scheduled_time`   | Start time, `HH:MM` (optional)                                                           |
| `duration_minutes` | Talk duration in minutes (optional)                                                      |

Only `venue`, `year`, `paper_type`, and `title` are required; everything else
may be empty.

## How to submit a fix

1. Edit the CSV in your favourite editor (VS Code, Excel, Numbers, LibreOffice).
   Keep the column order intact and use `;` for list fields.
2. Open a PR. A reviewer will run the import script against your changes and
   merge once the database round-trips cleanly.
3. For larger reorganisations or new years, add a note to `SOURCES.md` so the
   next contributor can find the upstream page.

## Where the importer lives

The scrape + import tooling lives at `tools/scrapers/`. To dry-run an
import locally (against the dockerised dev DB):

```bash
cd tools/scrapers
./import_from_csv.py committees ../../data/conferences/qip_2024/committees.csv --dry-run
./import_from_csv.py talks      ../../data/conferences/qip_2024/talks.csv      --dry-run
```

The same directory holds the scrapers themselves — see
`tools/scrapers/README.md` for how to (re-)populate or refine the CSVs.
