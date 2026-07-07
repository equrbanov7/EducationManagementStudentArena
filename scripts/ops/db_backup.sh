#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
# EMSArena — timestamped nightly PostgreSQL backup
#
# Self-contained pg_dump of the production database into a dedicated directory
# OUTSIDE the app checkout (so a deploy rsync can never touch it). Files are
# named with a full date+time stamp and gzip-compressed, integrity-checked,
# and pruned by age. Independent of the docker-compose postgres-backup sidecar
# (extra redundancy — two mechanisms).
#
# Usage:
#   sudo scripts/ops/db_backup.sh                 # run a backup now
#   BACKUP_DIR=/path RETENTION_DAYS=30 db_backup.sh
#
# Schedule (nightly) via the systemd units in scripts/ops/systemd/ or cron.
# ═══════════════════════════════════════════════════════════════════════════
set -euo pipefail

PG_CONTAINER="${PG_CONTAINER:-emsarena-postgres}"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/emsarena/postgres}"
RETENTION_DAYS="${RETENTION_DAYS:-60}"
LOG="${LOG:-/var/log/emsarena-backup.log}"

log() { echo "$(date '+%F %T') [db_backup] $*" | tee -a "$LOG" >&2; }

ts="$(date +%Y%m%d-%H%M%S)"
out="${BACKUP_DIR}/emsarena_db-${ts}.sql.gz"
mkdir -p "$BACKUP_DIR"

if ! docker inspect -f '{{.State.Running}}' "$PG_CONTAINER" >/dev/null 2>&1; then
  log "ERROR: postgres container '$PG_CONTAINER' is not running"; exit 1
fi

log "start -> $out"
# pg_dump runs inside the container using its own POSTGRES_* env (no secrets on
# the host). --no-owner keeps the dump portable across restores.
if docker exec "$PG_CONTAINER" sh -c \
     'PGPASSWORD="$POSTGRES_PASSWORD" pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner' \
     2>>"$LOG" | gzip -c > "$out"; then
  if gzip -t "$out" 2>/dev/null && [ "$(stat -c%s "$out")" -gt 500 ]; then
    ln -sfn "$(basename "$out")" "${BACKUP_DIR}/emsarena_db-latest.sql.gz"
    log "OK $(du -h "$out" | cut -f1) -> $out"
  else
    log "ERROR: dump invalid/too small — removing $out"; rm -f "$out"; exit 1
  fi
else
  log "ERROR: pg_dump failed"; rm -f "$out"; exit 1
fi

# Age-based retention.
pruned="$(find "$BACKUP_DIR" -maxdepth 1 -type f -name 'emsarena_db-*.sql.gz' \
            -mtime +"$RETENTION_DAYS" -print -delete | wc -l | tr -d ' ')"
log "retention: pruned ${pruned} file(s) older than ${RETENTION_DAYS}d; total now $(find "$BACKUP_DIR" -maxdepth 1 -type f -name 'emsarena_db-*.sql.gz' | wc -l | tr -d ' ')"
