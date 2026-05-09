# Committee Data Sources

This document describes the source pages used to produce each `committees.csv`
file under `data/conferences/`. Local archive paths for QIP are relative to
`~/Web/qip.iaqi.org/`; for TQC they are relative to `~/Web/tqc.iaqi.org/`.

QCrypt committee provenance is not yet captured here; see
`tools/scrapers/committees/qcrypt.py` for the current source URLs.

---

# QIP

Scraper: `tools/one_off/historical/scrape_qip_historical.py` (archived;
data already populated). The modular replacement is
`tools/scrapers/committees/qip.py`.

## 2026 — Riga (University of Latvia)

| Committee | Archive URL |
|-----------|-------------|
| Local Organizing | `2026/about/local-organizing-team/` |
| Program | `2026/about/programme-committee/` |
| Steering | `2026/about/steering-committee/` |

Scraper: `scrapers/qip.py` (QIPScraper, fetches programme-committee page)

---

## 2024 — Taipei (NTU/CYCU/NCKU/NSYSU/NYCU/NTHU)

| Committee | Archive URL |
|-----------|-------------|
| Local Organizing | `2024/site/mypage.aspx?pid=239&lang=en&sid=1522.html` |
| Program | `2024/site/mypage.aspx?pid=254&lang=en&sid=1522.html` |
| Steering | `2024/site/mypage.aspx?pid=238&lang=en&sid=1522.html` |

Scraper: `scrape_qip_historical.py` → `parse_2024()` (reads multiple `site/mypage.aspx?pid=*` files)

---

## 2023 — Ghent (UGhent)

| Committee | Archive URL |
|-----------|-------------|
| Local Organizing | `2023/event/13076/page/3879-local-organising-committee.html` |
| Program | `2023/event/13076/page/3880-program-committee.html` |
| Steering | `2023/event/13076/page/3885-steering-committee.html` |

Scraper: `scrape_qip_historical.py` → `parse_2023()` (reads three separate Indico pages)

---

## 2022 — Pasadena (Caltech)

No local archive copy. Committee data was collected manually.
Source: `qip_2022_committees.csv` — steering committee list (manually compiled).

---

## 2021 — Munich / Virtual (TU Munich)

| Committee | Archive URL |
|-----------|-------------|
| Local Organizing | `2021/qip2021/program/committees/` |
| Program | `2021/qip2021/program/committees/` |
| Steering | `2021/qip2021/program/committees/` |

All committees on a single page.
Scraper: `scrape_qip_historical.py` → `parse_2021()`

---

## 2020 — Shenzhen (SUSTech / Peng Cheng Laboratory)

Local archive is a JavaScript SPA (`index.html` with bundled JS only); no committee data is readable from HTML.
Committee data was likely collected from the live website or program book.
Source: `qip_2020_committees.csv` — program committee list.

---

## 2019 — Boulder (CU Boulder)

| Committee | Archive URL |
|-----------|-------------|
| Local Organizing | `2019/program.html#local` |
| Program | `2019/program.html#pc` (section `#pc`) |
| Steering | `2019/program.html#steering` (section `#steering`) |

Source: `qip_2019_committees.csv` — local organizing + program committee.

---

## 2018 — Delft (TU Delft)

| Committee | Archive URL |
|-----------|-------------|
| All (combined) | `2018/qutech.nl/qip2018/aboutqip/index.html` |

Scraper: `scrape_qip_historical.py` → `parse_2018()` (single page listing all committees)

---

## 2017 — Seattle (MSR)

| Committee | Archive URL |
|-----------|-------------|
| All (combined) | `2017/index.html` |

Archive is a single-page Angular/React app; all content including committees is embedded in `index.html`.
Scraper: `scrape_qip_historical.py` → `parse_2017()`

---

## 2016 — Banff (UCalgary)

| Committee | Archive URL |
|-----------|-------------|
| All (combined) | `2016/committees.html` |

Scraper: `scrape_qip_historical.py` → `parse_2016()`

---

## 2015 — Sydney (UTS)

| Committee | Archive URL |
|-----------|-------------|
| All (combined) | `2015/Committees.php.html` |

Scraper: `scrape_qip_historical.py` → `parse_2015()`

---

## 2014 — Barcelona (UB/UAB/ICFO)

| Committee | Archive URL |
|-----------|-------------|
| All (combined) | `2014/cgi-bin/committees.pl.html` |

Scraper: `scrape_qip_historical.py` → `parse_2014()`

---

## 2013 — Beijing (Tsinghua University)

| Committee | Archive URL |
|-----------|-------------|
| All (combined) | `2013/index.html@p=8.html` |

Note: The archive captures the PHP query parameter as part of the filename (`?p=8` → `@p=8`).
Scraper: `scrape_qip_historical.py` → `parse_2013()`

---

## 2012 — Montreal (UdeM)

| Committee | Archive URL |
|-----------|-------------|
| All (combined) | `2012/committee_e.php.html` |

English-language version; French version also archived as `committee_f.php.html`.
Scraper: `scrape_qip_historical.py` → `parse_2012()`

---

## 2011 — Singapore (NUS)

| Committee | Archive URL |
|-----------|-------------|
| All (combined) | `2011/committees/index.html` |

Scraper: `scrape_qip_historical.py` → `parse_2011()`

---

## 2010 — Zurich (ETHZ)

| Committee | Archive URL |
|-----------|-------------|
| All (combined) | `2010/committee.html` |

Scraper: `scrape_qip_historical.py` → `parse_2010()` *(if implemented; else manual)*

---

## 2009 — Santa Fe (UNM/SFI/LANL)

| Committee | Archive URL |
|-----------|-------------|
| All (combined) | `2009/organizing-committees.html` |

Scraper: `scrape_qip_historical.py` → `parse_2009()`

---

## 2008 — New Delhi (IIT/TIFR)

| Committee | Archive URL |
|-----------|-------------|
| All (combined) | `2008/index.html` |

Main index page contains PC, local organizers, and steering committee sections.
Encoding: latin-1.
Scraper: `scrape_qip_historical.py` → `parse_2008()`

---

## 2007 — Brisbane (UQ)

| Committee | Archive URL |
|-----------|-------------|
| All (combined) | `2007/index.htm` |

Committees embedded in the main homepage.

---

## 2006 — Paris (University Paris-Sud)

| Committee | Archive URL |
|-----------|-------------|
| All (combined) | `2006/index.html` |

Committees embedded in the main homepage.

---

## 2005 — Cambridge, MA (MIT)

No committee page identified in the local archive. No CSV produced from archive.

---

## 2004 — Waterloo (PI/IQC)

No committee page identified in the local archive. No CSV produced from archive.

---

## 2003 — Berkeley (MSRI)

No local archive available.

---

## 2002 — Yorktown Heights (IBM)

| Committee | Archive URL |
|-----------|-------------|
| Local Organizing | `2002/index.html` |

Only local organizers listed (Charles Bennett, David DiVincenzo). No PC/SC page archived.
Scraper: `scrape_qip_historical.py` → `parse_2002()` (hardcoded from index.html)

---

## 2001 — Amsterdam (CWI)

| Committee | Archive URL |
|-----------|-------------|
| Local Organizing | `2001/index.html` |

Only local organizers listed (Harry Buhrman, Hein Röhrig, Ronald de Wolf). No PC/SC page archived.
Scraper: `scrape_qip_historical.py` → `parse_2001()` (hardcoded from index.html)

---

## 2000 — Montreal (CRM)

| Committee | Archive URL |
|-----------|-------------|
| Local Organizing | `2000/index.html` |

Only organizers listed. No PC/SC page archived.
Scraper: `scrape_qip_historical.py` → `parse_2000()`

---

## 1999 — Chicago / Evanston (DePaul University)

| Committee | Archive URL |
|-----------|-------------|
| Local Organizing + PC | `1999/theme.htm` |

Organizers and program committee both on theme.htm (AQIP'99 site).
Scraper: `scrape_qip_historical.py` → `parse_1999()`

---

## 1998 — Aarhus (AU / BRICS)

| Committee | Archive URL |
|-----------|-------------|
| Local Organizing + PC | `1998/prog.html` |

Both local organizers and PC chair listed on the same page.
Scraper: `scrape_qip_historical.py` (no `parse_1998` function; data collected separately)

---

## Notes

- **Combined pages**: Years 2006–2018 (except 2019) use a single committee page for OC/PC/SC; all three `archive_*_url` fields in the database point to the same URL.
- **2022, 2020**: No usable local archive. Data was collected from external sources and entered manually.
- **2005, 2004, 2003**: No committee data available in the local archive.
- **Encoding quirks**: 2008 archive uses latin-1 encoding. 2013 uses PHP query params encoded as `@p=N` in filenames.

---

# TQC

Scraper: `tools/one_off/historical/scrape_tqc_historical.py` (archived;
data already populated). The modular replacement is
`tools/scrapers/committees/tqc.py`.
All local archive paths are relative to `~/Web/tqc.iaqi.org/`.

## 2025 — Bengaluru (IISc)

| Committee | Archive URL |
|-----------|-------------|
| All (combined) | `2025/people/index.html` |

WordPress layout. Uses `<h2/h3 class="wp-block-heading">` headings followed by
`<ul class="wp-block-list">`. Organising committee is split across three
`<p><strong>` sub-headers (Local organisers in Bengaluru / National organisers
/ International organisers); the parser maps the latter two to
`committee_type=organizing`.

Scraper: `parse_2025()`.

---

## 2024 — Okinawa (OIST)

| Committee | Archive URL |
|-----------|-------------|
| All (combined) | `2025/tqc-2024/index.html` |

Combined retro-archive at the 2025 IAQI site. Headings: "Steering Committee
of TQC 2024", "Programme Committee of TQC 2024", "Organising Committee of TQC
2024" (with sub-paragraphs "Local organizers in Okinawa", "International
organizers").

Scraper: `parse_2024()`.

**Talks** (`workshop.csv`, 92 rows): produced by
`tools/one_off/tqc2023-24/convert_tqc_to_csv.py` from
`raw/tqc-publications-23-24.bib` + `raw/tqc-calendar.ics`. 100% calendar
match; all rows have schedule + speakers. 91/92 have abstracts; 54/92
have arXiv IDs. The 12 talks also published in LIPIcs are in
`proceedings.csv` separately (with `is_proceedings_track=TRUE`).

---

## 2023 — Aveiro (Universidade de Aveiro)

| Committee | Archive URL |
|-----------|-------------|
| All (combined) | `2025/tqc2023/index.html` |

Combined retro-archive at the 2025 IAQI site. Headings: "Steering Committee",
"Local Organising Committee" (with `[host]` and `[chair, contact person]`
markers), "Programme Committee".

Scraper: `parse_2023()`.

**Talks** (`workshop.csv`, 59 rows): produced by
`tools/one_off/tqc2023-24/convert_tqc_to_csv.py` from
`raw/talks_with_schedule.csv` (filtered to `_entry_type=Workshop`). 100%
calendar match; all rows have schedule + speakers + abstracts. 14
proceedings-track talks (`_entry_type=Conference`) are in `proceedings.csv`
separately.

---

## 2022 — Illinois (UIUC)

| Committee | Archive URL |
|-----------|-------------|
| All (combined) | `2022/people/index.html` |

WordPress site at `tqc2022-conference.iquist.illinois.edu`. Section headings
live inside `<p><strong>...</strong></p>` rather than real `<h2>` tags;
`parse_generic_wp(strong_paragraph=True)` handles this. PC-chair markers use
the format `(Affiliation – chair)` with an en-dash.

Scraper: `parse_2022()`.

---

## 2021 — Riga (virtual; University of Latvia)

| Committee | Archive URL |
|-----------|-------------|
| All (combined) | `2021/people/index.html` |

WordPress layout. Section headings inside `<p><strong>...</strong></p>`.

Scraper: `parse_2021()`.

---

## 2020 — Riga (virtual; University of Latvia)

| Committee | Archive URL |
|-----------|-------------|
| All (combined) | `2020/people/index.html` |

WordPress layout. Headings: "Program committee:", "Local organizing committee
(University of Latvia):", "Steering committee:".

Scraper: `parse_2020()`.

---

## 2019 — Maryland (UMD/QuICS)

| Committee | Archive URL |
|-----------|-------------|
| All (combined) | `2019/committees/index.html` |

WordPress layout. The local organising committee is labelled "Local committee"
(not "Local organizing committee") — the heading classifier accepts both.
Some LOC entries carry `[LC contact: ...]` brackets which the role-strip
regex removes.

Scraper: `parse_2019()`.

---

## 2017 — Paris (UPMC, LIP6)

| Committee | Archive URL |
|-----------|-------------|
| All (combined) | `2017/committees.html` |

Plain HTML. `<h2>` headings followed by `<ul class="committee">`. Chair
markers use the format ` - Chair` / ` - co-chair` (dash-separated) and
`(Affiliation) (PC Chair)`.

Scraper: `parse_2017()`.

---

## 2015 — Brussels (ULB)

| Committee | Archive URL |
|-----------|-------------|
| All (combined) | `2015/committees.html` |

Plain HTML. `<h2>` headings followed by `<ul>`. Chair markers use
`(<strong>chair</strong>)` inline at the end of each member line.

Scraper: `parse_2015()`.

---

## 2014 — Singapore (CQT/NUS)

| Committee | Archive URL |
|-----------|-------------|
| All (combined) | `web.archive.org/web/20190902000118/http:/tqc.quantumlah.org/committees.php.html` |

Web-archive snapshot from 2019. Plain HTML with `<h3>Section</h3><p>Name1<br>Name2<br>...</p>`. Chair markers use `<b>(chair)</b>`. The parser stops at "Contacts Details:" to avoid scraping the address footer.

Scraper: `parse_2014()`.

---

## TQC years with no parser

| Year | Reason |
|------|--------|
| 2018 | Sydney; archive has no committee page (only `accepted-talks/`). The conference's main site (`tqc2018.org`) is a Wix SPA with JS-rendered content — committee data needs to come from LIPIcs front matter or other sources. |
| 2016 | Berlin; no archive in `~/Web/tqc.iaqi.org/`. LIPIcs only. |
| 2013 | Guelph; no archive. LIPIcs only. |
| 2012 | Tokyo; no archive. LIPIcs only. |
| 2011 | Madrid; no archive. LIPIcs only. |
| 2010 | Leeds; no archive. LIPIcs only. |
| 2009 | Waterloo; no archive. LIPIcs only. |
| 2008 | Tokyo; archive only has `web.archive.org` snapshot of `index.html`. LIPIcs only. |
| 2007 | Nara; archive has only `index.html` (Phase 3 candidate). |
| 2006 | Kanagawa; archive has only `index.html` (Phase 3 candidate). |

---

## TQC conventions

- `committee_type` values: `program`, `steering`, `local_organizing`, `organizing`.
- `position` values: `chair`, `co_chair`, `member`.
- `role_title` values: `Chair`, `Co-Chair`, `Program Chair`, `Steering Chair`,
  `Local Chair`, `General Chair`, `Publicity Chair` (or empty for plain members).
- The `organizing` committee_type is used for international/national organisers
  that are not part of the local organising committee (e.g. TQC 2025's
  "National organisers" and "International organisers").

CSV columns: `venue,year,committee_type,position,full_name,affiliation,role_title`.
Same shape as QIP and QCrypt committee CSVs.
