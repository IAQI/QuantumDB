# QuantumDB conference data

This directory holds the source-of-truth CSV files for every conference QuantumDB
tracks (QIP, QCrypt, TQC). The CSVs are produced by the scrapers under `tools/`
and then imported into the database. **If you spot a wrong author, missing
affiliation, or other data error, edit the CSV here and open a PR** — that is
the supported way to contribute corrections.

> [!IMPORTANT]
> We are particularly looking for the business-meeting slide decks — the annual reports presented by the local organizers and the PC chair at each conference's business meeting. These record participant counts, submission and acceptance numbers, and other figures we attach to each conference. If you have (or can point us to) any of these decks, please send them to quantumdb@iaqi.org — or open a pull request against the data directory.
>

## Layout

```
data/
  SOURCES.md                             # provenance per conference (which page each CSV came from)
  author_aliases.csv                     # curated name-change/identity merges (applied by tools/dedup_authors.py)
  conferences/
    qip_2024/
      committees.csv
      talks.csv
      posters.csv                        # accepted posters (paper_type=poster)
    qcrypt_2024/
      committees.csv
      talks.csv
      posters.csv
    tqc_2025/
      committees.csv
      proceedings.csv                    # TQC formal proceedings track (LIPIcs)
      workshop.csv                       # TQC workshop track
      posters.csv
    qip_2026/
      committees.csv
      talks.csv
      raw/                               # raw scraper inputs (json, html, .bib, .ics)
```

One folder per conference instance, named `<venue>_<year>` (lower-case venue).
TQC has both `proceedings.csv` and `workshop.csv` in years where both tracks
ran. `posters.csv`, when present, holds the accepted posters (same schema as
`talks.csv`, every row `paper_type=poster`); it is scraper-generated
(`scrape_to_csv.py posters`) and overwritten wholesale — fix the parser/source,
not the file. A `raw/` subfolder, when present, contains scraper inputs and
intermediate files — you usually don't need to touch these.

## CSV schemas

Lists inside cells are **semicolon-separated** (e.g. `Alice Quantum;Bob Crypto`).
Order in `affiliations` must match the order in `authors`.

### `committees.csv`

| Column          | Description                                                                              |
|-----------------|------------------------------------------------------------------------------------------|
| `venue`         | `QIP`, `QCRYPT`, or `TQC` (upper-case)                                                   |
| `year`          | Conference year                                                                          |
| `committee_type`| `program`, `steering`, or `organizing` (legacy `local_organizing` still imports, mapped to `organizing`) |
| `position`      | `chair`, `co_chair`, `area_chair`, or `member`                                           |
| `full_name`     | Member's full name                                                                       |
| `affiliation`   | Affiliation at time of service (optional)                                                |
| `role_title`    | Optional free-text label, **only when it adds detail beyond `committee_type` + `position`** (e.g. `Publicity Chair`, `Rump Session Organizer`, `Local Service`). Do **not** restate the position — labels that merely echo the committee/position (`Chair`, `Co-Chair`, `PC Member`, `LO Chair`, `Program Chair`, …) are dropped on import. |

### `talks.csv` (and `proceedings.csv` / `workshop.csv` for TQC, and `posters.csv`)

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

### `business_meeting.csv`

Stats announced at a conference's annual business meeting (registered
participants, submission/acceptance counts, etc.). Unlike the other CSVs, this
one is **tall**: one row per announced *fact*, so you can append just the facts
you have — each carrying its own provenance. Much of this data arrives ad-hoc by
email from past chairs, so per-fact `source_type` matters.

| Column        | Description                                                                 |
|---------------|-----------------------------------------------------------------------------|
| `venue`       | `QIP`, `QCRYPT`, or `TQC` (upper-case)                                       |
| `year`        | Conference year                                                             |
| `field`       | Which fact this row records (see vocabulary below)                          |
| `value`       | The value (integer, `YYYY-MM-DD`, percent, or JSON for `track_breakdown`)   |
| `source_type` | `slides`, `conference_website`, `email`, `manual`, … (provenance)           |
| `source_url`  | Where it came from — archive path, page, or deck (optional)                 |
| `source_date` | When it was sourced/announced (optional)                                    |
| `notes`       | Per-fact annotation (optional; folded into the row's narrative notes)       |

`field` vocabulary: `meeting_date`, `registered_participants`,
`onsite_participants`, `countries_represented`, `talk_submissions`,
`talks_accepted`, `posters_submitted`, `posters_accepted`, `acceptance_rate`,
`track_breakdown` (value is a JSON object — used for TQC's proceedings/workshop/
poster-only splits), and `notes` (general narrative). Unknown field names are
warned about on import and stashed in the row's `metadata.extra` (never dropped).

**Slide-deck links** use a `slide:<label>` field, where `value` is the full URL;
the label is shown as the link text on the conference page. There's usually a
PC-chair report and a local-organizers report, e.g.:

```
QCRYPT,2022,slide:PC chair report,https://qcrypt.iaqi.org/2022/slides/01_PC_Report.pdf,slides,,2022-08-31,
QCRYPT,2022,slide:local organizers report,https://qcrypt.iaqi.org/2022/slides/02_Local%20organizers%20report_business-meeting.pdf,slides,,2022-08-31,
```

Only `http(s)` URLs are rendered. Multiple `slide:` rows are kept in file order.

The importer pivots all rows for a conference into one
`conference_business_meetings` row and records per-fact provenance in
`metadata.sources`. Re-importing a file overwrites that conference's row from
the CSV, so keep all known facts for a conference in its file.

Prizes (best paper / best student paper) are **not** recorded here — they live on
the winning publication's `award` field in `talks.csv`.

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
./import_from_csv.py committees        ../../data/conferences/qip_2024/committees.csv      --dry-run
./import_from_csv.py talks             ../../data/conferences/qip_2024/talks.csv           --dry-run
./import_from_csv.py business-meetings ../../data/conferences/qcrypt_2022/business_meeting.csv --dry-run
```

The same directory holds the scrapers themselves — see
`tools/scrapers/README.md` for how to (re-)populate or refine the CSVs.
