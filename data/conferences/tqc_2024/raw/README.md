# TQC 2023-24 raw artifacts

Source files used to produce `../proceedings.csv` and `../workshop.csv` for
TQC 2024 (and TQC 2023, see `../../tqc_2023/raw/`).

- `tqc-publications-23-24.bib` — BibTeX export covering both TQC 2023 and
  TQC 2024 publications.
- `tqc-calendar.ics` — iCalendar export of the TQC 2024 schedule (used to
  enrich `talks_with_schedule.csv`).
- `talks_with_schedule.csv` — intermediate scraping output before splitting
  into proceedings / workshop tracks.

Conversion script lives at `tools/scrape_talks/tqc2023-24/convert_tqc_to_csv.py`.
