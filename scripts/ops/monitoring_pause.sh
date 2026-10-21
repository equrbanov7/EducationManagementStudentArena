#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
# EMS Arena — ağır monitorinq konteynerlərinin pauzası (sahib 2026-10-21)
# ═══════════════════════════════════════════════════════════════════════════
# «Sistemin yüklənməsində əsas yüklərdən biri monitorinqə görə ola bilər — əgər sistemi çox yükləsə, onu
# söndürmək də olsun.» Web tətbiq konteynerləri dayandıra BİLMƏZ (docker-socket-proxy yalnız GET-dir, qəsdən);
# bu skripti sahib .github/workflows/prod-host-maint.yml (action=monitoring-pause / monitoring-resume) ilə işə
# salır.
#
# Dayandırılanlar (PAUSE_SERVICES) — kritik olmayan, CPU/yaddaşı log həcmi və konteyner sayı ilə artanlar:
#   cadvisor            konteyner metrikləri (privileged; ən ağır exporter)
#   promtail            konteyner loglarının toplanması (pik yükdə sətir sayı ilə artır)
#   docker-socket-proxy yalnız promtail-ə xidmət edir (log axınlarını proxy-ləyir)
#   loki                log saxlama/indeks
#   grafana             yalnız əl ilə baxış üçün UI (alert vermir)
# İŞLƏMƏYƏ DAVAM EDİR: prometheus + alertmanager (bütün kəsinti alertləri, Watchdog), node_exporter (host
# CPU/RAM/disk + bu markerin özü), blackbox (sayt əlçatanlığı), postgres/redis/pgbouncer/nginx exporterləri
# (PostgresDown/RedisDown/NginxDown/PgBouncer alertləri). İmtahan nəzarəti tətbiqin içindədir — təsir yoxdur.
#
# Marker: node_exporter textfile kollektoruna `emsarena_monitoring_paused 1` (+ başlama vaxtı) yazılır —
# alerts.yml TargetDown/ContainerDown/LogIngestionStalled qəsdən dayanan hədəflər üçün yalançı yanmasın,
# MonitoringPausedTooLong 12 saatdan sonra xatırlatsın. Marker konteynerlər dayanmazdan ƏVVƏL yazılır və
# Prometheus onu bir scrape + qiymətləndirmə ərzində (MARKER_WAIT_SECONDS) görür.
#
# Geri qaytarma: `resume` (və ya istənilən deploy — remote_deploy.sh `up -d` dayanan konteynerləri qaldırır və
# markeri silir; reboot-dan sonra boot converge də qaldırır, marker qalarsa MonitoringPauseMarkerStale yanır).
# autoheal səliqəli dayandırılmış konteynerə (çıxış 0/137/143, xətasız) toxunmur — pauza öz-özünə pozulmur.
#
# İstifadə: monitoring_pause.sh pause|resume|status|clear-marker [--dry-run]
# Mühit: APP_DIR, COMPOSE_FILE, TEXTFILE_DIR, HELPER_IMAGE, MARKER_WAIT_SECONDS, PAUSE_SERVICES.
# Sirr oxunmur/çap olunmur (.env-ə toxunulmur; compose yalnız stop/up/ps).
set -euo pipefail

APP_DIR="${APP_DIR:-/home/wcu/EducationManagementStudentArena}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
TEXTFILE_DIR="${TEXTFILE_DIR:-/var/lib/node_exporter/textfile_collector}"
MARKER_NAME="monitoring_pause.prom"
HELPER_IMAGE="${HELPER_IMAGE:-postgres:16-alpine}"
MARKER_WAIT_SECONDS="${MARKER_WAIT_SECONDS:-45}"
PAUSE_SERVICES="${PAUSE_SERVICES:-cadvisor promtail docker-socket-proxy loki grafana}"
DRY_RUN=0

log() { printf '[monitoring-pause] %s\n' "$*"; }

usage() {
  echo "istifadə: $0 pause|resume|status|clear-marker [--dry-run]" >&2
  exit 64
}

MODE="${1:-}"
case "$MODE" in
  pause | resume | status | clear-marker) ;;
  *) usage ;;
esac
case "${2:-}" in
  --dry-run) DRY_RUN=1 ;;
  "") ;;
  *) usage ;;
esac
case "$MARKER_WAIT_SECONDS" in
  '' | *[!0-9]*) MARKER_WAIT_SECONDS=45 ;;
esac

# İcazəli servis adları — PAUSE_SERVICES-ə kritik servis (app/postgres/prometheus/…) səhvən yazılmasın.
ALLOWED_SERVICES="cadvisor promtail docker-socket-proxy loki grafana"
read -r -a SERVICES <<<"$PAUSE_SERVICES"
for service in "${SERVICES[@]}"; do
  case " $ALLOWED_SERVICES " in
    *" $service "*) ;;
    *)
      log "XƏTA: '${service}' pauza edilə bilən servis deyil (icazəli: ${ALLOWED_SERVICES})"
      exit 65
      ;;
  esac
done
[ "${#SERVICES[@]}" -gt 0 ] || {
  log "XƏTA: PAUSE_SERVICES boşdur"
  exit 65
}

run() {
  if [ "$DRY_RUN" = 1 ]; then
    log "dry-run: $*"
    return 0
  fi
  "$@"
}

compose() { docker compose -f "$COMPOSE_FILE" "$@"; }

# Runner istifadəçisinin sudo-su yoxdur — host qovluğuna docker (root) ilə yazılır (remote_deploy.sh
# ensure_textfile_collector_dir ilə eyni üsul). Yazı atomikdir: node_exporter yalnız *.prom oxuyur.
write_marker() {
  local now
  now="$(date +%s)"
  run docker run --rm --user 0 --network none --entrypoint sh -v "${TEXTFILE_DIR}:/tf" "$HELPER_IMAGE" -c "
    set -e
    printf '%s\n' \
      '# HELP emsarena_monitoring_paused 1 while heavy monitoring containers are paused (prod-host-maint monitoring-pause).' \
      '# TYPE emsarena_monitoring_paused gauge' \
      'emsarena_monitoring_paused 1' \
      '# HELP emsarena_monitoring_paused_since_timestamp_seconds Unix time the monitoring pause started.' \
      '# TYPE emsarena_monitoring_paused_since_timestamp_seconds gauge' \
      'emsarena_monitoring_paused_since_timestamp_seconds ${now}' >/tf/.${MARKER_NAME}.tmp
    chmod 0644 /tf/.${MARKER_NAME}.tmp
    mv /tf/.${MARKER_NAME}.tmp /tf/${MARKER_NAME}"
}

remove_marker() {
  run docker run --rm --user 0 --network none --entrypoint sh -v "${TEXTFILE_DIR}:/tf" "$HELPER_IMAGE" \
    -c "rm -f /tf/${MARKER_NAME} /tf/.${MARKER_NAME}.tmp"
}

marker_state() {
  if [ -f "${TEXTFILE_DIR}/${MARKER_NAME}" ]; then
    echo "marker: VAR (${TEXTFILE_DIR}/${MARKER_NAME})"
    grep -E '^emsarena_' "${TEXTFILE_DIR}/${MARKER_NAME}" || true
  else
    echo "marker: yoxdur"
  fi
}

show_status() {
  echo "--- monitorinq konteynerləri"
  compose ps --all --format '{{.Service}}  {{.State}}  {{.Status}}' "${SERVICES[@]}" prometheus alertmanager \
    node_exporter blackbox_exporter 2>/dev/null || compose ps "${SERVICES[@]}" || true
  echo "--- $(marker_state)"
}

cd "$APP_DIR"
[ -f "$COMPOSE_FILE" ] || {
  log "XƏTA: ${APP_DIR}/${COMPOSE_FILE} tapılmadı"
  exit 66
}

case "$MODE" in
  pause)
    [ -d "$TEXTFILE_DIR" ] || {
      log "XƏTA: ${TEXTFILE_DIR} yoxdur (deploy ensure_textfile_collector_dir yaradır) — marker yazılmadan pauza alertləri yandırardı"
      exit 67
    }
    log "1/3 marker yazılır (alertlər qəsdən dayanan hədəfləri susdursun)"
    write_marker
    log "2/3 ${MARKER_WAIT_SECONDS} s gözlənilir — Prometheus markeri scrape edib qaydaları qiymətləndirsin"
    [ "$DRY_RUN" = 1 ] || sleep "$MARKER_WAIT_SECONDS"
    log "3/3 dayandırılır: ${SERVICES[*]}"
    run compose stop -t 30 "${SERVICES[@]}"
    show_status
    log "hazır: geri qaytarmaq üçün prod-host-maint.yml action=monitoring-resume (və ya növbəti deploy)"
    ;;
  resume)
    log "1/3 qaldırılır: ${SERVICES[*]} (--no-deps: prometheus/app-a toxunulmur)"
    run compose up -d --no-deps "${SERVICES[@]}"
    log "2/3 ${MARKER_WAIT_SECONDS} s gözlənilir — hədəflər yenidən scrape olunsun (marker silinəndə alert yanmasın)"
    [ "$DRY_RUN" = 1 ] || sleep "$MARKER_WAIT_SECONDS"
    log "3/3 marker silinir"
    remove_marker
    show_status
    ;;
  status)
    show_status
    ;;
  clear-marker)
    remove_marker
    echo "--- $(marker_state)"
    ;;
esac
