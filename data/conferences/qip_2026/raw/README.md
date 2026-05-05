# QIP 2026 raw artifacts

Source files used to produce `../talks.csv` (canonical) for QIP 2026.

- `qip2026-data.json` — paper submission export from the program-committee
  system.
- `qip_2026_schedule.html` — HTML snapshot of the conference schedule page.
- `papers_compact.csv` — intermediate, JSON-flattened paper list before
  schedule enrichment.
- `papers_manual_review.txt` — items flagged during scraping for human review.
- `tutorials.csv` — tutorial sessions extracted separately.

Conversion scripts live at `tools/scrape_talks/qip2026/`.
