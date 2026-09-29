# TODO

Quick scratchpad of pending work. Add items freely; move done items out.

## Data

- [x] **Merge duplicate author: "Alex Bredariol Grilo" vs "Alex B. Grilo"** —
  done in the author-anomaly cleanup pass, along with 55 other fuzzy-duplicate
  groups (full middle name / initial / name-particle variants) via
  `tools/one_off/merge_fuzzy_authors.py`.
- [x] **Re-run author-anomaly check after the big author influx (~8.6k authors)**
  (2026-07-02). `merge_fuzzy_authors.py` surfaced 53 new groups: 47 clean fuzzy
  merges appended to `data/author_aliases.csv`; 5 doubled-name scraping artifacts
  (`Cecilia Lancien Lancien`, `Myungshik Kim Kim`, `Nike Dattani Dattani`,
  `Mizanur Mizanur Rahaman`, `Subhendu Bikash Ghosh ×2`) + the `Marco Tlúio`→`Túlio`
  typo fixed at source in the poster CSVs; `Subhendu B. Ghosh`→`Subhendu Bikash Ghosh`
  added as the residual alias. Left un-merged for a human call: `Francesco/Antonio
  Anna Mele` (suspicious "Anna" expansion), `Adnan A.E./Adil Hajomer`, and the
  `Luis Felipe/Paulo/Luís Santos` group (likely ≥2 distinct people).
- [x] **Fix ALL-CAPS / affiliation-in-name poster authors** (2026-07-03). The
  poster scrapers leaked affiliations into author names (`Xin Wang (The Hong Kong
  University of Science and Technology (Guangzhou)`) and passed through shouted
  ALL-CAPS / all-lower-case names (`YANGYANG FEI`, `yicheng shi`). Fixed in the
  parsers, not by hand-editing the (overwrite-wholesale) poster CSVs: added
  `clean_display_name()` in `_lib.py` (honorific strip + smart re-casing, keeping
  initials/particles) used by `posters/parsers.py` and `qcrypt_json_to_csv.py`;
  made `_strip_trailing_paren` nested/unbalanced-paren aware; added top-level-only
  author splitting (so an affiliation's own " and "/"," no longer shatters it);
  added source-doubled-name collapse (`Nike Dattani Dattani`→`Nike Dattani`);
  rewrote `parse_qip_2016` to anchor author+title on the paper `<a>`. Re-scraped
  the affected poster CSVs from the local `~/Web` mirrors + repaired 2 corrupt
  records in `qcrypt_2024/raw/posters-2024.json` and 1 `workshop.csv` speaker.
  99 corrupt author rows → 0 (one residual left: qip_2015 `M`, the ambiguous
  `M & P Horodecki` sibling shorthand). Live DB reflects this on the next
  reload-from-CSVs.
- [x] **Apply curated aliases at ingest** — `get_or_create_author` (now shared in
  `tools/scrapers/_lib.py`) resolves `data/author_aliases.csv` before the
  normalized-name lookup, so aliased spellings (surname changes, full-middle-name
  vs initial like "Jane Q. Doe" vs "Jane Quux Doe") no longer split on import.
  `dedup_authors.py` is therefore no longer needed on a fresh reload.
- [ ] **Auto-detect full-middle-name vs initial without an alias entry** — ingest
  resolution above covers pairs already listed in `author_aliases.csv`; a brand-new
  "Jane Quux Doe" with no alias and no prior "Jane Q. Doe" row still can't be linked
  by `normalize_name` alone. Optionally teach `normalize_name` / the matching query
  a middle-name↔initial rule so these collapse automatically (lower priority now
  that the alias path prevents the common cases).

## Import pipeline

- [x] **TQC `canonical_key` collision: proceedings clobbered by workshop** — fixed
  2026-09-28. `proceedings.csv` rows are keyed `{VENUE}{YEAR}-proc-{type}-{n}` and the
  importer now writes `is_proceedings_track`. Before the fix the DB held only
  max(proceedings, workshop) regular talks per TQC year (76 talks missing across 2009–2025) and
  no row was flagged as proceedings. Papers listed in both files (2017: 6, 2019: 8,
  2020: 11, 2021: 10, 2024: 12, 2025: 10) were merged into the proceedings row.
  **Needs a from-scratch rebuild** (existing rows keep their old keys).

## Schema / data model

- [x] **Merge `local_organizing` and `organizing` committee types** — done.
  Collapsed everything to `organizing` (CSV) → `OC` (enum); local/national/
  international nuance preserved per-row in `role_title`. All `committees.csv`
  merged, importer `map_committee_type` keeps `local_organizing` as a legacy
  alias → `OC`, and the `Local` rendering path was dropped from the templates +
  `committee_full_name()`/`committee_order()`/`glyph_points()` in
  `src/handlers/web/authors.rs`. The `Local` enum value is left dormant in the
  DB type (no migration); a follow-up could drop it by recreating the enum.

## Frontend

- [x] **Co-chairs should render as chairs (filled) in the contribution graph** —
  fixed. Root cause confirmed: `map_position()` in the committees importer only
  keyed `'co-chair'` (hyphen), so the documented `'co_chair'` (underscore) form
  fell through to `member` — 33 co-chair rows were mis-stored (e.g. Eleni
  Diamanti, QCrypt 2025). `map_position()` now normalises `-`→`_` before mapping,
  the 14 stray hyphen rows in the CSVs were normalised to `co_chair`, and a
  committee re-import corrected the DB (co_chair 14 → 47).
