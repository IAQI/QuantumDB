# Deployment & production hardening

This guide covers running QuantumDB on a server (a single VM) and the security
hardening applied to the codebase. See `docs/CODE_REVIEW.md` for the full review
history.

## Environment variables

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `DATABASE_URL` | yes | — | Postgres connection string. |
| `POSTGRES_PASSWORD` | yes (prod compose) | — | DB password; the prod compose builds `DATABASE_URL` and initialises the DB from it. |
| `API_TOKENS` | yes | — | Comma-separated Bearer tokens for write/admin endpoints. Generate with `./tools/generate_token.sh`. |
| `CORS_ALLOWED_ORIGINS` | no | *(none → no cross-origin)* | Comma-separated browser origins allowed to call the API cross-origin. `*` restores any-origin. Same-origin always works. |
| `TRUST_PROXY` | no | `false` | When `1`, the rate limiter keys on `X-Forwarded-For`/`X-Real-IP`. Enable **only** behind a proxy that overwrites those headers. |
| `ENABLE_SWAGGER` | no | `true` | Set `0` to hide `/api/v1/openapi.json` and the Swagger UI in production. |
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
   `TRUST_PROXY=1` and `ENABLE_SWAGGER=0` baked in. No pgAdmin, no published 5432.
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

## Security hardening applied (pre-deploy pass)

- **Auth**: removed the `?token=` query-string fallback (tokens no longer leak to
  proxy/access logs, history, or `Referer`); Bearer header only. Constant-time
  comparison and the 32-char minimum are unchanged.
- **Rate limiting**: proxy-aware via `TRUST_PROXY` (X-Forwarded-For) so the limit
  stays per-client behind a proxy instead of collapsing to one global bucket.
- **Response headers**: added `Content-Security-Policy` (allows only the CDNs the
  app uses + inline scripts/styles it relies on; blocks framing and foreign
  origins) and `Strict-Transport-Security` (HSTS), alongside the existing
  X-Frame-Options / X-Content-Type-Options / Referrer-Policy / Permissions-Policy.
- **CORS**: now driven by `CORS_ALLOWED_ORIGINS`; default denies cross-origin.
- **Request size**: explicit 1 MB body limit.
- **API docs**: Swagger/OpenAPI gated behind `ENABLE_SWAGGER` (off in prod compose).
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
