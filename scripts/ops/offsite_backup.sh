#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
# EMSArena — off-site, encrypted backup of DB dumps + media (audit 2026-09-28 AD-01)
#
# Copies to an OFF-HOST restic repository (encrypted client-side, deduplicated):
#   1. ./backups/postgres            postgres-backup sidecar dumps (daily/weekly/monthly/last)
#   2. /var/backups/emsarena         db_backup.sh timestamped dumps
#   3. the `media_data` volume        exam answer files, uploaded documents, correction scans
# then applies retention (forget --prune) and writes a Prometheus textfile
# metric for node_exporter:
#   emsarena_offsite_backup_last_success_timestamp_seconds   (0 = never / not configured)
# The OffsiteBackupStale alert (docker/prometheus/alerts.yml) fires when it is
# older than 26 h — so an unconfigured or broken off-site copy is never silent.
#
# The media volume is mounted READ-ONLY (docker mode: `-v <volume>:/backup/media:ro`;
# host mode: restic only reads the volume mountpoint). Nothing on the host is modified
# except the restic cache and the metrics file.
#
# Configuration (environment, or the env file below — chmod 600, root-owned):
#   OFFSITE_ENV_FILE               default /etc/emsarena/offsite-backup.env (sourced if readable)
#   OFFSITE_RESTIC_REPOSITORY      REQUIRED. e.g. s3:https://s3.example.org/bucket/emsarena,
#                                  sftp:backup@nas.local:/srv/restic/emsarena, rest:https://…,
#                                  b2:bucket:emsarena, rclone:remote:emsarena (rclone → host mode)
#   OFFSITE_RESTIC_PASSWORD_FILE   REQUIRED. file holding the repository encryption password
#                                  (store a copy OFF the server too — without it nothing restores)
#   backend credentials            AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY, B2_ACCOUNT_ID /
#                                  B2_ACCOUNT_KEY, AZURE_*, GOOGLE_*, OS_* … (passed through)
#   OFFSITE_RESTIC_MODE            docker (default: pinned restic image, no host install) | host
#   OFFSITE_RESTIC_IMAGE           default restic/restic:0.18.0
#   OFFSITE_SSH_DIR                docker mode + sftp: directory mounted as /root/.ssh:ro
#   OFFSITE_SIDECAR_DUMPS          default /home/wcu/EducationManagementStudentArena/backups/postgres  ("" = skip)
#   OFFSITE_HOST_DUMPS             default /var/backups/emsarena               ("" = skip)
#   OFFSITE_MEDIA_VOLUME           docker volume name; default: auto-detected from the
#                                  emsarena-nginx /var/www/media mount, else the unique volume
#                                  labelled com.docker.compose.volume=media_data ("" = skip)
#   OFFSITE_HOST_TAG               restic --host value (default emsarena-prod)
#   OFFSITE_KEEP_DAILY/WEEKLY/MONTHLY   retention, default 7 / 4 / 6
#   OFFSITE_RESTIC_CHECK           1 = run `restic check` after pruning (metadata only)
#   OFFSITE_CACHE_DIR              default /var/cache/emsarena-restic
#   OFFSITE_TEXTFILE_DIR           default /var/lib/node_exporter/textfile_collector ("" = off)
#   OFFSITE_LOG                    default /var/log/emsarena-offsite-backup.log
#   OFFSITE_RESTORE_DIR            docker mode: host dir mounted read-write at /restore for
#                                  `restic restore … --target /restore` (see deployment.md §12)
#
# Usage:
#   sudo scripts/ops/offsite_backup.sh            # run = backup + forget --prune (+ metrics)
#   sudo scripts/ops/offsite_backup.sh init       # one-time: create the encrypted repository
#   sudo scripts/ops/offsite_backup.sh snapshots  # list snapshots
#   sudo scripts/ops/offsite_backup.sh check      # verify repository integrity
#   sudo scripts/ops/offsite_backup.sh restic <args…>  # any restic command (e.g. restore)
#
# Exit codes: 0 ok · 1 backup/prune failed · 3 not configured (metric written as 0).
# Schedule: scripts/ops/systemd/emsarena-offsite-backup.{service,timer}.
# ═══════════════════════════════════════════════════════════════════════════
set -euo pipefail

OFFSITE_ENV_FILE="${OFFSITE_ENV_FILE:-/etc/emsarena/offsite-backup.env}"
if [ -r "$OFFSITE_ENV_FILE" ]; then
  set -a
  # shellcheck disable=SC1090
  . "$OFFSITE_ENV_FILE"
  set +a
fi

REPO="${OFFSITE_RESTIC_REPOSITORY:-}"
PASSWORD_FILE="${OFFSITE_RESTIC_PASSWORD_FILE:-}"
MODE="${OFFSITE_RESTIC_MODE:-docker}"
IMAGE="${OFFSITE_RESTIC_IMAGE:-restic/restic:0.18.0}"
SSH_DIR="${OFFSITE_SSH_DIR:-}"
RESTORE_DIR="${OFFSITE_RESTORE_DIR:-}"
SIDECAR_DUMPS="${OFFSITE_SIDECAR_DUMPS-/home/wcu/EducationManagementStudentArena/backups/postgres}"
HOST_DUMPS="${OFFSITE_HOST_DUMPS-/var/backups/emsarena}"
MEDIA_VOLUME="${OFFSITE_MEDIA_VOLUME-auto}"
HOST_TAG="${OFFSITE_HOST_TAG:-emsarena-prod}"
KEEP_DAILY="${OFFSITE_KEEP_DAILY:-7}"
KEEP_WEEKLY="${OFFSITE_KEEP_WEEKLY:-4}"
KEEP_MONTHLY="${OFFSITE_KEEP_MONTHLY:-6}"
RUN_CHECK="${OFFSITE_RESTIC_CHECK:-0}"
CACHE_DIR="${OFFSITE_CACHE_DIR:-/var/cache/emsarena-restic}"
TEXTFILE_DIR="${OFFSITE_TEXTFILE_DIR-/var/lib/node_exporter/textfile_collector}"
LOG="${OFFSITE_LOG:-/var/log/emsarena-offsite-backup.log}"
METRICS_FILE="${TEXTFILE_DIR:+${TEXTFILE_DIR}/emsarena_offsite_backup.prom}"

log() {
  local line
  line="$(date '+%F %T') [offsite_backup] $*"
  echo "$line" >&2
  { echo "$line" >> "$LOG"; } 2>/dev/null || true
}

# ── Prometheus textfile metrics (atomic write; node_exporter reads *.prom) ──
write_metrics() {
  # $1 configured(0|1)  $2 run_ok(0|1)  $3 duration_seconds
  [ -n "$METRICS_FILE" ] || return 0
  local now last_success tmp
  now="$(date +%s)"
  last_success=0
  if [ -r "$METRICS_FILE" ]; then
    last_success="$(awk '$1 == "emsarena_offsite_backup_last_success_timestamp_seconds" {print $2}' "$METRICS_FILE" 2>/dev/null || true)"
    case "$last_success" in ''|*[!0-9]*) last_success=0 ;; esac
  fi
  if [ "$2" -eq 1 ]; then last_success="$now"; fi
  mkdir -p "$TEXTFILE_DIR" 2>/dev/null || { log "WARNING: cannot create $TEXTFILE_DIR"; return 0; }
  tmp="$(mktemp "${TEXTFILE_DIR}/.emsarena_offsite_backup.XXXXXX")" || return 0
  cat > "$tmp" <<EOF
# HELP emsarena_offsite_backup_last_success_timestamp_seconds Unix time of the last successful off-site backup (0 = never or not configured).
# TYPE emsarena_offsite_backup_last_success_timestamp_seconds gauge
emsarena_offsite_backup_last_success_timestamp_seconds ${last_success}
# HELP emsarena_offsite_backup_last_run_timestamp_seconds Unix time of the last off-site backup attempt.
# TYPE emsarena_offsite_backup_last_run_timestamp_seconds gauge
emsarena_offsite_backup_last_run_timestamp_seconds ${now}
# HELP emsarena_offsite_backup_last_run_success 1 if the last off-site backup attempt succeeded, else 0.
# TYPE emsarena_offsite_backup_last_run_success gauge
emsarena_offsite_backup_last_run_success $2
# HELP emsarena_offsite_backup_configured 1 if an off-site repository is configured, else 0.
# TYPE emsarena_offsite_backup_configured gauge
emsarena_offsite_backup_configured $1
# HELP emsarena_offsite_backup_duration_seconds Duration of the last off-site backup attempt.
# TYPE emsarena_offsite_backup_duration_seconds gauge
emsarena_offsite_backup_duration_seconds $3
EOF
  chmod 0644 "$tmp"
  mv -f "$tmp" "$METRICS_FILE"
}

# ── restic invocation (docker image or host binary) ─────────────────────────
MOUNTS=()      # docker mode: -v source:target:ro
PATHS=()       # paths passed to `restic backup`

restic_cmd() {
  if [ "$MODE" = host ]; then
    RESTIC_REPOSITORY="$REPO" RESTIC_PASSWORD_FILE="$PASSWORD_FILE" RESTIC_CACHE_DIR="$CACHE_DIR" \
      restic "$@"
  else
    local envs=() name
    # Backend credentials: pass through by name only (values never hit argv).
    while IFS= read -r name; do
      case "$name" in
        RESTIC_REPOSITORY|RESTIC_PASSWORD_FILE|RESTIC_CACHE_DIR) ;;  # set explicitly below
        AWS_*|B2_*|AZURE_*|GOOGLE_*|OS_*|ST_*|RESTIC_*) envs+=(-e "$name") ;;
      esac
    done < <(compgen -e)
    local ssh_mount=()
    if [ -n "$SSH_DIR" ]; then ssh_mount+=(-v "${SSH_DIR}:/root/.ssh:ro"); fi
    if [ -n "$RESTORE_DIR" ]; then ssh_mount+=(-v "${RESTORE_DIR}:/restore"); fi
    docker run --rm -i \
      --hostname "$HOST_TAG" \
      -e RESTIC_REPOSITORY="$REPO" \
      -e RESTIC_PASSWORD_FILE=/run/secrets/restic_password \
      -e RESTIC_CACHE_DIR=/cache \
      ${envs[@]+"${envs[@]}"} \
      -v "${PASSWORD_FILE}:/run/secrets/restic_password:ro" \
      -v "${CACHE_DIR}:/cache" \
      ${ssh_mount[@]+"${ssh_mount[@]}"} \
      ${MOUNTS[@]+"${MOUNTS[@]}"} \
      "$IMAGE" "$@"
  fi
}

resolve_media_volume() {
  local vol=""
  if [ "$MEDIA_VOLUME" != auto ]; then
    printf '%s' "$MEDIA_VOLUME"; return 0
  fi
  vol="$(docker inspect -f '{{range .Mounts}}{{if eq .Destination "/var/www/media"}}{{.Name}}{{end}}{{end}}' \
           emsarena-nginx 2>/dev/null || true)"
  if [ -z "$vol" ]; then
    local candidates
    candidates="$(docker volume ls -q --filter label=com.docker.compose.volume=media_data 2>/dev/null || true)"
    if [ "$(printf '%s\n' "$candidates" | grep -c .)" -eq 1 ]; then
      vol="$candidates"
    fi
  fi
  printf '%s' "$vol"
}

# Adds one source; a configured-but-missing source is an error (not a silent skip).
add_source() {
  # $1 label  $2 host path (dir)  $3 container path
  [ -n "$2" ] || { log "source $1: skipped (explicitly empty)"; return 0; }
  [ -d "$2" ] || { log "ERROR: source $1: directory $2 not found"; return 1; }
  if [ "$MODE" = host ]; then
    PATHS+=("$2")
  else
    MOUNTS+=(-v "$2:$3:ro")
    PATHS+=("$3")
  fi
}

prepare_sources() {
  local ok=0 vol mp
  add_source postgres-sidecar "$SIDECAR_DUMPS" /backup/postgres-sidecar || ok=1
  # db_backup.sh timer is optional: a MISSING default dir is skipped with a note;
  # an explicitly configured OFFSITE_HOST_DUMPS that is missing is an error.
  if [ -z "${OFFSITE_HOST_DUMPS+x}" ] && [ ! -d "$HOST_DUMPS" ]; then
    log "source postgres-host: $HOST_DUMPS not found (db_backup.sh timer not installed?) — skipped"
  else
    add_source postgres-host "$HOST_DUMPS" /backup/postgres-host || ok=1
  fi
  if [ -z "$MEDIA_VOLUME" ]; then
    log "source media: skipped (OFFSITE_MEDIA_VOLUME is empty)"
  else
    vol="$(resolve_media_volume)"
    if [ -z "$vol" ] || ! docker volume inspect "$vol" >/dev/null 2>&1; then
      log "ERROR: source media: docker volume not found (set OFFSITE_MEDIA_VOLUME)"; ok=1
    elif [ "$MODE" = host ]; then
      mp="$(docker volume inspect -f '{{.Mountpoint}}' "$vol")"
      add_source media "$mp" "" || ok=1
    else
      MOUNTS+=(-v "${vol}:/backup/media:ro")
      PATHS+=(/backup/media)
    fi
  fi
  return "$ok"
}

preflight() {
  if [ -z "$REPO" ]; then
    log "off-site backup NOT CONFIGURED (OFFSITE_RESTIC_REPOSITORY is empty) — host loss = data loss. See deployment.md §12."
    write_metrics 0 0 0
    exit 3
  fi
  if [ -z "$PASSWORD_FILE" ] || [ ! -s "$PASSWORD_FILE" ]; then
    log "ERROR: OFFSITE_RESTIC_PASSWORD_FILE is unset, missing or empty"
    write_metrics 1 0 0
    exit 1
  fi
  case "$MODE" in
    docker) command -v docker >/dev/null || { log "ERROR: docker not found"; write_metrics 1 0 0; exit 1; } ;;
    host) command -v restic >/dev/null || { log "ERROR: restic not found (apt install restic) or use OFFSITE_RESTIC_MODE=docker"; write_metrics 1 0 0; exit 1; } ;;
    *) log "ERROR: OFFSITE_RESTIC_MODE must be docker or host"; write_metrics 1 0 0; exit 1 ;;
  esac
  mkdir -p "$CACHE_DIR"
  chmod 0700 "$CACHE_DIR" 2>/dev/null || true
}

run_backup() {
  local t0 rc=0
  t0="$(date +%s)"
  if ! prepare_sources; then
    rc=1
  fi
  if [ "${#PATHS[@]}" -eq 0 ]; then
    log "ERROR: nothing to back up"; rc=1
  else
    log "backup → repository (mode=$MODE, host=$HOST_TAG): ${PATHS[*]}"
    if ! restic_cmd backup --host "$HOST_TAG" --tag emsarena --exclude-caches "${PATHS[@]}" >>"$LOG" 2>&1; then
      log "ERROR: restic backup failed (details in $LOG)"; rc=1
    fi
  fi
  if [ "$rc" -eq 0 ]; then
    log "retention: keep daily=$KEEP_DAILY weekly=$KEEP_WEEKLY monthly=$KEEP_MONTHLY"
    if ! restic_cmd forget --prune --host "$HOST_TAG" --tag emsarena \
         --keep-daily "$KEEP_DAILY" --keep-weekly "$KEEP_WEEKLY" --keep-monthly "$KEEP_MONTHLY" \
         >>"$LOG" 2>&1; then
      log "ERROR: restic forget --prune failed"; rc=1
    fi
  fi
  if [ "$rc" -eq 0 ] && [ "$RUN_CHECK" = 1 ]; then
    restic_cmd check >>"$LOG" 2>&1 || { log "ERROR: restic check failed"; rc=1; }
  fi
  local dur=$(( $(date +%s) - t0 ))
  if [ "$rc" -eq 0 ]; then
    write_metrics 1 1 "$dur"
    log "OK in ${dur}s"
  else
    write_metrics 1 0 "$dur"
    log "FAILED after ${dur}s"
  fi
  return "$rc"
}

cmd="${1:-run}"
if [ "$#" -gt 0 ]; then shift; fi

# One run at a time (systemd oneshot never overlaps, cron might).
if command -v flock >/dev/null 2>&1; then
  lock_dir=/run/lock; [ -d "$lock_dir" ] || lock_dir=/tmp
  exec 9>"${lock_dir}/emsarena-offsite-backup.lock"
  flock -n 9 || { log "another off-site backup is running — exiting"; exit 1; }
fi

case "$cmd" in
  run) preflight; run_backup ;;
  init) preflight; restic_cmd init ;;
  snapshots) preflight; restic_cmd snapshots --host "$HOST_TAG" ;;
  check) preflight; restic_cmd check "$@" ;;
  restic) preflight; restic_cmd "$@" ;;
  -h|--help|help) sed -n '2,55p' "$0" | sed 's/^# \{0,1\}//' ;;
  *) log "unknown command: $cmd (run|init|snapshots|check|restic)"; exit 2 ;;
esac
