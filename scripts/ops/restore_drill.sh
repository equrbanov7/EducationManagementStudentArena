#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
# EMSArena — PostgreSQL restore drill (audit 2026-09-28 AD-02)
#
# Restores a backup into a NEW scratch database (never into the live one),
# runs sanity counts, prints the elapsed time (= measured RTO) and drops the
# scratch DB again. With --keep the restored DB is left in place so the
# runbook (docs/operations/deployment.md §12 «Restore procedure») can swap it
# in with ALTER DATABASE … RENAME while the writers are stopped.
#
# Why a new DB: the sidecar dumps are plain SQL WITHOUT --clean. Replaying one
# into the existing DB half-loads it ("relation already exists", duplicated
# rows in PK-less tables, schema not rolled back) — AD-02 reproduced that.
#
# Supported dump formats (auto-detected by magic bytes, not by extension):
#   *.sql.gz  plain SQL, gzip   (postgres-backup sidecar, db_backup.sh)
#   *.sql     plain SQL
#   *.dump    pg_dump custom format (-Fc)  → pg_restore
#
# Connection modes:
#   --container NAME  run createdb/psql/pg_restore INSIDE the postgres
#                     container via `docker exec` using its own POSTGRES_*
#                     env (no secrets on the host). Default: emsarena-postgres.
#   --dsn URL         connect with the local client tools to a server DSN,
#                     e.g. postgres://user:pass@127.0.0.1:5432/postgres
#                     (the path DB is only the maintenance DB).
#
# Usage:
#   scripts/ops/restore_drill.sh backups/postgres/daily/<file>.sql.gz
#   scripts/ops/restore_drill.sh backups/postgres            # newest dump in dir
#   scripts/ops/restore_drill.sh --keep --db emsarena_restore_20260928 <dump>
#   scripts/ops/restore_drill.sh --dsn "$DSN" --no-owner --check-tables t1,t2 \
#       --require-rows t1 <dump>
#
# Options:
#   --db NAME             scratch DB name (default emsarena_restore_drill_<ts>)
#   --keep                keep the scratch DB after a SUCCESSFUL drill
#   --no-owner            drop ownership/privilege statements (restore on a
#                         cluster that lacks the production roles, e.g. staging)
#   --check-tables LIST   comma list; each must exist, row counts are printed
#   --require-rows LIST   comma list; each must have at least one row
#   --metrics-file PATH   write Prometheus textfile metrics (last success
#                         timestamp + durations) for node_exporter
#
# Exit code: 0 = restore + sanity checks OK, non-zero otherwise. The scratch
# DB is dropped on failure even with --keep (a failed restore is useless and
# --single-transaction leaves it empty anyway).
# ═══════════════════════════════════════════════════════════════════════════
set -euo pipefail

CONTAINER="${PG_CONTAINER:-emsarena-postgres}"
DSN=""
SCRATCH_DB=""
KEEP=0
NO_OWNER=0
CHECK_TABLES="auth_user,organizations_organization,registrar_lessonmark,registrar_finalgrade,exams_examattempt,exams_examanswer,audit_auditlog,django_migrations"
REQUIRE_ROWS="auth_user,organizations_organization,django_migrations"
METRICS_FILE=""
DUMP=""

log() { echo "$(date '+%F %T') [restore_drill] $*" >&2; }
die() { log "ERROR: $*"; exit 1; }

usage() { sed -n '2,48p' "$0" | sed 's/^# \{0,1\}//'; }

while [ "$#" -gt 0 ]; do
  case "$1" in
    --container) CONTAINER="${2:?--container needs a value}"; shift 2 ;;
    --dsn) DSN="${2:?--dsn needs a value}"; shift 2 ;;
    --db) SCRATCH_DB="${2:?--db needs a value}"; shift 2 ;;
    --keep) KEEP=1; shift ;;
    --no-owner) NO_OWNER=1; shift ;;
    --check-tables) CHECK_TABLES="${2?--check-tables needs a value}"; shift 2 ;;
    --require-rows) REQUIRE_ROWS="${2?--require-rows needs a value}"; shift 2 ;;
    --metrics-file) METRICS_FILE="${2:?--metrics-file needs a value}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    --) shift; DUMP="${1:-}"; break ;;
    -*) die "unknown option: $1 (see --help)" ;;
    *) DUMP="$1"; shift ;;
  esac
done

[ -n "$DUMP" ] || { usage; die "dump file (or directory) is required"; }

# A directory → the newest dump inside it (daily/weekly/monthly/last subfolders).
if [ -d "$DUMP" ]; then
  newest="$(find "$DUMP" -type f \( -name '*.sql.gz' -o -name '*.sql' -o -name '*.dump' \) \
              -exec ls -t {} + 2>/dev/null | head -n1 || true)"
  [ -n "$newest" ] || die "no *.sql.gz / *.sql / *.dump files under $DUMP"
  DUMP="$newest"
fi
[ -f "$DUMP" ] && [ -r "$DUMP" ] || die "dump file not readable: $DUMP"
[ -s "$DUMP" ] || die "dump file is empty: $DUMP"

SCRATCH_DB="${SCRATCH_DB:-emsarena_restore_drill_$(date +%Y%m%d_%H%M%S)}"
# Identifier is interpolated into SQL — allow only a safe, unquoted name.
printf '%s' "$SCRATCH_DB" | grep -Eq '^[a-z_][a-z0-9_]{0,62}$' \
  || die "unsafe scratch DB name '$SCRATCH_DB' (use [a-z0-9_], max 63 chars)"
for list in "$CHECK_TABLES" "$REQUIRE_ROWS"; do
  [ -z "$list" ] || printf '%s' "$list" | grep -Eq '^[a-z_][a-z0-9_]*(,[a-z_][a-z0-9_]*)*$' \
    || die "table lists must be comma-separated lowercase identifiers: '$list'"
done

# ── format detection ────────────────────────────────────────────────────────
magic="$(head -c 5 "$DUMP" | od -An -tx1 | tr -d ' \n')"
case "$magic" in
  1f8b*) FORMAT=plain_gz ;;
  5047444d50) FORMAT=custom ;;        # "PGDMP"
  *) FORMAT=plain ;;
esac
if [ "$FORMAT" = plain_gz ]; then
  gzip -t "$DUMP" 2>/dev/null || die "gzip integrity check failed: $DUMP"
fi

# ── connection helpers ──────────────────────────────────────────────────────
if [ -n "$DSN" ]; then
  MODE=dsn
  command -v psql >/dev/null || die "psql not found (needed for --dsn mode)"
  # Build the scratch-DB URI by replacing the path of the maintenance DSN.
  dsn_base="${DSN%%\?*}"
  dsn_query=""
  [ "$dsn_base" = "$DSN" ] || dsn_query="?${DSN#*\?}"
  dsn_scheme="${dsn_base%%://*}"
  dsn_rest="${dsn_base#*://}"
  dsn_authority="${dsn_rest%%/*}"
  SCRATCH_DSN="${dsn_scheme}://${dsn_authority}/${SCRATCH_DB}${dsn_query}"
else
  MODE=container
  command -v docker >/dev/null || die "docker not found (use --dsn for a direct connection)"
  [ "$(docker inspect -f '{{.State.Running}}' "$CONTAINER" 2>/dev/null)" = "true" ] \
    || die "postgres container '$CONTAINER' is not running"
fi

# SQL on the maintenance DB (stdin), unaligned tuples-only output.
admin_sql() {
  if [ "$MODE" = dsn ]; then
    psql -X -q -At -v ON_ERROR_STOP=1 "$DSN"
  else
    docker exec -i "$CONTAINER" sh -c \
      'PGPASSWORD="$POSTGRES_PASSWORD" psql -X -q -At -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d postgres'
  fi
}

# SQL on the scratch DB (stdin). Extra psql args are passed through.
scratch_psql() {
  if [ "$MODE" = dsn ]; then
    psql -X -q -v ON_ERROR_STOP=1 "$@" "$SCRATCH_DSN"
  else
    docker exec -i -e DRILL_DB="$SCRATCH_DB" "$CONTAINER" sh -c \
      'PGPASSWORD="$POSTGRES_PASSWORD" exec psql -X -q -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$DRILL_DB" "$@"' \
      psql "$@"
  fi
}

# Custom-format dump on stdin → pg_restore into the scratch DB.
scratch_pg_restore() {
  local extra=()
  [ "$NO_OWNER" -eq 1 ] && extra=(--no-owner --no-privileges)
  if [ "$MODE" = dsn ]; then
    command -v pg_restore >/dev/null || die "pg_restore not found"
    pg_restore --exit-on-error --single-transaction ${extra[@]+"${extra[@]}"} -d "$SCRATCH_DSN"
  else
    docker exec -i -e DRILL_DB="$SCRATCH_DB" "$CONTAINER" sh -c \
      'PGPASSWORD="$POSTGRES_PASSWORD" exec pg_restore --exit-on-error --single-transaction "$@" -U "$POSTGRES_USER" -d "$DRILL_DB"' \
      pg_restore ${extra[@]+"${extra[@]}"}
  fi
}

# Plain SQL on stdin; --no-owner strips one-line OWNER/GRANT/REVOKE statements
# (pg_dump always emits them on a single line).
plain_filter() {
  if [ "$NO_OWNER" -eq 1 ]; then
    sed -E -e '/^ALTER [A-Z ]+ .* OWNER TO .*;$/d' -e '/^(GRANT|REVOKE) .*;$/d'
  else
    cat
  fi
}

# ── safety: never touch the live DB, never reuse an existing DB ─────────────
if [ "$MODE" = container ]; then
  live_db="$(docker exec "$CONTAINER" sh -c 'printf %s "$POSTGRES_DB"')"
  [ "$SCRATCH_DB" != "$live_db" ] || die "scratch DB must not be the live DB '$live_db'"
fi
exists="$(printf "SELECT 1 FROM pg_database WHERE datname = '%s';\n" "$SCRATCH_DB" | admin_sql)"
[ -z "$exists" ] || die "database '$SCRATCH_DB' already exists — pick another --db (refusing to overwrite)"

CREATED=0
SUCCESS=0
cleanup() {
  local rc=$?
  if [ "$CREATED" -eq 1 ] && { [ "$KEEP" -eq 0 ] || [ "$SUCCESS" -eq 0 ]; }; then
    log "dropping scratch DB $SCRATCH_DB"
    printf 'DROP DATABASE IF EXISTS %s WITH (FORCE);\n' "$SCRATCH_DB" | admin_sql \
      || log "WARNING: could not drop $SCRATCH_DB — drop it by hand"
  fi
  exit "$rc"
}
trap cleanup EXIT
trap 'exit 130' INT TERM

dump_bytes="$(wc -c < "$DUMP" | tr -d ' ')"
# DSN may carry a password — log only the mode, never the URI.
target="$CONTAINER"; [ "$MODE" = dsn ] && target="dsn"
log "dump=$DUMP format=$FORMAT size=${dump_bytes}B mode=$MODE target=$target scratch=$SCRATCH_DB"

t0="$(date +%s)"
printf 'CREATE DATABASE %s;\n' "$SCRATCH_DB" | admin_sql
CREATED=1

# ── restore (atomic: ON_ERROR_STOP + single transaction) ────────────────────
log "restoring…"
case "$FORMAT" in
  plain_gz) gzip -dc "$DUMP" | plain_filter | scratch_psql --single-transaction >/dev/null ;;
  plain)    plain_filter < "$DUMP" | scratch_psql --single-transaction >/dev/null ;;
  custom)   scratch_pg_restore < "$DUMP" ;;
esac
t1="$(date +%s)"
restore_seconds=$((t1 - t0))
log "restore finished in ${restore_seconds}s"

# ── sanity checks ───────────────────────────────────────────────────────────
fail=0
tables_total="$(printf "SELECT count(*) FROM pg_tables WHERE schemaname = 'public';\n" | scratch_psql -At)"
db_size="$(printf 'SELECT pg_size_pretty(pg_database_size(current_database()));\n' | scratch_psql -At)"
log "public tables: $tables_total, restored size: $db_size"
[ "${tables_total:-0}" -gt 0 ] || { log "FAIL: no tables in schema public"; fail=1; }

if [ -n "$CHECK_TABLES$REQUIRE_ROWS" ]; then
  all_tables="$(printf '%s,%s' "$CHECK_TABLES" "$REQUIRE_ROWS" | tr ',' '\n' | awk 'NF && !seen[$0]++')"
  for t in $all_tables; do
    present="$(printf "SELECT to_regclass('public.%s') IS NOT NULL;\n" "$t" | scratch_psql -At)"
    if [ "$present" != "t" ]; then
      log "FAIL: table public.$t is missing"; fail=1; continue
    fi
    rows="$(printf 'SELECT count(*) FROM public.%s;\n' "$t" | scratch_psql -At)"
    printf '  %-32s %s\n' "$t" "$rows" >&2
    case ",$REQUIRE_ROWS," in
      *",$t,"*) [ "$rows" -gt 0 ] || { log "FAIL: public.$t is empty"; fail=1; } ;;
    esac
  done
fi

has_migrations="$(printf "SELECT to_regclass('public.django_migrations') IS NOT NULL;\n" | scratch_psql -At)"
if [ "$has_migrations" = "t" ]; then
  last_mig="$(printf "SELECT app || '.' || name || ' @ ' || to_char(applied, 'YYYY-MM-DD HH24:MI') FROM django_migrations ORDER BY applied DESC, id DESC LIMIT 1;\n" | scratch_psql -At)"
  log "latest migration in dump: ${last_mig:-<none>}"
fi

t2="$(date +%s)"
total_seconds=$((t2 - t0))
[ "$fail" -eq 0 ] || die "sanity checks failed (restore took ${restore_seconds}s)"
SUCCESS=1

if [ -n "$METRICS_FILE" ]; then
  tmp="${METRICS_FILE}.$$"
  {
    echo "# HELP emsarena_restore_drill_last_success_timestamp_seconds Unix time of the last successful restore drill."
    echo "# TYPE emsarena_restore_drill_last_success_timestamp_seconds gauge"
    echo "emsarena_restore_drill_last_success_timestamp_seconds $t2"
    echo "# HELP emsarena_restore_drill_restore_seconds Restore duration of the last successful drill (RTO input)."
    echo "# TYPE emsarena_restore_drill_restore_seconds gauge"
    echo "emsarena_restore_drill_restore_seconds $restore_seconds"
    echo "# HELP emsarena_restore_drill_dump_bytes Size of the dump used by the last successful drill."
    echo "# TYPE emsarena_restore_drill_dump_bytes gauge"
    echo "emsarena_restore_drill_dump_bytes $dump_bytes"
  } > "$tmp" && mv -f "$tmp" "$METRICS_FILE"
fi

if [ "$KEEP" -eq 1 ]; then
  log "KEEPING restored DB '$SCRATCH_DB' (see deployment.md §12 for the rename swap)"
fi
echo "RESTORE DRILL OK: dump=$(basename "$DUMP") format=$FORMAT size=${dump_bytes}B db=$SCRATCH_DB tables=$tables_total restore_seconds=$restore_seconds total_seconds=$total_seconds (RTO ≈ restore + swap + app start)"
