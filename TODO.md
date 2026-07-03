# TODO

Quick scratchpad of pending work. Add items freely; move done items out.

## Data

- [x] **Merge duplicate author: "Alex Bredariol Grilo" vs "Alex B. Grilo"** —
  done in the author-anomaly cleanup pass, along with 55 other fuzzy-duplicate
  groups (full middle name / initial / name-particle variants) via
  `tools/one_off/merge_fuzzy_authors.py`.
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

- [x] **Merge `local_organizing` and `organizing` committee types** — done.
  Collapsed everything to `organizing` (CSV) → `OC` (enum); local/national/
  international nuance preserved per-row in `role_title`. All `committees.csv`
  merged, importer `map_committee_type` keeps `local_organizing` as a legacy
  alias → `OC`, and the `Local` rendering path was dropped from the templates +
  `committee_full_name()`/`committee_order()`/`glyph_points()` in
  `src/handlers/web/authors.rs`. The `Local` enum value is left dormant in the
  DB type (no migration); a follow-up could drop it by recreating the enum.

## Frontend

- [ ] **Co-chairs should render as chairs (filled) in the contribution graph** —
  `is_leadership()` in `src/handlers/web/authors.rs` already includes
  `co_chair`, so the likely culprit is the data: check whether co-chair rows
  are stored as `member`. Suspect `map_position()` in the committees importer —
  it maps `'co-chair'` (hyphen) but not `'co_chair'` (underscore), so any CSV
  using the underscore form silently falls through to `member`.
