# QIP Committee Data Sources

This document describes the source pages used to produce each `qip_YEAR_committees.csv` file.
All local archive paths are relative to `~/Web/qip.iaqi.org/`.

---

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
| Local Organizing | `2019/local.html` |
| Program | `2019/about.html` (section `#pc`) |
| Steering | `2019/about.html` (section `#steering`) |

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
