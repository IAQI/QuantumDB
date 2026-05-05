# QuantumDB Comprehensive Code Review

## Context

A comprehensive review of the QuantumDB codebase (Rust + Axum + PostgreSQL REST API for tracking quantum computing conferences) with particular attention to security. Findings come from reading the actual source — every file:line reference has been verified, not inferred.

**Overall verdict.** The codebase is solid for a v0.1.0 project. Schema design is clean, SQLx usage is uniformly safe (no string-interpolated SQL), Askama auto-escaping prevents XSS, and the modular handler structure is easy to extend. The most important issues are concentrated in (a) authentication coverage gaps, (b) input validation, and (c) a few hardening items that production deployment will require.

Counts: **2 critical, 4 high, 8 medium, 5 low/info-level recommendations.** The first three items below are the ones to fix before any non-trivial public deployment.

---

## CRITICAL

### C1 — `/admin/refresh-stats` is unauthenticated
- **Files:** [src/main.rs:176](../src/main.rs), [src/handlers/web/admin.rs](../src/handlers/web/admin.rs)
- **Evidence:** `/admin/refresh-stats` is registered on `web_routes`, which has no auth layer. The `protected_web_routes` router exists at `src/main.rs:179` but is empty (`// currently none`). Both `web_routes` and `protected_web_routes` are merged in `src/main.rs:182-184`, so the empty protected layer never gets applied to anything.
- **Why it matters:** Anyone on the internet can issue `GET /admin/refresh-stats`, which runs three `REFRESH MATERIALIZED VIEW` statements. Each refresh holds an `ACCESS EXCLUSIVE` lock on the view (the handler calls plain `REFRESH`, not `REFRESH ... CONCURRENTLY`), so concurrent reads of `author_stats` / `conference_stats` / `coauthor_pairs` are blocked for the duration. A trivial loop is a DoS primitive.
- **Note:** [CLAUDE.md](../CLAUDE.md) claims this route is authenticated. The doc is out of sync with the code.
- **Fix:** Move the route into `protected_web_routes` (which already has `auth_middleware` layered on at `src/main.rs:180`). One-line change.

### C2 — Token comparison is not constant-time
- **File:** [src/middleware/auth.rs:118](../src/middleware/auth.rs)
- **Evidence:** `valid_tokens.iter().any(|t| t == provided_token)`. Rust's `String == String` first checks length, then does a byte-by-byte comparison that short-circuits on the first mismatch.
- **Why it matters:** Standard timing-side-channel concern for any auth-secret comparison. Practical exploitability over the open internet is limited (network jitter dominates), but against a co-located attacker this leaks token prefix length and possibly bytes. Constant-time comparison is the universally-applied mitigation and the cost is trivial.
- **Fix:** Use the `subtle` crate's `ConstantTimeEq` (already a transitive dependency in most Rust stacks) or `ring::constant_time::verify_slices_are_equal`. Compare each candidate token in constant time, avoid any short-circuit.

---

## HIGH

### H1 — Pagination `limit`/`offset` are unbounded and unvalidated
- **Files:** [src/handlers/authors.rs:37-38](../src/handlers/authors.rs), and the same pattern in `conferences.rs`, `publications.rs`, `committees.rs`, `authorships.rs`.
- **Evidence:** `let limit = query.limit.unwrap_or(100);` — accepts any `i64`. There is no upper bound and no rejection of negative values. PostgreSQL accepts negative LIMIT as zero rows, but extremely large limits will fetch and serialise enormous result sets.
- **Why it matters:** `?limit=999999999` against a public read endpoint forces a full-table scan + serialisation. Combined with the lack of rate limiting (L1), this is a single-request DoS.
- **Fix:** Introduce a shared `Pagination { limit, offset }` extractor that clamps `limit` to e.g. `1..=1000` and `offset` to `>=0`. Apply across all five list handlers. Default to 100, max 1000.

### H2 — No string-length or shape validation on POST/PUT bodies
- **Files:** model definitions in [src/models/](../src/models/) (e.g. `Author`, `Conference`, `Publication`).
- **Evidence:** `CreateAuthor`/`CreatePublication`/etc. accept `String` for `full_name`, `title`, `abstract_text`, `affiliation`, etc., with no length cap and no validation derives. The DB has no `VARCHAR(N)` caps either — most text columns are unbounded `TEXT`.
- **Why it matters:** Authenticated callers (or, more concerning, leaked tokens) can write 100 MB strings into `title` or `abstract_text`. Beyond storage bloat, oversized text breaks the GIN/tsvector full-text index path.
- **Fix:** Add `validator` crate derives (`#[validate(length(max = 1024))]` etc.) on Create/Update DTOs. Enforce reasonable caps: name ≤ 255, title ≤ 1000, abstract ≤ 50 KB, URLs ≤ 2048. Reject in handler before INSERT.

### H3 — JSONB `metadata` accepts arbitrary shape and size
- **Files:** [src/models/authorship.rs](../src/models/authorship.rs), [src/models/committee.rs](../src/models/committee.rs); migration [migrations/20251230100001_add_source_tracking_comments.sql](../migrations/20251230100001_add_source_tracking_comments.sql) documents an *intended* shape but no DB-level constraint enforces it.
- **Why it matters:** (a) DoS via huge JSONB payloads (Axum's default 2 MB body limit caps single requests, but no per-field cap), (b) the documented `source_type` taxonomy is advisory only, so scrapers writing inconsistent shapes will produce data that downstream queries can't aggregate cleanly.
- **Fix:** Either (i) typed wrapper struct deserialised from JSONB (`SourceMetadata { source_type: SourceType, source_url: Option<Url>, ... }`) and serialised on write, or (ii) a `CHECK (jsonb_typeof(metadata) = 'object' AND length(metadata::text) < 4096)` constraint. Option (i) is preferred — it makes the docs and the code agree.

### H4 — No URL validation on URL-typed fields
- **Files:** [src/models/conference.rs](../src/models/conference.rs) (`archive_url`, `archive_organizers_url`, etc.), [src/models/author.rs](../src/models/author.rs) (`homepage_url`), [src/models/publication.rs](../src/models/publication.rs) (`presentation_url`, `video_url`).
- **Evidence:** All stored as raw `String`. Templates render them inside `<a href="…">`.
- **Why it matters:** An authenticated client can write `javascript:alert(1)` or `data:text/html,…` into `homepage_url`. Askama auto-escapes the *attribute value*, but `javascript:` URIs survive HTML escaping — they only fail when rendered with a URL-context-aware sanitiser. So this is a stored-XSS sink reachable through the admin/scraper surface.
- **Fix:** Validate URLs with `url::Url::parse` and reject any scheme other than `http`/`https` at the API boundary.

---

## MEDIUM

### M1 — `eprintln!` in async handlers instead of `tracing`
- **Files:** [src/handlers/web/admin.rs:13,20,28](../src/handlers/web/admin.rs), [src/middleware/auth.rs:103](../src/middleware/auth.rs), and similar in `src/handlers/web/home.rs`, `src/handlers/web/authors.rs`.
- **Why it matters:** Inconsistent observability — API handlers correctly use `tracing::error!`, but the web layer and one auth path bypass it. In production these go to stderr unstructured.
- **Fix:** Replace `eprintln!` with `tracing::error!` using structured fields.

### M2 — No CORS, no security headers
- **File:** [src/main.rs](../src/main.rs) — no `CorsLayer`, no `SetResponseHeaderLayer`.
- **Why it matters:** With auth tokens travelling in `Authorization` headers, a misconfigured browser context could exfiltrate. More immediately, no `X-Frame-Options`/`Content-Security-Policy` means the HTML pages can be framed.
- **Fix:** Add `tower_http::cors::CorsLayer::permissive()` or a tighter origin allowlist for the API; add `SetResponseHeaderLayer`s for `X-Frame-Options: DENY`, a basic CSP, and (when behind TLS) HSTS.

### M3 — No request-body size limit beyond Axum's default
- **File:** [src/main.rs](../src/main.rs).
- **Why it matters:** Default is 2 MB; combined with H3 (unbounded metadata) this is workable. But for scraper-bulk-import workflows, an explicit, documented limit is safer than relying on the default.
- **Fix:** `app.layer(DefaultBodyLimit::max(1 * 1024 * 1024))` plus per-route overrides if any endpoint legitimately needs more.

### M4 — `creator` / `updated_by` are client-supplied free-text
- **Files:** [src/handlers/conferences.rs](../src/handlers/conferences.rs) (and the other CRUD handlers).
- **Evidence:** The `created_by`/`updated_by` columns exist on most tables but the API trusts the client to fill them in. There's no link from `auth_middleware` to a principal identity, so an authenticated request can write any string into those audit fields.
- **Why it matters:** Audit fields that the auditee writes have ~zero forensic value. They make it look like there's accountability when there isn't.
- **Fix:** Either (i) extend `auth_middleware` to attach a principal/token-id to the request extensions and have handlers read it server-side, ignoring any client-provided value, or (ii) drop the columns.

### M5 — Materialised view refresh is non-CONCURRENT and non-transactional
- **File:** [src/handlers/web/admin.rs:9-31](../src/handlers/web/admin.rs).
- **Evidence:** Three sequential `REFRESH MATERIALIZED VIEW` statements without `CONCURRENTLY`, not wrapped in a transaction. Unique indexes for CONCURRENT refresh are present per migration [20251228160006](../migrations/20251228160006_create_materialized_views.sql).
- **Why it matters:** Each refresh blocks readers. If the second refresh fails, the first has already committed and the third never runs — leaving stats in a partially-fresh state.
- **Fix:** Append `CONCURRENTLY` to each REFRESH (already supported by existing unique indexes).

### M6 — Author ORCID lacks a UNIQUE constraint
- **File:** [migrations/20251228160001_create_authors_table.sql:34](../migrations/20251228160001_create_authors_table.sql).
- **Evidence:** Partial index exists but no unique constraint. ORCIDs are globally unique by construction; the schema should mirror that invariant.
- **Fix:** `ALTER TABLE authors ADD CONSTRAINT authors_orcid_unique UNIQUE (orcid);` (works with NULLs in Postgres — multiple NULLs allowed).

### M7 — Token format check inconsistent with token generator
- **Files:** [src/middleware/auth.rs:79-93](../src/middleware/auth.rs), [tools/generate_token.sh](../tools/generate_token.sh).
- **Evidence:** Auth allows `[A-Za-z0-9_-]`. The generator uses `openssl rand -base64 32` and strips `+/=`. A user generating a token any other way (e.g. plain base64) gets a 401 with the unhelpful message "Invalid token format."
- **Fix:** Either (i) drop the character whitelist (length check is enough — it's an opaque shared secret), or (ii) document the constraint loudly in the README and in the generator script's output.

### M8 — Authorship `(publication_id, author_position)` race
- **File:** [migrations/20251228160004_create_authorships_table.sql:21](../migrations/20251228160004_create_authorships_table.sql).
- **Evidence:** UNIQUE constraint is correct, but `create_authorship` doesn't run inside a transaction or use `INSERT ... ON CONFLICT`. Two concurrent inserts for the same `(pub, position)` race; the loser gets a generic 500.
- **Fix:** Either compute the next position server-side inside a transaction, or return 409 Conflict on the unique-violation SQLState (`23505`) so the client can retry.

---

## LOW / INFO

### L1 — No rate limiting
- Recommended for the auth endpoint surface (POST/PUT/DELETE) and for the unbounded list endpoints. `tower-governor` is the usual choice. Pair with C2/H1.

### L2 — No `HEALTHCHECK` in Dockerfile
- Add `HEALTHCHECK CMD curl -fsS http://localhost:3000/health || exit 1` so orchestrators can detect a wedged container.

### L3 — API is not versioned
- Currently mounted at `/api/...`. Fine for v0.1; once external consumers exist, prefer `/api/v1/...`.

### L4 — Significant CRUD boilerplate
- ~1,750 lines across the five CRUD modules with near-identical structure. This isn't a bug — but if you find yourself maintaining the same change in five places repeatedly, a generic `Crud<T>` trait or a `crud_handlers!` macro would pay back quickly. Don't extract speculatively; extract on the third repetition.

### L5 — Scraper imports lack idempotency
- [tools/scrapers/talks/importer.py](../tools/scrapers/talks/importer.py) inserts authors without `SELECT id FROM authors WHERE orcid = $1 OR normalized_name = $1` first, so re-running an import duplicates rows. M6 (ORCID UNIQUE) makes the ORCID case fail loudly, which is the right default — but the importer should `ON CONFLICT DO NOTHING` / lookup-then-insert.

---

## Things that are notably well-done

So the report isn't lopsided — these are explicit confirmations, not boilerplate praise:

- **SQL injection: clean.** Every query uses SQLx `query!`/`query_as!` macros with parameter placeholders. The ILIKE search at `src/handlers/authors.rs:41` builds the `%pattern%` string in Rust and passes it as a bound parameter — the wildcard sandwich is in the value, not the SQL text. No `format!` building SQL anywhere in the tree.
- **XSS: clean.** Askama auto-escapes by default. No `|safe` filter usage in the templates. (Caveat: H4 — URL-attribute context still needs scheme validation.)
- **Token entropy: correct.** [tools/generate_token.sh](../tools/generate_token.sh) uses `openssl rand -base64 32` → 256 bits. The format check rejects anything under 32 chars.
- **Schema design: solid.** `UNIQUE (venue, year)` on conferences; presenter trigger validates the FK target is actually an authorship; `GENERATED ALWAYS` tsvector with weighted columns A/B; partial indexes on nullable lookup columns; GIN indexes on JSONB; `ON DELETE` rules thought through (cascade where children are dependent, set-null where the relationship is informational).
- **`.gitignore` is correct.** `.env`, `target/`, IDE files all covered.
- **Error handling discipline.** No `.unwrap()` in request paths — only at startup in `main`. SQLx errors are mapped to HTTP status codes consistently.
- **Async hygiene.** No blocking calls in async fns. Pool shared via `with_state(pool)` correctly.
- **`SQLX_OFFLINE` properly wired.** `.sqlx/` metadata is committed (40 query files, 176 KB), Dockerfile sets `SQLX_OFFLINE=true`. Builds reproducibly without a live DB.

---

## Suggested fix order

If acting on this review, the highest-leverage sequence:

1. **C1** (one-line move of the admin route into `protected_web_routes`)
2. **C2** (constant-time token comparison via `subtle`)
3. **H1** (shared `Pagination` extractor with clamping)
4. **H4** (URL scheme validation — protects template rendering)
5. **H2 + H3** (length caps + typed metadata) — these can ship together as a single "input validation" pass over the models
6. **M2** (CORS + security headers — cheap; do before any public deploy)
7. **M5** (CONCURRENTLY refresh — also one-line edits)
8. Then the rest of the medium tier

Verification per fix: run `cargo test` (existing 39 tests in `tests/api_tests.rs` cover CRUD lifecycles); for C1 specifically, add a test that hits `/admin/refresh-stats` without an `Authorization` header and asserts 401.
