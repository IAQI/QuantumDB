# Source Tracking and Affiliation for Committee Roles and Authorships

## Overview
Add simple source tracking to indicate where committee membership and authorship data came from, plus add point-in-time affiliation tracking for committee roles. Uses conference-level archive URLs with optional record-level metadata for additional details.

**User Requirements:**
- Conference-level granularity (leverage existing archive URLs)
- Support multiple source types: archived websites, proceedings, HotCRP files, manual entry
- Optional source information (not mandatory)
- Simple metadata: URL + description
- Track affiliation at committee role level (same as authorships already do)
- Keep authors.affiliation updated to most recent affiliation

## Implementation Strategy

### Approach: Two-Tier Source Tracking

1. **Primary**: Use existing conference archive URLs as default source
   - `archive_pc_url` → default for PC committee roles
   - `archive_organizers_url` → default for Local committee roles
   - `archive_steering_url` → default for SC committee roles
   - `archive_url` → default for OC committee roles
   - `archive_program_url` → default for authorships

2. **Override**: Add optional metadata JSONB field for record-specific details
   - Store source_type, source_url, source_description when needed
   - Only populate when source differs from conference default or needs clarification

### Metadata Schema Pattern

```json
{
  "source_type": "archive|proceedings|hotcrp|manual",
  "source_url": "optional-override-url",
  "source_description": "human-readable note",
  "source_date": "YYYY-MM-DD"
}
```

## Current State

**authorships table** already has:
- ✅ `affiliation TEXT` - Point-in-time affiliation (already exists)
- ❌ `metadata JSONB` - Need to add for source tracking

**committee_roles table** already has:
- ✅ `metadata JSONB` - Already exists for extensibility
- ❌ `affiliation TEXT` - Need to add for point-in-time affiliation

**authors table** already has:
- ✅ `affiliation TEXT` - Current/most recent affiliation (already exists)
- Logic needed: Update this when newer affiliations appear in committee_roles or authorships

## Implementation Tasks

### 1. Database Migrations

**File: migrations/20251230100000_add_affiliation_and_metadata.sql**
- Add `affiliation TEXT` to committee_roles table
- Add `metadata JSONB DEFAULT '{}'::jsonb` to authorships table
- Add GIN index on authorships.metadata for efficient JSONB queries
- Add column comments documenting usage

**File: migrations/20251230100001_add_source_tracking_comments.sql**
- Document source tracking pattern in committee_roles.metadata comment
- Document source tracking pattern in authorships.metadata comment
- Document affiliation tracking pattern in committee_roles.affiliation comment
- Link conference archive URLs to their intended use cases

### 2. Rust Model Updates

**File: src/models/committee.rs**
- Add `pub affiliation: Option<String>` to `CommitteeRole` struct (line ~47)
- Add `pub metadata: serde_json::Value` to `CommitteeRole` struct (line ~47)
- Add `pub affiliation: Option<String>` to `CreateCommitteeRole` struct (line ~61)
- Add `pub metadata: Option<serde_json::Value>` to `CreateCommitteeRole` struct (line ~61)
- Add `pub affiliation: Option<String>` to `UpdateCommitteeRole` struct (line ~72)
- Add `pub metadata: Option<serde_json::Value>` to `UpdateCommitteeRole` struct (line ~72)

**File: src/models/publication.rs**
- Add `pub metadata: serde_json::Value` to `Authorship` struct (~line 95)
- Add `pub metadata: Option<serde_json::Value>` to `CreateAuthorship` struct (~line 105)
- Add `pub metadata: Option<serde_json::Value>` to `UpdateAuthorship` struct (~line 115)

### 3. Handler SQL Query Updates

**File: src/handlers/committees.rs**
Updates needed in ~12 locations (add both `affiliation` and `metadata` to each):

- `list_committee_roles` (line ~91): Add `affiliation, metadata` to SELECT
- `list_committee_roles` (line ~115): Add `affiliation, metadata` to SELECT (author_id filter branch)
- `list_committee_roles` (line ~139): Add `affiliation, metadata` to SELECT (committee_type filter branch)
- `list_committee_roles` (line ~163): Add `affiliation, metadata` to SELECT (position filter branch)
- `list_committee_roles` (line ~187): Add `affiliation, metadata` to SELECT (else branch)
- `get_committee_role` (line ~210): Add `affiliation, metadata` to SELECT
- `create_committee_role` (line ~245): Add `affiliation, metadata` to INSERT columns and parameters
- `update_committee_role` (line ~285): Add `affiliation, metadata` to UPDATE SET clause
- `list_committee_roles_by_conference` (line ~320): Add `affiliation, metadata` to SELECT
- `list_committee_roles_by_author` (line ~350): Add `affiliation, metadata` to SELECT

**File: src/handlers/authorships.rs**
Updates needed in ~6 locations:

- `list_authorships` (line ~40): Add `metadata` to SELECT
- `list_authorships` (line ~60): Add `metadata` to SELECT (publication_id filter branch)
- `list_authorships` (line ~80): Add `metadata` to SELECT (author_id filter branch)
- `get_authorship` (line ~105): Add `metadata` to SELECT
- `create_authorship` (line ~135): Add `metadata` to INSERT columns and parameters
- `update_authorship` (line ~170): Add `metadata` to UPDATE SET clause

### 4. SQLx Offline Mode Update

After all query changes:
```bash
cargo sqlx prepare
```

This regenerates `.sqlx/query-*.json` files for Docker builds.

### 5. Author Affiliation Update Logic (Optional Enhancement)

When creating/updating committee_roles or authorships with affiliation data, optionally update authors.affiliation if the new data is more recent.

**Approach 1: Manual/Application-Level** (Recommended for now)
- Leave it to curators to update authors.affiliation manually via PUT /authors/{id}
- Simpler, more explicit, no automatic overwrites

**Approach 2: Database Trigger** (Future enhancement)
- Create trigger function to update authors.affiliation based on latest committee_role or authorship
- More complex, but keeps authors.affiliation automatically synchronized
- Requires determining "latest" (by conference year? by created_at?)

**Recommendation:** Start with Approach 1 (manual updates). Add trigger later if needed.

### 6. Testing

**Manual testing commands:**
```bash
# Create committee role with affiliation and source metadata
curl -X POST http://localhost:3000/committees \
  -H "Content-Type: application/json" \
  -d '{
    "conference_id": "uuid",
    "author_id": "uuid",
    "committee": "PC",
    "position": "member",
    "affiliation": "MIT CSAIL",
    "creator": "test",
    "modifier": "test",
    "metadata": {
      "source_type": "archive",
      "source_description": "Verified from program committee page"
    }
  }'

# Query returns affiliation and metadata fields
curl "http://localhost:3000/committees?conference_id=uuid"
```

**Automated tests:**
```bash
cargo test
RUST_LOG=debug cargo test
```

## Critical Files

**Database:**
- `migrations/20251230100000_add_affiliation_and_metadata.sql` - Add affiliation to committee_roles, metadata to authorships
- `migrations/20251230100001_add_source_tracking_comments.sql` - Document patterns

**Models:**
- `src/models/committee.rs` - Add affiliation + metadata fields to 3 structs
- `src/models/publication.rs` - Add metadata field to Authorship structs (affiliation already exists)

**Handlers:**
- `src/handlers/committees.rs` - Update ~12 SQL queries (add affiliation + metadata)
- `src/handlers/authorships.rs` - Update ~6 SQL queries (add metadata only, affiliation exists)

## Example Usage

### Implicit Source (uses conference archive URLs)
```json
{
  "conference_id": "qip-2024-uuid",
  "author_id": "author-uuid",
  "committee": "PC",
  "position": "member",
  "affiliation": "MIT",
  "metadata": {}
}
```
→ Source assumed to be `conferences.archive_pc_url` for QIP 2024

### Explicit Source Override with Affiliation
```json
{
  "conference_id": "qip-2024-uuid",
  "author_id": "author-uuid",
  "committee": "PC",
  "position": "area_chair",
  "affiliation": "MIT CSAIL",
  "metadata": {
    "source_type": "archive",
    "source_url": "https://qip.iaqi.org/2024/pc.html#area-chairs",
    "source_description": "Listed in Area Chairs section"
  }
}
```

### HotCRP Import (Authorship with existing affiliation field)
```json
{
  "publication_id": "paper-uuid",
  "author_id": "author-uuid",
  "author_position": 2,
  "published_as_name": "Alice Quantum",
  "affiliation": "Caltech",
  "metadata": {
    "source_type": "hotcrp",
    "source_url": "hotcrp-qip2024.json",
    "source_description": "Imported from HotCRP export"
  }
}
```

### Manual Entry with Affiliation
```json
{
  "conference_id": "qcrypt-2018-uuid",
  "author_id": "author-uuid",
  "committee": "OC",
  "affiliation": "University of Waterloo",
  "metadata": {
    "source_type": "manual",
    "source_description": "Personal knowledge - no archive available",
    "source_date": "2024-12-30"
  }
}
```

## Migration Path for Existing Data

Optional backfill script for existing records:

```sql
-- Mark existing committee roles as manual imports
UPDATE committee_roles
SET metadata = '{"source_type": "manual", "source_description": "Initial data import"}'::jsonb
WHERE metadata = '{}'::jsonb
  AND creator = 'data_import';
```

## Benefits

1. **Non-breaking**: Existing code works without changes (metadata defaults to `{}`, affiliation defaults to NULL)
2. **Flexible**: Can track any source type via JSONB
3. **Efficient**: Leverages existing conference archive URLs to avoid duplication
4. **Simple**: Just URL + description, no complex structure
5. **Queryable**: GIN index enables efficient filtering by source_type
6. **Auditable**: Complements existing creator/modifier fields with source provenance
7. **Point-in-time affiliations**: Committee roles now track affiliation just like authorships do
8. **Consistent pattern**: Both committee_roles and authorships have affiliation + metadata fields

## Future Enhancements (Optional)

- Add `source_type` filter to query parameters in CommitteeQuery/AuthorshipQuery
- Create utility endpoint to resolve effective source URL (merging record metadata with conference archive URLs)
- Add verification status tracking (e.g., `"verified": true`)
