#!/bin/sh
# Runs inside the opsgpt-backup container. Dumps Postgres on a schedule and
# prunes old dumps. PGPASSWORD/POSTGRES_* come from the environment.
set -u

INTERVAL="${BACKUP_INTERVAL_HOURS:-24}"
RETAIN="${BACKUP_RETAIN_DAYS:-7}"
mkdir -p /backups

echo "[backup] started: every ${INTERVAL}h, retain ${RETAIN}d"
while true; do
  TS=$(date +%Y%m%d-%H%M%S)
  OUT="/backups/opsgpt-${TS}.sql.gz"
  echo "[backup] $(date -u +%FT%TZ) dumping -> ${OUT}"
  if pg_dump -h postgres -U "${POSTGRES_USER}" "${POSTGRES_DB}" | gzip > "${OUT}"; then
    echo "[backup] ok ($(du -h "${OUT}" | cut -f1))"
  else
    echo "[backup] FAILED"; rm -f "${OUT}"
  fi
  # retention
  find /backups -name 'opsgpt-*.sql.gz' -type f -mtime "+${RETAIN}" -delete 2>/dev/null
  sleep "$(( INTERVAL * 3600 ))"
done
