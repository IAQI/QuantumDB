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
- [ ] **Improve author dedup matching for full-middle-name vs initial** — the
  one-off merge above cleaned existing rows, but the *importers* still match only
  on exact `normalized_name` (`tools/scrapers/.../get_or_create_author`), so new
  imports can re-introduce "Jane Q. Doe" vs "Jane Quux Doe" splits. Fold this
  into the matching query (and/or `src/utils/normalize.rs`) so it's prevented at
  ingest, then the one-off tool becomes unnecessary.

## Import pipeline

- [ ] **TQC `canonical_key` collision: proceedings clobbered by workshop** —
  `generate_canonical_key()` is `{VENUE}{YEAR}-{paper_type}-{index}` with `index`
  reset per file (`tools/scrapers/talks/importer.py`). TQC has both
  `proceedings.csv` and `workshop.csv` with `paper_type=regular`, imported as
  separate files, so e.g. `TQC2025-regular-1` collides and workshop overwrites
  proceedings (TQC 2025 lands 90 pubs, not 102). Fix: namespace the key by track
  (e.g. include `is_proceedings_track` or the source filename) so both survive.
  Surfaced during the author-anomaly cleanup; out of scope there.

## Schema / data model

- [ ] **Consider merging `local_organizing` and `organizing` committee types** —
  review how the two are actually used across conferences first (many years
  only use one; the distinction is often blurry). If merging: touch the
  `committee` enum / CHECK constraint via a migration, the importer mapping in
  `tools/scrapers/committees/importer.py` (`map_committee_type`), and the
  committee-type rendering in the templates + `committee_full_name()` /
  `committee_order()` in `src/handlers/web/authors.rs`.

## Frontend

- [ ] **Co-chairs should render as chairs (filled) in the contribution graph** —
  `is_leadership()` in `src/handlers/web/authors.rs` already includes
  `co_chair`, so the likely culprit is the data: check whether co-chair rows
  are stored as `member`. Suspect `map_position()` in the committees importer —
  it maps `'co-chair'` (hyphen) but not `'co_chair'` (underscore), so any CSV
  using the underscore form silently falls through to `member`.
