# Implementation Plan: Talks vs Publications Schema Enhancement

## Overview

Extend QuantumDB's publications schema to properly distinguish between talks and publications, with support for:
- Presenter tracking (who gave the talk vs who authored)
- Enhanced talk types (regular, plenary, plenary_short, plenary_long)
- Proceedings track distinction (TQC has both proceedings and workshop tracks)
- Talk scheduling (date, time, duration)

## User Requirements Summary

1. **Presenter tracking**: Optional field to designate which author gave the talk (often unknown for contributed talks, may be inferred from video/slides)
2. **Talk type granularity**:
   - Add `plenary`, `plenary_short`, `plenary_long` to existing paper_type enum
   - **REMOVE `short` from enum** - duration tracking replaces this
   - Keep existing: regular, poster, invited, tutorial, keynote
   - Use `regular` for both historical single-track conferences and modern parallel sessions
   - Use `plenary` types only for modern parallel-track era prestigious talks
   - These represent what appears in the conference program, not selection mechanism
3. **Proceedings tracking**: Boolean flag for TQC's dual-track system (proceedings vs workshop)
4. **Talk scheduling**: Add optional fields for when talks occur
   - `talk_date` (DATE) - Day of the talk
   - `talk_time` (TIME) - Start time of the talk
   - `duration_minutes` (INTEGER) - Duration in minutes

## Implementation Steps

### 1. Database Migration (NEW FILE)

**Create**: [migrations/20260101000000_add_talk_presenter_and_types.sql](migrations/20260101000000_add_talk_presenter_and_types.sql)

- **REMOVE `short` value from `paper_type` enum** (existing value, needs removal)
- Extend `paper_type` enum with `plenary`, `plenary_short`, `plenary_long` values
- Add `presenter_author_id UUID` column (nullable FK to authors, ON DELETE SET NULL)
- Add `is_proceedings_track BOOLEAN` column (NOT NULL DEFAULT FALSE)
- Add `talk_date DATE` column (nullable)
- Add `talk_time TIME` column (nullable)
- Add `duration_minutes INTEGER` column (nullable, CHECK >= 0)
- Create partial index on `presenter_author_id` (WHERE NOT NULL)
- Add trigger `ensure_presenter_is_author` to validate presenter is in authorships table
- Update table comments for documentation

**Key SQL snippets**:
```sql
-- Remove 'short' from enum (requires recreation due to PostgreSQL limitation)
-- This will be handled carefully to preserve existing data

ALTER TYPE paper_type ADD VALUE 'plenary';
ALTER TYPE paper_type ADD VALUE 'plenary_short';
ALTER TYPE paper_type ADD VALUE 'plenary_long';

ALTER TABLE publications
ADD COLUMN presenter_author_id UUID REFERENCES authors(id) ON DELETE SET NULL,
ADD COLUMN is_proceedings_track BOOLEAN NOT NULL DEFAULT FALSE,
ADD COLUMN talk_date DATE,
ADD COLUMN talk_time TIME,
ADD COLUMN duration_minutes INTEGER CHECK (duration_minutes >= 0);

CREATE TRIGGER ensure_presenter_is_author
    BEFORE INSERT OR UPDATE ON publications
    FOR EACH ROW
    EXECUTE FUNCTION validate_presenter_is_author();
```

### 2. Model Updates

**Modify**: [src/models/publication.rs](src/models/publication.rs)

- **REMOVE `Short` variant from `PaperType` enum** (lines 14-15)
- Add 3 new enum variants to `PaperType`:
  - `Plenary` (plenary talk as listed in program)
  - `PlenaryShort` (short plenary, e.g., at QIP)
  - `PlenaryLong` (long plenary, e.g., at QIP)
- Add fields to `Publication` struct:
  - `presenter_author_id: Option<Uuid>`
  - `is_proceedings_track: bool`
  - `talk_date: Option<NaiveDate>`
  - `talk_time: Option<NaiveTime>`
  - `duration_minutes: Option<i32>`
- Add same fields to `CreatePublication` and `UpdatePublication`
- Add OpenAPI schema descriptions for new fields
- Import `chrono::NaiveTime` at top of file

### 3. Handler Updates

**Modify**: [src/handlers/publications.rs](src/handlers/publications.rs)

- Update ALL SQL queries to include new fields:
  - `list_publications()` - add to SELECT (3 queries: search, conference filter, all)
  - `get_publication()` - add to SELECT
  - `create_publication()` - add to INSERT and RETURNING
  - `update_publication()` - add to UPDATE and RETURNING (fetch + update queries)
  - `delete_publication()` - no changes needed
- Add default values:
  - `is_proceedings_track` defaults to `false` if not provided
- Note: Presenter validation handled by database trigger (will raise error if invalid)

**Query pattern example**:
```rust
RETURNING
    id, conference_id, canonical_key, doi,
    COALESCE(arxiv_ids, ARRAY[]::text[]) as "arxiv_ids!",
    title, abstract as "abstract_text",
    paper_type as "paper_type: PaperType",
    pages, session_name, presentation_url, video_url, youtube_id,
    award, award_date, published_date,
    presenter_author_id, is_proceedings_track,  -- NEW FIELDS
    talk_date, talk_time, duration_minutes,     -- NEW SCHEDULING FIELDS
    created_at, updated_at
```

### 4. Documentation Updates

**Modify**: [DATABASE_SCHEMA.md](DATABASE_SCHEMA.md)

- **Remove `short` from paper_type enum documentation**
- Update publications section with new enum values (plenary, plenary_short, plenary_long)
- Document `presenter_author_id`, `is_proceedings_track`, `talk_date`, `talk_time`, `duration_minutes` columns
- Add "Paper Type Guide" explaining the different talk types as they appear in conference programs
  - Clarify `regular` usage for historical single-track and modern non-plenary talks
  - Clarify `plenary` types only for modern parallel-track era
- Add "Presenter vs Authors" section explaining the distinction
- Add "Proceedings Track" section explaining TQC's dual-track system
- Add "Talk Scheduling" section explaining date/time/duration fields

**Modify**: [CLAUDE.md](CLAUDE.md)

- Add "Paper Types" section to Critical Implementation Details listing all types
  - **Exclude `short` from the list** - document that it was removed
  - Document `regular` usage convention (historical + modern non-plenary)
  - Document `plenary` types usage (modern parallel-track era only)
- Add "Presenter Tracking" section explaining validation
- Add "Proceedings vs Workshop Tracks" section
- Add "Talk Scheduling" section explaining date/time/duration fields
- Update existing documentation as needed

### 5. Testing

**Modify**: [tests/api_tests.rs](tests/api_tests.rs)

Add new test cases:
- `test_publication_with_presenter()` - Create publication, add authorships, set presenter, verify validation
- `test_new_paper_types()` - Test plenary/plenary_short/plenary_long serialization (ensure `short` is NOT accepted)
- `test_proceedings_track_flag()` - Test is_proceedings_track defaults and behavior
- `test_presenter_validation_trigger()` - Test database trigger prevents invalid presenter
- `test_talk_scheduling()` - Test talk_date, talk_time, duration_minutes fields

### 6. SQLx Offline Mode Preparation

After code changes, regenerate SQLx metadata:
```bash
# Ensure database running with new migration applied
sqlx migrate run

# Regenerate offline metadata
cargo sqlx prepare

# Commit .sqlx/ directory
git add .sqlx/
```

## Critical Files

1. **migrations/20260101000000_add_talk_presenter_and_types.sql** (NEW) - Database schema changes, remove `short`, add scheduling fields
2. **src/models/publication.rs** (MODIFY) - Remove `Short` from PaperType enum, add plenary types and scheduling fields
3. **src/handlers/publications.rs** (MODIFY) - Update all SQL queries with new fields
4. **DATABASE_SCHEMA.md** (MODIFY) - Update schema documentation, remove `short`, add scheduling
5. **CLAUDE.md** (MODIFY) - Update developer documentation
6. **tests/api_tests.rs** (MODIFY) - Add test coverage for new features

## Backward Compatibility

- All existing publications: `presenter_author_id` will be NULL (acceptable)
- All existing publications: `is_proceedings_track` will be FALSE (correct)
- All existing publications: `talk_date`, `talk_time`, `duration_minutes` will be NULL (acceptable)
- **BREAKING**: `short` paper_type removed - any existing data with `short` must be migrated
  - Migration strategy: Convert existing `short` records to `regular` before removing enum value
  - Check if any existing data uses `short` type before migration
- Existing other `paper_type` values remain valid (enum is extended)
- API: New fields are optional in requests, included in responses

## Data Integrity

- **Trigger validation**: Database trigger ensures presenter is an author
- **Cascade behavior**: ON DELETE SET NULL on presenter_author_id FK
- **Index optimization**: Partial index on non-NULL presenter_author_id values
- **Default values**: is_proceedings_track defaults to FALSE for safety
- **Duration constraint**: CHECK constraint ensures duration_minutes >= 0 if provided

## Deployment Order

1. **Check existing data**: Query database for any publications with `paper_type = 'short'`
2. **Migrate data if needed**: Convert any `short` records to `regular` before enum change
3. Apply database migration (`sqlx migrate run`) - removes `short`, adds new types and fields
4. Update Rust models (remove `Short`, add plenary types and scheduling fields)
5. Update handlers (all SQL queries with new fields)
6. Run `cargo sqlx prepare` to regenerate offline metadata
7. Run tests (`cargo test`)
8. Update documentation (DATABASE_SCHEMA.md, CLAUDE.md)
9. Build and deploy (`docker-compose up --build`)

## Notes

- OpenAPI/Swagger docs update automatically via `#[derive(ToSchema)]`
- Scraper tools in `tools/scrape_talks/` already have `speakers` field that maps to presenter
- Paper types represent what appears in conference programs, not the selection mechanism
- TQC is currently the only venue with proceedings track; QIP/QCrypt are workshop-style only
- Selection mechanisms (e.g., SC-invited vs PC-reviewed) may evolve over time and are not explicitly tracked
- **`short` removal rationale**: Duration tracking (via `duration_minutes`) replaces the need for a `short` paper type. Historical short contributed talks will be marked as `regular` with appropriate duration values.
- **`regular` usage convention**: Use for both historical single-track conferences (even though all talks were technically plenary format) and modern parallel-session contributed talks. Use `plenary` types only for prestigious talks in the modern parallel-track era.
- **Presenter field is optional**: For contributed talks, the actual speaker is often unknown and can be left NULL. May be inferred later from videos, slides, or other sources
- **Edge case - non-author presenter**: In rare cases where the presenter is not one of the authors, keep presenter_author_id NULL and store presenter information in the metadata JSONB field (e.g., `{"presenter_name": "John Doe", "presenter_note": "Presented on behalf of authors"}`). The validation trigger ensures data integrity for the common case while metadata handles exceptions
- **Talk scheduling fields**: All three scheduling fields (talk_date, talk_time, duration_minutes) are optional. Populate when data is available from conference programs or videos.
