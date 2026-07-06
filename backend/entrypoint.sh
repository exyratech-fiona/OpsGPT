#!/usr/bin/env bash
# Apply DB migrations, then start the API. Migrations are idempotent
# (alembic tracks applied revisions), so this is safe on every restart.
set -e

echo "[entrypoint] running database migrations..."
alembic upgrade head

echo "[entrypoint] starting uvicorn..."
exec uvicorn app.main:app \
    --host 0.0.0.0 --port 8000 \
    --proxy-headers --forwarded-allow-ips "*"
