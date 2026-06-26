#!/bin/bash
# reset-db.sh — Tear down the database volume and rebuild from scratch.
# Runs: docker-compose down -v, starts db, applies sqlx migrations, loads seeds.
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$SCRIPT_DIR"

echo "==> Stopping all containers and removing volumes..."
docker-compose down -v

echo "==> Starting database container..."
docker-compose up -d db

echo "==> Waiting for PostgreSQL to be ready..."
until docker-compose exec -T db pg_isready -U quantumdb -q; do
    sleep 1
done
echo "    PostgreSQL is ready."

echo "==> Running migrations..."
sqlx migrate run
echo "    Migrations complete."

echo "==> Loading seeds..."
for f in seeds/insert_qip_conferences.sql seeds/insert_qcrypt_conferences.sql seeds/insert_tqc_conferences.sql; do
    echo "    $f"
    docker-compose exec -T db psql -U quantumdb -d quantumdb -f "/seeds/$(basename "$f")"
done
echo "    Seeds loaded."

echo "==> Starting remaining services..."
docker-compose up -d

echo ""
echo "Reset complete. App running at http://localhost:3000"
