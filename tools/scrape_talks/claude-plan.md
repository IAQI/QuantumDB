# Plan: Scrape QIP Historical Talk Data

## Context
QuantumDB needs talk/paper data for QIP conferences. Years 1998–2001, 2005–2007, and 2026 are already scraped. Local static HTML copies of all conference websites are at `~/Web/qip.iaqi.org/{year}/`. The committee scraper (`tools/scrape_committees/scrape_qip_historical.py`) provides the exact architecture to follow: year-specific `parse_YEAR()` functions, a `PARSERS` dispatch table, `save_csv()`, and a CLI.

## New File
**`tools/scrape_talks/scrape_qip_talks_historical.py`**

Also save this plan to **`tools/scrape_talks/claude-plan.md`** (first step).

## CSV Schema
Extended version of the existing historical format (e.g. `qip_2007_talks.csv`):
```
venue, year, paper_type, title, speaker, authors, affiliations, abstract,
arxiv_ids, presentation_url, video_url, session_name, award, notes,
scheduled_date, scheduled_time, duration_minutes
```
- `paper_type`: `regular`, `invited`, `tutorial`, `plenary`, `plenary_short`, `plenary_long`, `poster`
- `speaker`: single presenter name (underlined/bold author, if distinguishable)
- `authors`: full author list, semicolon-separated
- `arxiv_ids`: semicolon-separated arXiv IDs (e.g. `1001.0017`)
- `duration_minutes`: integer minutes (importer also accepts column name `duration`)

## Architecture (mirror `scrape_qip_historical.py`)

### Constants
```python
ARCHIVE_BASE = Path.home() / 'Web' / 'qip.iaqi.org'
OUTPUT_DIR = Path(__file__).parent / 'scraped_data'
```

### Helper functions
- `make_talk(**kwargs) -> Dict` — dict with all CSV fields (empty string defaults)
- `read_html(path, encoding='utf-8') -> BeautifulSoup` — identical to committee scraper
- `extract_arxiv_id(href_or_text: str) -> Optional[str]` — from `arxiv.org/abs/XXXX` URL or `arXiv: XXXX` text
- `parse_time_range(text: str) -> Tuple[str, int]` — `"09:30-10:20"` → `("09:30", 50)`
- `classify_type(text: str, duration: int = 0) -> str` — keyword → paper_type; default `"regular"`
- `join_authors(names: List[str]) -> str` — semicolon-join, strip whitespace
- `parse_name_affiliation(text: str)` — reuse from committee scraper (same pattern)

### PARSERS dispatch table
```python
PARSERS = {
    2002: parse_2002,
    2004: parse_2004,
    2008: parse_2008,
    2009: parse_2009,
    2010: parse_2010,
    2011: parse_2011,
    2012: parse_2012,
    2013: parse_2013,
    2014: parse_2014,
    2015: parse_2015,
    2016: parse_2016,
    2019: parse_2019,
}
```

---

## Year-Specific Parsers

### 2002 — `2002/Schedule.html`
- Table rows with time and event description; limited per-talk data
- Parse what's available; set `paper_type` from context (session name)
- Most entries will be sessions not individual talks — output what is identifiable

### 2004 — `2004/schedule.html` + `2004/abstracts.html`
- `schedule.html`: HTML tables; time range in first `<td>`; anchor link (e.g. `<a href="abstracts.html#Cleve">`) in second `<td>`
- `abstracts.html`: abstract per `<a name="Cleve">` anchor — contains title + abstract + full author list
- Strategy: build dict from abstracts.html keyed by anchor name; enrich with time from schedule.html
- Duration → type: ~45 min = `invited`, ≤15 min = `regular`
- Populate `scheduled_time`, `duration_minutes`, `abstract`

### 2008 — `2008/Program.html`
- `<h3>` section headers: "Invited Talks", "ten 30-minute talks", "twenty 20-minute talks"
- `<ul>/<ol><li>` per talk: `<em>` title, plain text authors
- Map header → `paper_type` + `duration_minutes` (no time slots)

### 2009 — `2009/talks.html`
- `<h2><b>Invited Talks</b></h2>` then `<ul><li>` entries
- Each `<li>`: speaker name, `<br>`, `<em>` title, `<br>`, abstract paragraph
- Contributed talks under `<p class="style4">` headings e.g. "TEN 30-MINUTE TALKS"
- Duration from heading → `duration_minutes`; type: invited vs regular
- Abstracts inline

### 2010 — `2010/programme.html`
- `<table class="timetable">` rows; day headers in `<h3>`/`<h2>`
- Row: first `<td>` = time range (HH:MM-HH:MM), second `<td>` = content
- Content: `<b>` speaker, `(plenary)` / `(featured)` parenthetical, `: <br> <i>` title
- arXiv ID from `href` with `arxiv.org/abs/`; `presentation_url` from "Lecture" link; `video_url` from "Watch"
- Co-authors after "(based on joint work with …)"
- `scheduled_time`, `duration_minutes` from time range

### 2011 — `2011/scientificprogramme/index.html`
- Identical structure to 2010; reuse same parsing logic

### 2012 — `2012/scientific_e.php.html`
- `<table border="1">` rows; `<h3>` day headers
- Row: first `<td>` = start time, second `<td>` = content
- Content: `<u>` presenter, `(Plenary lecture)` / `(Featured talk)` / `(contributed talk)`, `<br>`, `<a><i>` title
- arXiv and video links present
- `paper_type`: "Plenary lecture" → `plenary`; "Featured talk" → `invited`; "contributed" → `regular`

### 2013 — `2013/program.html`
- Table-based with session structure; arXiv links present
- Pattern similar to 2010–2012: time `<td>` + content `<td>`
- Extract arXiv IDs from `href` attributes

### 2014 — `2014/cgi-bin/program.pl.html`
- Numbered list: `<p><b>1a. Title</b><br>\nAuthor One, Author Two.</p>`
- Title inside `<b>` after stripping number prefix; authors in text node after `<br>`
- Merger info in `<i>merged with</i>` → `notes` field
- No time/type; all `paper_type = "regular"`

### 2015 — `2015/Program.php.html`
- Grid table; CSS class per cell: `tutorial`, `plenary`, `normal` (contributed), `break`
- Cell text: paper number + presenter last name (e.g. "5 Montanaro")
- `title` = placeholder `"[{number}] {name}"` (full titles not in this page)
- `paper_type` from CSS class; `scheduled_time` from row's `<td class="time">`

### 2016 — `2016/accepted-talks.html`
- Triple-nested `<ul><ul><ul><li>` entries
- Text pattern: `"Author One, Author Two and Author Three. Title of Talk"`
- Split: everything before first `. ` that follows a name = authors; rest = title (heuristic)
- Awards in `<span style="color: #0000ff;">` → `award` field
- Mergers in `<em>Merger of:</em>` → `notes` field
- All `paper_type = "regular"`; no time data

### 2019 — `2019/program.html` (partial)
- Invited talks: speaker name in `<h3>` or `<strong>`, affiliation nearby — no title in HTML
- Tutorial talks: `<span class="title">` (title) + speaker text nearby
- Contributed talks: PDF-only; skip with `notes = "see qip2019_talk_schedule.pdf"`
- Output only invited + tutorial rows

---

## Not Tractable
| Year | Reason |
|------|--------|
| 2003 | No local archive |
| 2017 | Angular/React SPA |
| 2018 | Indico JS-rendered |
| 2020 | React SPA shell only |
| 2021 | Indico React SPA (day pages JS-rendered) |
| 2022 | No local archive |
| 2023 | Indico React SPA |
| 2024 | Custom system, needs investigation |

---

## Critical Files
- **New**: `tools/scrape_talks/scrape_qip_talks_historical.py`
- **New**: `tools/scrape_talks/claude-plan.md` (copy of this plan)
- **Reference**: `tools/scrape_committees/scrape_qip_historical.py`
- **Reference**: `tools/scrape_talks/scraped_data/qip_2007_talks.csv` (schema)
- **Archive**: `~/Web/qip.iaqi.org/{year}/`

## Verification
```bash
python tools/scrape_talks/scrape_qip_talks_historical.py --year 2012
python tools/scrape_talks/scrape_qip_talks_historical.py --all
head -5 tools/scrape_talks/scraped_data/qip_2012_talks.csv
wc -l tools/scrape_talks/scraped_data/qip_*_talks.csv
```
Validate: correct headers, non-empty titles, sensible paper_type values, arXiv IDs where expected (2010–2013).
