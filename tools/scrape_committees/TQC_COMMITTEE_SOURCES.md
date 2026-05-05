# TQC Committee Data Sources

This document describes the source pages used to produce each `tqc_YEAR_committees.csv`
file. All local archive paths are relative to `~/Web/tqc.iaqi.org/`.

Scraper: [scrape_tqc_historical.py](scrape_tqc_historical.py).

---

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

---

## 2023 — Aveiro (Universidade de Aveiro)

| Committee | Archive URL |
|-----------|-------------|
| All (combined) | `2025/tqc2023/index.html` |

Combined retro-archive at the 2025 IAQI site. Headings: "Steering Committee",
"Local Organising Committee" (with `[host]` and `[chair, contact person]`
markers), "Programme Committee".

Scraper: `parse_2023()`.

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

## 2014 — Singapore (CQT/NUS)

| Committee | Archive URL |
|-----------|-------------|
| All (combined) | `web.archive.org/web/20190902000118/http:/tqc.quantumlah.org/committees.php.html` |

Web-archive snapshot from 2019. Plain HTML with `<h3>Section</h3><p>Name1<br>Name2<br>...</p>`. Chair markers use `<b>(chair)</b>`. The parser stops at "Contacts Details:" to avoid scraping the address footer.

Scraper: `parse_2014()`.

---

## 2015 — Brussels (ULB)

| Committee | Archive URL |
|-----------|-------------|
| All (combined) | `2015/committees.html` |

Plain HTML. `<h2>` headings followed by `<ul>`. Chair markers use
`(<strong>chair</strong>)` inline at the end of each member line.

Scraper: `parse_2015()`.

---

## Years with no parser

| Year | Reason |
|------|--------|
| 2024 | covered above (combined archive at `2025/tqc-2024/`) |
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

## Conventions

- `committee_type` values: `program`, `steering`, `local_organizing`, `organizing`.
- `position` values: `chair`, `co_chair`, `member`.
- `role_title` values: `Chair`, `Co-Chair`, `Program Chair`, `Steering Chair`,
  `Local Chair`, `General Chair`, `Publicity Chair` (or empty for plain members).
- The `organizing` committee_type is used for international/national organisers
  that are not part of the local organising committee (e.g. TQC 2025's
  "National organisers" and "International organisers").

## Output schema

CSV columns: `venue,year,committee_type,position,full_name,affiliation,role_title`.
Same shape as QIP and QCrypt committee CSVs, ready for
[`import_from_csv.py`](import_from_csv.py).
