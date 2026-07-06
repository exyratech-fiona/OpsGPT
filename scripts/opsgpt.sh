#!/usr/bin/env bash
# OpsGPT ops helper. Run on the server from anywhere: ~/OpsGPT/scripts/opsgpt.sh <cmd>
set -euo pipefail
cd "$(cd "$(dirname "$0")/.." && pwd)"   # -> ~/OpsGPT

cmd="${1:-help}"; shift || true

case "$cmd" in
  up)        docker compose up -d ;;
  down)      docker compose down ;;
  restart)   docker compose restart "$@" ;;
  ps|status) docker compose ps ;;
  logs)      docker compose logs -f "$@" ;;
  build)     docker compose build "$@" ;;
  pull)      docker compose pull "$@" ;;
  health)    curl -s localhost:"${HTTP_PORT:-8088}"/api/health/ready; echo ;;

  backup)    # on-demand dump to ./backups
    ts=$(date +%Y%m%d-%H%M%S)
    out="backups/opsgpt-manual-${ts}.sql.gz"
    mkdir -p backups
    docker compose exec -T postgres pg_dump -U "${POSTGRES_USER:-opsgpt}" "${POSTGRES_DB:-opsgpt}" | gzip > "$out"
    echo "wrote $out ($(du -h "$out" | cut -f1))"
    ;;

  restore)   # restore from a .sql.gz: opsgpt.sh restore backups/opsgpt-XXXX.sql.gz
    file="${1:?usage: opsgpt.sh restore <backups/xxx.sql.gz>}"
    echo "Restoring $file into the database (existing data will be overwritten where it conflicts)..."
    gunzip -c "$file" | docker compose exec -T postgres psql -U "${POSTGRES_USER:-opsgpt}" "${POSTGRES_DB:-opsgpt}"
    echo "restore done"
    ;;

  backups)   ls -lh backups/ 2>/dev/null || echo "no backups yet" ;;

  *)
    cat <<EOF
OpsGPT ops helper
  up | down | restart [svc] | ps | logs [svc] | build [svc] | pull [svc]
  health                 readiness probe
  backup                 on-demand DB dump -> ./backups
  restore <file.sql.gz>  restore a dump
  backups                list dumps
EOF
    ;;
esac
