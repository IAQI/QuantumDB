# Deployment & operations

How to run QuantumDB on a server, the security hardening applied to the
codebase, and the runbook for the **live instance** (<https://quantumdb.iaqi.org>).
See `docs/CODE_REVIEW.md` for the security-review history.

## Environment variables

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `DATABASE_URL` | yes | — | Postgres connection string. |
| `POSTGRES_PASSWORD` | yes (prod compose) | — | DB password; the prod compose builds `DATABASE_URL` and initialises the DB from it. |
| `API_TOKENS` | yes | — | Comma-separated Bearer tokens for write/admin endpoints. Generate with `./tools/generate_token.sh`. |
| `CORS_ALLOWED_ORIGINS` | no | *(none → no cross-origin)* | Comma-separated browser origins allowed to call the API cross-origin. `*` restores any-origin. Same-origin always works. |
| `TRUST_PROXY` | no | `false` | When `1`, the rate limiter keys on `X-Forwarded-For`/`X-Real-IP`. Enable **only** behind a proxy that overwrites those headers. |
| `ENABLE_SWAGGER` | no | `true` (app) | Gates `/api/v1/openapi.json` + the Swagger UI. The app enables it by default; the **prod compose flips the default off** (`${ENABLE_SWAGGER:-0}`), so set `ENABLE_SWAGGER=1` in `.env` to expose it in prod. |
| `BIND_ADDR` | no | `0.0.0.0:3000` | Listen address. Use `127.0.0.1:3000` for a direct run behind a same-host proxy. |
| `RUST_LOG` | no | `info` | Log level. |
| `AUTH_DISABLED` | no | unset | `1` bypasses auth entirely. **Local dev only — never set in production.** |

## Recommended topology (VM + reverse proxy)

Run the app on loopback and put a TLS-terminating reverse proxy in front. The
prod compose already publishes the app to `127.0.0.1:3000` only, and does **not**
expose Postgres or pgAdmin.

1. **Secrets** — create `.env` next to the compose file (copy `.env.example`):
   ```
   POSTGRES_PASSWORD=<strong random>
   API_TOKENS=<output of ./tools/generate_token.sh>
   CORS_ALLOWED_ORIGINS=https://quantumdb.example.org   # or leave empty
   ```
2. **Start the hardened stack:**
   ```bash
   docker compose -f docker-compose.prod.yml up -d --build
   ```
   This runs `app` (loopback-only) + `db` (internal-only, healthchecked), with
   `TRUST_PROXY=1` baked in and Swagger off by default. No pgAdmin, no published 5432.
3. **Reverse proxy with automatic HTTPS — Caddy** (simplest):
   ```
   # /etc/caddy/Caddyfile
   quantumdb.example.org {
       reverse_proxy 127.0.0.1:3000
   }
   ```
   Caddy obtains/renews Let's Encrypt certificates automatically and sets
   `X-Forwarded-For`, which the app's rate limiter then uses (`TRUST_PROXY=1`).
4. **Firewall** — allow only `80`/`443` inbound (e.g. `ufw allow 80,443/tcp`).
   Do **not** expose `3000`, `5432`, or `5050`.
5. **DB admin** — use `docker compose -f docker-compose.prod.yml exec db psql -U quantumdb`
   or an SSH tunnel; pgAdmin is intentionally absent from the prod stack.

## Security hardening applied

- **Auth**: Bearer header only — the `?token=` query-string fallback was removed
  (tokens no longer leak to proxy/access logs, history, or `Referer`).
  Constant-time comparison and the 32-char minimum are enforced.
- **Rate limiting**: proxy-aware via `TRUST_PROXY` (X-Forwarded-For) so the limit
  stays per-client behind a proxy instead of collapsing to one global bucket.
- **Response headers**: `Content-Security-Policy` (allows only the CDNs the app
  uses + the inline scripts/styles it relies on; blocks framing and foreign
  origins) and `Strict-Transport-Security` (HSTS), alongside X-Frame-Options /
  X-Content-Type-Options / Referrer-Policy / Permissions-Policy.
- **CORS**: driven by `CORS_ALLOWED_ORIGINS`; default denies cross-origin.
- **Request size**: explicit 1 MB body limit.
- **API docs**: Swagger/OpenAPI gated behind `ENABLE_SWAGGER` (off by default in prod compose).
- **Container**: runs as a non-root user; builder base pinned (`rust:1-bookworm`).
- **Logging**: web handlers use structured `tracing` instead of `eprintln!`.

### Pre-deploy checklist
- [ ] `.env` populated with a strong `POSTGRES_PASSWORD` and a fresh `API_TOKENS`; `AUTH_DISABLED` unset.
- [ ] Reverse proxy terminating TLS; app reachable only via it (firewall to 80/443).
- [ ] `CORS_ALLOWED_ORIGINS` set to your front-end origin (or left empty).
- [ ] `docker compose -f docker-compose.prod.yml config` validates with your `.env`.
- [ ] Rotate `API_TOKENS` periodically.

## Known limitations (not blockers)

- `creator`/`modifier` audit fields are client-supplied, so they are advisory, not
  a trustworthy actor trail (tokens are opaque and carry no principal identity).
- The CSP relies on `'unsafe-inline'` because the templates use inline scripts and
  event handlers; self-hosting the CDN assets would allow a stricter policy.

---

# Live instance — quantumdb.iaqi.org

Record of the production deployment and its operations runbook.

- **Live URL:** <https://quantumdb.iaqi.org>  ·  **API:** `/api/v1`  ·  **Swagger:** `/api/v1/swagger-ui/`
- **Deployed:** 2026-06-27 (Infomaniak VPS)

## Host

| | |
|---|---|
| SSH | `ssh infomaniak-quantumdb` (user `ubuntu`, passwordless sudo) |
| Public IP | `179.237.80.172` (A) · `2001:1600:18:206::34f` (AAAA) — domain has both |
| OS | Ubuntu 24.04 LTS, 1 vCPU / 1.9 GB RAM / ~17 GB disk |
| Swap | 4 GB swapfile (`/swapfile`, in `/etc/fstab`) — added for the Rust build |
| Repo | `~/quantumdb`, cloned via read-only GitHub **deploy key** `~/.ssh/quantumdb_deploy` |

## Architecture

```
Internet ──443/80──> Caddy (host, auto-TLS) ──127.0.0.1:3000──> app container ──> db container
                                                                 (Postgres, internal-only)
```

- **Docker Compose** stack from `docker-compose.prod.yml`:
  - `app` — published to `127.0.0.1:3000` **only** (not public), runs as a non-root user.
  - `db` — Postgres 15, **no published port** (reachable only by `app` over the compose network);
    data in the `postgres_data` volume; schema+seed conferences loaded on first boot via `docker-init.sh`.
  - Both `restart: unless-stopped`; Docker enabled on boot.
- **Caddy** (host service, apt) reverse-proxies `quantumdb.iaqi.org → 127.0.0.1:3000` with
  automatic Let's Encrypt TLS. Config: `/etc/caddy/Caddyfile`. Sets `X-Forwarded-For` (the app
  uses it for rate limiting via `TRUST_PROXY=1`). Caddy also writes a JSON **access log** to
  `/var/log/caddy/access.log` (rolled at 10 MiB × 10 files, 30-day cap) — the input for the
  traffic dashboard. A second vhost, `stats.quantumdb.iaqi.org`, serves that dashboard behind
  HTTP basic auth (see *Traffic analytics* in the runbook).
- **Firewall** (`ufw`): only **22/80/443** open. Ports 3000 and 5432 are not externally reachable.

## Environment / secrets

App config lives in `~/quantumdb/.env` (gitignored; perms 600). **Never commit it.** Live values:

| Var | Value in prod | Notes |
|---|---|---|
| `POSTGRES_PASSWORD` | *(secret)* | builds `DATABASE_URL` + initialises the DB |
| `API_TOKENS` | *(secret)* | Bearer token(s) for write/admin endpoints |
| `ENABLE_SWAGGER` | `1` | Swagger UI + OpenAPI exposed (compose default is off) |
| `CORS_ALLOWED_ORIGINS` | *(empty)* | web UI is same-origin; no cross-origin grant needed |
| `RUST_LOG` | `info` | |
| `TRUST_PROXY` | baked into the compose file (`=1`, behind Caddy) | |

Retrieve the live API token: `grep API_TOKENS ~/quantumdb/.env`.

## Operations runbook

All commands run from `~/quantumdb` on the host.

**Deploy code updates** (Rust change → rebuild, ~6 min first time, faster after thanks to layer cache):
```bash
GIT_SSH_COMMAND='ssh -i ~/.ssh/quantumdb_deploy -o IdentitiesOnly=yes' git pull --ff-only
docker compose -f docker-compose.prod.yml up -d --build
```

**Restart / recreate app** (e.g. after an `.env` change — no rebuild):
```bash
docker compose -f docker-compose.prod.yml up -d app
```

**Logs / status:**
```bash
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs -f app
```

**Rotate the API token:**
```bash
NEW=$(openssl rand -hex 32)
sed -i "s|^API_TOKENS=.*|API_TOKENS=${NEW}|" .env
docker compose -f docker-compose.prod.yml up -d app
```

**Toggle Swagger** in prod: set `ENABLE_SWAGGER=1` (or `0`) in `.env`, then `… up -d app`.

**DB shell:** `docker compose -f docker-compose.prod.yml exec db psql -U quantumdb -d quantumdb`

**Refresh / reload data** (re-run the CSV importers — they're idempotent). The DB is
internal-only, so expose it on loopback for the import then remove the port:
```bash
printf 'services:\n  db:\n    ports:\n      - "127.0.0.1:5432:5432"\n' > docker-compose.import.yml
docker compose -f docker-compose.prod.yml -f docker-compose.import.yml up -d db
python3 -m venv ~/venv && ~/venv/bin/pip install -r tools/scrapers/requirements.txt   # once
source .env; export DATABASE_URL="postgres://quantumdb:${POSTGRES_PASSWORD}@127.0.0.1:5432/quantumdb"
~/venv/bin/python tools/scrapers/import_from_csv.py committees data/conferences/*/committees.csv
~/venv/bin/python tools/scrapers/import_from_csv.py talks data/conferences/*/talks.csv data/conferences/*/proceedings.csv data/conferences/*/workshop.csv
~/venv/bin/python tools/scrapers/import_from_csv.py business-meetings data/conferences/*/business_meeting.csv
~/venv/bin/python tools/dedup_authors.py --commit         # also refreshes the materialized views
rm docker-compose.import.yml
docker compose -f docker-compose.prod.yml up -d --force-recreate db   # back to internal-only
```
After bulk data changes, materialized views must be refreshed (`dedup_authors.py --commit` does
this; otherwise `REFRESH MATERIALIZED VIEW CONCURRENTLY author_stats, conference_stats, coauthor_pairs`).

**Full from-scratch re-init** (wipe + rebuild the DB from the CSVs). The importers above are
*incremental* (find-or-update by `canonical_key` / normalized name), so they **cannot** undo a
structural CSV change — a removed talk row, a renamed/merged author, a stripped nickname — because
the old author/publication row simply keeps existing. Those changes only take effect on a clean
rebuild. This is the intended path whenever the source CSVs are the truth and the DB should be a
pure function of them (e.g. the author-anomaly cleanup + fuzzy-merge aliases).

> ⚠️ **Destructive + downtime.** `down -v` deletes the `postgres_data` volume. Only safe because the
> DB is a pure function of the CSVs — confirm nothing was entered via the API on prod that isn't in
> the CSVs. **Back up first** (see below) so you can roll back.

```bash
# 0. Back up the current volume first (see Backups) — keep the dump until the reload is verified.
docker compose -f docker-compose.prod.yml exec -T db pg_dump -U quantumdb quantumdb | gzip > ~/pre-reinit-$(date +%F).sql.gz

# 1. Wipe and re-create the DB (fresh volume auto-runs migrations + seeds = conferences only).
docker compose -f docker-compose.prod.yml down -v
printf 'services:\n  db:\n    ports:\n      - "127.0.0.1:5432:5432"\n' > docker-compose.import.yml
docker compose -f docker-compose.prod.yml -f docker-compose.import.yml up -d db
until docker compose -f docker-compose.prod.yml exec -T db pg_isready -U quantumdb -q; do sleep 1; done

# 2. Import every CSV, then apply curated dedup + aliases. Note the `*/` glob (not `tqc_*/`):
#    proceedings/workshop are TQC-only but some dirs are uppercase (TQC_2006..TQC_2012), which a
#    lowercase `tqc_*` glob silently skips — dropping those years' papers + authors.
source .env; export DATABASE_URL="postgres://quantumdb:${POSTGRES_PASSWORD}@127.0.0.1:5432/quantumdb"
~/venv/bin/python tools/scrapers/import_from_csv.py committees data/conferences/*/committees.csv
~/venv/bin/python tools/scrapers/import_from_csv.py talks data/conferences/*/talks.csv data/conferences/*/proceedings.csv data/conferences/*/workshop.csv
~/venv/bin/python tools/scrapers/import_from_csv.py business-meetings data/conferences/*/business_meeting.csv
~/venv/bin/python tools/dedup_authors.py --commit          # Phase A applies data/author_aliases.csv, then refreshes the views

# 3. Back to internal-only + bring the app up.
rm docker-compose.import.yml
docker compose -f docker-compose.prod.yml up -d --force-recreate db
docker compose -f docker-compose.prod.yml up -d app
```
The `talks` import prints a handful of "conference not found or no authors" warnings — these are
junk schedule rows and rows with empty author+speaker columns, correctly skipped (they create no
authors). Sanity-check afterward: `SELECT count(*) FROM authors` and
`SELECT full_name FROM authors WHERE full_name LIKE '%(%'` (should be empty).

**Backups:** the only state is the `postgres_data` Docker volume. To dump:
`docker compose -f docker-compose.prod.yml exec -T db pg_dump -U quantumdb quantumdb | gzip > backup.sql.gz`.

## Traffic analytics (GoAccess)

A static [GoAccess](https://goaccess.io) dashboard reports site/API traffic (unique visitors,
top pages, status codes, etc.) from Caddy's access log. It is **not** part of the Docker stack —
everything runs on the host.

- **Dashboard:** <https://stats.quantumdb.iaqi.org> — HTTP basic auth, user `iaqi`. The password
  is stored only as a bcrypt hash in the Caddyfile (not recoverable); keep the plaintext in a
  password manager. To reset it: `caddy hash-password --plaintext '<new>'`, paste the hash into
  the `stats.quantumdb.iaqi.org` block in `/etc/caddy/Caddyfile`, then `sudo systemctl reload caddy`.
- **DNS:** `stats.quantumdb.iaqi.org` needs `A 179.237.80.172` + `AAAA 2001:1600:18:206::34f`
  (same targets as the apex). Caddy auto-provisions the TLS cert once the record resolves.
- **Moving parts on the host:**
  - Caddy `log` directive → `/var/log/caddy/access.log` (JSON, self-rotating).
  - `/usr/local/bin/quantumdb-stats.sh` — converts the JSON log to Apache COMBINED with `jq`
    (GoAccess 1.8 can't parse Caddy's log envelope directly), then renders
    `/var/www/quantumdb-stats/index.html`. IPs are anonymized (`--anonymize-ip`) and known
    crawlers excluded (`--ignore-crawlers`).
  - `/etc/cron.d/quantumdb-stats` — regenerates the report every 15 min.
  - `stats.quantumdb.iaqi.org` vhost in `/etc/caddy/Caddyfile` — `basic_auth` + `file_server`
    over `/var/www/quantumdb-stats`.
- **Regenerate on demand:** `sudo /usr/local/bin/quantumdb-stats.sh`.
- **Raw ad-hoc queries** (no dashboard needed), e.g. unique client IPs in the current log:
  `sudo jq -r '.request.client_ip' /var/log/caddy/access.log | sort -u | wc -l`.
- **Privacy:** client IPs are personal data. The dashboard anonymizes them and logs self-rotate
  with a 30-day cap; tighten `roll_keep`/`roll_keep_for` in the Caddyfile if you want shorter retention.

## Current data (as of 2026-07-02)

66 conferences · ~8,640 authors · ~7,250 publications (~1,480 with abstracts) ·
~24,250 authorships · 2,640 committee roles · 18 business meetings.

## Notes / gotchas

- **Deleting a conference (or author/publication) that still has children returns 409**, not a
  delete — FKs are `NO ACTION` (no cascade). Remove the children first, or add `ON DELETE CASCADE`
  deliberately.
- **Askama templates compile into the binary** → any `templates/` change needs a rebuild
  (`… up -d --build`); `static/` is served live.
- The on-box Rust build can peak past 2 GB RAM; the 4 GB swap covers it.
