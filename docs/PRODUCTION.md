# Production deployment — runbook

Record of the live production instance and the operations runbook for it. For the
generic "how to deploy from scratch" guide see [DEPLOYMENT.md](DEPLOYMENT.md).

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
  uses it for rate limiting via `TRUST_PROXY=1`).
- **Firewall** (`ufw`): only **22/80/443** open. Ports 3000 and 5432 are not externally reachable.

## Environment / secrets

App config lives in `~/quantumdb/.env` (gitignored; perms 600). **Never commit it.** Keys:

| Var | Value in prod | Notes |
|---|---|---|
| `POSTGRES_PASSWORD` | *(secret)* | builds `DATABASE_URL` + initialises the DB |
| `API_TOKENS` | *(secret)* | Bearer token(s) for write/admin endpoints |
| `ENABLE_SWAGGER` | `1` | Swagger UI + OpenAPI exposed (default off if unset) |
| `CORS_ALLOWED_ORIGINS` | *(empty)* | web UI is same-origin; no cross-origin grant needed |
| `RUST_LOG` | `info` | |
| `TRUST_PROXY` / | baked into the compose file (`TRUST_PROXY=1`, behind Caddy) | |

`docker-compose.prod.yml` hardcodes `TRUST_PROXY=1`; `ENABLE_SWAGGER` is `${ENABLE_SWAGGER:-0}`
so it's toggled via `.env`.

Retrieve the live API token: `grep API_TOKENS ~/quantumdb/.env`.

## Operations runbook

All commands run from `~/quantumdb` on the host. `C=docker compose -f docker-compose.prod.yml`.

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
~/venv/bin/python tools/scrapers/import_from_csv.py talks data/conferences/*/talks.csv data/conferences/tqc_*/proceedings.csv data/conferences/tqc_*/workshop.csv
~/venv/bin/python tools/scrapers/import_from_csv.py business-meetings data/conferences/*/business_meeting.csv
~/venv/bin/python tools/dedup_authors.py --commit         # also refreshes the materialized views
rm docker-compose.import.yml
docker compose -f docker-compose.prod.yml up -d --force-recreate db   # back to internal-only
```
After bulk data changes, materialized views must be refreshed (`dedup_authors.py --commit` does
this; otherwise `REFRESH MATERIALIZED VIEW CONCURRENTLY author_stats, conference_stats, coauthor_pairs`).

**Backups:** the only state is the `postgres_data` Docker volume. To dump:
`docker compose -f docker-compose.prod.yml exec -T db pg_dump -U quantumdb quantumdb | gzip > backup.sql.gz`.

## Current data (as of go-live)

~66 conferences · ~5,540 authors · ~3,970 publications · ~13,640 authorships ·
2,635 committee roles · 18 business meetings.

## Notes / gotchas

- **Deleting a conference (or author/publication) that still has children returns 409**, not a
  delete — FKs are `NO ACTION` (no cascade). Remove the children first, or add `ON DELETE CASCADE`
  deliberately.
- **Askama templates compile into the binary** → any `templates/` change needs a rebuild
  (`… up -d --build`); `static/` is served live.
- The on-box Rust build can peak past 2 GB RAM; the 4 GB swap covers it.
