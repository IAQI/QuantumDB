# QuantumDB Project: Remaining Work & Recommendations

**Last Updated**: 2026-05-14

## Executive Summary

**Project Status**: Production-ready core; data population well underway.
- ✅ **Complete**: All core CRUD operations, opaque-token auth, rate limiting,
  CORS + security headers, input validation, pagination, web interface, test
  suite, OpenAPI/Swagger docs.
- 🟡 **In progress**: Data population — the database now holds ~66 conferences,
  ~3,700 publications, ~4,900 authors, and ~2,600 committee roles. Coverage is
  uneven per conference-year; the authoritative status table is in
  [`DATA_INGESTION_PLAN.md`](DATA_INGESTION_PLAN.md).
- 🔮 **Future**: Dedicated search endpoints, export features, analytics
  endpoints, production deployment.

**Where the live punch lists are:**
- **Data work** → [`docs/DATA_INGESTION_PLAN.md`](DATA_INGESTION_PLAN.md) is the
  authoritative working plan (per-conference inventory + per-gap method).
- **Day-to-day scratchpad** → [`TODO.md`](../TODO.md) at the repo root.
- This file is the **higher-level feature/roadmap** view.

---

## 1. Data Population

The CSV-based pipeline (`tools/scrapers/scrape_to_csv.py` →
`data/conferences/<venue>_<year>/*.csv` → `tools/scrapers/import_from_csv.py`)
is complete and in active use. See [`DATA_POPULATION.md`](../DATA_POPULATION.md)
for mechanics.

**Remaining data gaps** are tracked per conference-year in
`DATA_INGESTION_PLAN.md`. As of the last audit, the notable open items are:

- A handful of QIP years deferred pending external sources (e.g. 2020, 2022 —
  JS-rendered archives needing Wayback/DBLP fetches).
- QIP 2019 talks only partially extracted.
- TQC 2009/2010 committee + schedule gaps; some TQC workshop years lack
  schedule/video metadata.
- QCrypt 2025/2026 and QIP 2025 seeding/extraction as archives become available.
- YouTube enrichment (`video_url` / `youtube_id` / presenter inference) — a
  deferred, verification-heavy track; design captured in the ingestion plan.

Do **not** re-derive the gap list here — `DATA_INGESTION_PLAN.md` is kept
current and is the single source of truth.

---

## 2. User-Facing Features (Not Yet Built)

### A. Dedicated Search Endpoints ⭐⭐
Current state: list endpoints support some filtering; there are no dedicated
search endpoints, and the publications `search_vector` column is not yet
queried.
- `GET /api/v1/authors/search?q=<name>` — leverage `src/utils/normalize.rs`
- `GET /api/v1/publications/search?q=<title>` — PostgreSQL full-text via
  `search_vector` (column already exists and is `GENERATED ALWAYS`)
- `GET /api/v1/publications/search?arxiv_id=<id>` — arXiv lookup
- Files: `src/handlers/publications.rs`, `src/handlers/authors.rs`, `src/main.rs`

### B. Export Features ⭐⭐
- BibTeX: `GET /api/v1/publications/:id/bibtex`,
  `GET /api/v1/conferences/:slug/bibtex` (format varies by
  `is_proceedings_track`)
- CSV: author lists, per-conference paper lists
- Suggested new file: `src/utils/bibtex.rs`

### C. Analytics Endpoints ⭐
Three materialized views exist (`author_stats`, `conference_stats`,
`coauthor_pairs`) and the author detail page already renders a contribution
chart. Still missing: dedicated JSON analytics endpoints exposing the views
(top authors, conference trends, coauthor graph data).

### D. Author Management UI ⭐
The `author_name_variants` table exists but has no management UI. Useful:
duplicate detection (via `names_similar()`), author merge (fold authorships +
committee roles onto one record), variant editing. Partial duplicate cleanup is
currently a manual + `tools/dedup_authors.py` process — see `TODO.md`.

---

## 3. Operations & Deployment

### Production Deployment Checklist
- [ ] Choose hosting platform
- [ ] Production PostgreSQL instance
- [ ] Secure environment variable management
- [ ] SSL/TLS termination
- [ ] Tighten CORS origin list (currently `Any` — flagged in CLAUDE.md)
- [ ] Backup strategy (automated `pg_dump`)
- [ ] Monitoring (app logs, DB metrics)
- [ ] Document the deployment process

### Backup & Recovery
- Daily automated database dumps
- Archive all raw CSVs (already version-controlled under `data/conferences/`)
- Periodic restore tests

---

## 4. Code Quality

- **Open TODOs**: a small number remain in the scraper package and in some
  one-off converters under `tools/one_off/` — mostly "could fetch richer
  abstract/arXiv data" notes, best addressed opportunistically during data
  passes.
- **Test coverage gaps**: the integration suite bypasses the production
  middleware stack (auth, rate limiting, `/api/v1` routing) — see
  `TESTING.md`. No tests yet for the Python scrape/import pipeline.

---

## Recommended Next Steps

1. Continue closing data gaps per `DATA_INGESTION_PLAN.md`.
2. Add dedicated search endpoints (Feature A) — highest user-facing value, and
   the schema already supports full-text search.
3. BibTeX/CSV export (Feature B).
4. Analytics endpoints (Feature C).
5. Production deployment hardening (Section 3).

**Architecture is sound — no structural changes needed, just feature additions
and continued data population.**
