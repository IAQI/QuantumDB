#!/bin/bash
set -e

echo "Running migrations..."
for f in /migrations/*.sql; do
    echo "  Running $f"
    psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" -f "$f"
done

echo "Running seeds..."
for f in /seeds/*.sql; do
    echo "  Running $f"
    psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" -f "$f"
done

echo "Database initialization complete!"
