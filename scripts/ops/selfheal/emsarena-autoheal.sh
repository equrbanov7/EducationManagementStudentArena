#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
# EMS Arena — autoheal (systemd: emsarena-autoheal.timer → .service, hər 2 dəq)
# ═══════════════════════════════════════════════════════════════════════════
# Docker `unhealthy` konteyneri ÖZÜ restart etmir (yalnız swarm edir), start-ı
# uğursuz olan konteyneri isə restart siyasəti bir daha cəhd etmir. Bu skript
# hər keçiddə YALNIZ bu compose layihəsinin konteynerlərinə baxır:
#   - `docker ps --filter label=com.docker.compose.project=<layihə>` + ikinci qoruma:
#     `com.docker.compose.project.working_dir` = APP_DIR (başqa stack-a toxunmur);
#   - one-off (`compose run`) konteynerləri və restart siyasəti always/unless-stopped
#     olmayanlar nəzərə alınmır.
# Əməliyyatlar:
#   restart — `running` + `unhealthy` ardıcıl AUTOHEAL_UNHEALTHY_CHECKS (3) keçiddə
#             (state /run-da; ≈ 6+ dəq, healthcheck retries-in üstündən);
#   start   — `exited` və restart siyasəti işləməlidir deyir: start xətası
#             (State.Error), OOM və ya qeyri-səliqəli çıxış kodu; `created`
#             (yarımçıq compose up). Səliqəli/əl ilə stop (kod 0/137/143,
#             xətasız) — toxunulmur (seed/bərpa zamanı yazanlar dayandırılır).
# Təhlükəsizlik limitləri:
#   - deploy/converge kilidi (/run/emsarena/deploy.lock) tutulubsa keçid ötürülür;
#     autoheal öz keçidində kilidi saxlayır (deploy gözləyir);
#   - pauza faylı /run/emsarena/autoheal.pause (6 saatdan köhnəsi nəzərə alınmır);
#   - konteyner başına saatda ən çox AUTOHEAL_MAX_RESTARTS_PER_HOUR (3) əməliyyat;
#   - keçid başına ən çox AUTOHEAL_MAX_ACTIONS_PER_RUN (3), servis başına 1 (rolling);
#   - postgres/redis/postgres-backup unhealthy-yə görə restart OLUNMUR (crash
#     recovery / AOF yüklənməsi kəsilməsin; backup unhealthy = siqnaldır);
#   - postgres və ya redis sağlam deyilsə digər servislərin unhealthy restart-ı
#     gözlədilir (səbəb oradadır);
#   - load1 > AUTOHEAL_LOAD_FACTOR × nüvə → unhealthy restart-lar ötürülür (yük
#     altında healthcheck-in gecikməsi simptomdur; restart yarımçıq sorğuları öldürər);
#   - app/celery image-i sonuncu sağlam release (`emsarena-prod:latest`) deyilsə
#     start edilmir (converge/deploy həll edir).
# Hər əməliyyat jurnala (`journalctl -u emsarena-autoheal`) və
# /run/emsarena/autoheal/actions.log-a yazılır. `--dry-run`: heç nə etmir.
set -euo pipefail

CONF_FILE="${SELFHEAL_CONF:-/etc/default/emsarena-selfheal}"
for conf in "$CONF_FILE" "${CONF_FILE}.local"; do
  if [ -r "$conf" ]; then
    # shellcheck source=/dev/null
    . "$conf"
  fi
done

APP_DIR="${APP_DIR:-/home/wcu/EducationManagementStudentArena}"
COMPOSE_PROJECT="${COMPOSE_PROJECT:-}"
APP_IMAGE_REPOSITORY="${APP_IMAGE_REPOSITORY:-emsarena-prod}"
DEPLOY_LOCK_FILE="${DEPLOY_LOCK_FILE:-/run/emsarena/deploy.lock}"
STATE_DIR="${AUTOHEAL_STATE_DIR:-/run/emsarena/autoheal}"
PAUSE_FILE="${AUTOHEAL_PAUSE_FILE:-/run/emsarena/autoheal.pause}"
NO_RESTART_SERVICES="${AUTOHEAL_NO_RESTART_SERVICES:-postgres redis postgres-backup}"
CORE_SERVICES="${AUTOHEAL_CORE_SERVICES:-postgres redis}"
LOADAVG_FILE="${AUTOHEAL_LOADAVG_FILE:-/proc/loadavg}"
LOAD_FACTOR="${AUTOHEAL_LOAD_FACTOR:-2}"
DRY_RUN="${AUTOHEAL_DRY_RUN:-0}"

log() { printf '[autoheal] %s\n' "$*"; }

# Rəqəmsal parametr: tam ədəd deyilsə defolt (səhv .local konfiqi skripti sındırmasın).
int_or() {
  case "$1" in
    '' | *[!0-9]*) printf '%s' "$2" ;;
    *) printf '%s' "$1" ;;
  esac
}
UNHEALTHY_CHECKS="$(int_or "${AUTOHEAL_UNHEALTHY_CHECKS:-}" 3)"
MAX_PER_HOUR="$(int_or "${AUTOHEAL_MAX_RESTARTS_PER_HOUR:-}" 3)"
MAX_PER_RUN="$(int_or "${AUTOHEAL_MAX_ACTIONS_PER_RUN:-}" 3)"
STOP_TIMEOUT_MAX="$(int_or "${AUTOHEAL_STOP_TIMEOUT_MAX:-}" 120)"
PAUSE_MAX_MINUTES="$(int_or "${AUTOHEAL_PAUSE_MAX_MINUTES:-}" 360)"

case "${1:-}" in
  --dry-run) DRY_RUN=1 ;;
  "") ;;
  *)
    echo "istifadə: $0 [--dry-run]" >&2
    exit 64
    ;;
esac

in_list() {
  case " $2 " in
    *" $1 "*) return 0 ;;
  esac
  return 1
}

action_log() {
  log "$*"
  local file="${STATE_DIR}/actions.log"
  printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" >>"$file" 2>/dev/null || return 0
  if [ "$(wc -l <"$file" | tr -d ' ')" -gt 400 ]; then
    tail -n 200 "$file" >"${file}.tmp" && mv "${file}.tmp" "$file"
  fi
}

# Eyni vəziyyət üçün jurnalı hər 2 dəqiqədə doldurmasın: açar üzrə bir dəfə yazılır.
note_once() {
  local key="$1"
  shift
  [ -e "${STATE_DIR}/noted/${key}" ] && return 0
  : >"${STATE_DIR}/noted/${key}"
  log "$*"
}

safe_name() { printf '%s' "$1" | tr -c 'A-Za-z0-9._-' '_'; }

recent_actions() {
  local file="${STATE_DIR}/restarts/$1" cutoff
  [ -f "$file" ] || {
    echo 0
    return 0
  }
  cutoff=$(($(date +%s) - 3600))
  awk -v c="$cutoff" '$1 >= c' "$file" >"${file}.tmp" || true
  mv "${file}.tmp" "$file"
  wc -l <"$file" | tr -d ' '
}

is_clean_stop_code() {
  case "$1" in
    0 | 137 | 143) return 0 ;;
  esac
  return 1
}

main() {
  umask 027
  mkdir -p "${STATE_DIR}/streak" "${STATE_DIR}/restarts" "${STATE_DIR}/noted"

  if [ -e "$PAUSE_FILE" ]; then
    if [ -n "$(find "$PAUSE_FILE" -mmin "-${PAUSE_MAX_MINUTES}" 2>/dev/null)" ]; then
      log "PAUSE: ${PAUSE_FILE} var — bu keçid ötürülür"
      return 0
    fi
    log "XƏBƏRDARLIQ: pauza faylı ${PAUSE_MAX_MINUTES} dəqiqədən köhnədir — nəzərə alınmır"
  fi

  # Deploy kilidi: deploy/converge gedirsə heç nəyə toxunma.
  if ! command -v flock >/dev/null 2>&1; then
    log "XƏTA: flock yoxdur — deploy ilə koordinasiya mümkün deyil, autoheal işləmir"
    return 1
  fi
  if [ ! -d "${DEPLOY_LOCK_FILE%/*}" ]; then
    log "XƏTA: ${DEPLOY_LOCK_FILE%/*} yoxdur (systemd-tmpfiles / selfheal quraşdırılması) — autoheal işləmir"
    return 1
  fi
  if [ ! -e "$DEPLOY_LOCK_FILE" ]; then
    : >"$DEPLOY_LOCK_FILE" 2>/dev/null || true
  fi
  exec 9<"$DEPLOY_LOCK_FILE"
  if ! flock -n 9; then
    log "SKIP: deploy/converge gedir (kilid ${DEPLOY_LOCK_FILE}) — bu keçid ötürülür"
    return 0
  fi

  if ! docker info >/dev/null 2>&1; then
    log "SKIP: docker cavab vermir — dockerd/converge məsələsidir, keçid ötürülür"
    return 0
  fi
  if [ -z "$COMPOSE_PROJECT" ]; then
    COMPOSE_PROJECT="$(basename "$APP_DIR" | tr '[:upper:]' '[:lower:]')"
  fi

  local overloaded=0 load1 cpus
  if [ -r "$LOADAVG_FILE" ]; then
    load1="$(cut -d' ' -f1 "$LOADAVG_FILE")"
    cpus="$(getconf _NPROCESSORS_ONLN 2>/dev/null || echo 1)"
    if awk -v l="$load1" -v c="$cpus" -v f="$LOAD_FACTOR" 'BEGIN { exit !(l + 0 > c * f) }'; then
      overloaded=1
      log "OVERLOAD: load1=${load1} > ${LOAD_FACTOR}×${cpus} nüvə — bu keçiddə unhealthy restart-lar ötürülür"
    fi
  fi

  local ids inventory latest_id
  # Yalnız bu compose layihəsi — başqa konteynerlərə heç vaxt baxılmır.
  ids="$(docker ps -aq --filter "label=com.docker.compose.project=${COMPOSE_PROJECT}" 2>/dev/null || true)"
  if [ -z "$ids" ]; then
    log "layihə konteyneri yoxdur (${COMPOSE_PROJECT}) — converge/deploy məsələsidir"
    return 0
  fi
  # Sahələr: id|ad|status|health|restart|kod|oom|servis|oneoff|working_dir|teq|image-id|stop_timeout|xəta(son, '|' ola bilər)
  local fmt='{{.Id}}|{{.Name}}|{{.State.Status}}|{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}|{{.HostConfig.RestartPolicy.Name}}|{{.State.ExitCode}}|{{.State.OOMKilled}}|{{index .Config.Labels "com.docker.compose.service"}}|{{index .Config.Labels "com.docker.compose.oneoff"}}|{{index .Config.Labels "com.docker.compose.project.working_dir"}}|{{.Config.Image}}|{{.Image}}|{{if .Config.StopTimeout}}{{.Config.StopTimeout}}{{end}}|{{.State.Error}}'
  # shellcheck disable=SC2086  # qəsdən: id-lər boşluqla ayrılmış siyahıdır
  inventory="$(docker inspect --format "$fmt" $ids 2>/dev/null || true)"
  latest_id="$(docker image inspect --format '{{.Id}}' "${APP_IMAGE_REPOSITORY}:latest" 2>/dev/null || true)"

  local id name status health policy code oom service oneoff workdir image_ref image_id stop_timeout error
  local core_ok=1 core_bad=""
  while IFS='|' read -r id name status health policy code oom service oneoff workdir image_ref image_id stop_timeout error <&3; do
    [ -n "$id" ] || continue
    if [ "$oneoff" = "True" ] || ! in_list "$service" "$CORE_SERVICES"; then
      continue
    fi
    if [ "$status" != "running" ] || { [ "$health" != "healthy" ] && [ "$health" != "none" ]; }; then
      core_ok=0
      core_bad="${core_bad} ${service}:${status}/${health}"
    fi
  done 3<<EOF
$inventory
EOF

  local actions=0 failures=0 touched=" " seen=" " streak want reason recent timeout key rc
  while IFS='|' read -r id name status health policy code oom service oneoff workdir image_ref image_id stop_timeout error <&3; do
    [ -n "$id" ] || continue
    name="${name#/}"
    seen="${seen}${id} "
    [ "$workdir" = "<no value>" ] && workdir=""
    if [ "$oneoff" = "True" ]; then
      continue
    fi
    if [ -n "$workdir" ] && [ "$workdir" != "$APP_DIR" ]; then
      note_once "${id}-foreign" "SKIP: ${name} başqa qovluğun compose layihəsidir (${workdir}) — toxunulmur"
      continue
    fi
    case "$policy" in
      always | unless-stopped) ;;
      *) continue ;;
    esac

    want=""
    reason=""
    case "$status" in
      running)
        if [ "$health" != "unhealthy" ]; then
          rm -f "${STATE_DIR}/streak/${id}" "${STATE_DIR}/noted/${id}"-*
          continue
        fi
        streak=$(($(cat "${STATE_DIR}/streak/${id}" 2>/dev/null || echo 0) + 1))
        if [ "$DRY_RUN" != 1 ]; then
          echo "$streak" >"${STATE_DIR}/streak/${id}"
        fi
        if [ "$streak" -lt "$UNHEALTHY_CHECKS" ]; then
          log "unhealthy (${streak}/${UNHEALTHY_CHECKS}): ${name}"
          continue
        fi
        want=restart
        reason="unhealthy ${streak} ardıcıl yoxlamada"
        ;;
      exited)
        if [ -n "$error" ] || [ "$oom" = "true" ] || ! is_clean_stop_code "$code"; then
          want=start
          reason="exited (kod=${code} oom=${oom}${error:+ xəta=${error}})"
        else
          note_once "${id}-stopped" "INFO: ${name} səliqəli dayandırılıb (kod=${code}) — əl ilə stop sayılır, toxunulmur"
          continue
        fi
        ;;
      created)
        want=start
        reason="created (heç vaxt start olunmayıb — yarımçıq compose up?)"
        ;;
      dead)
        note_once "${id}-dead" "XƏBƏRDARLIQ: ${name} 'dead' vəziyyətdədir — əl ilə baxın"
        continue
        ;;
      *)
        # restarting / paused / removing — docker özü idarə edir.
        continue
        ;;
    esac

    if [ "$want" = restart ]; then
      if in_list "$service" "$NO_RESTART_SERVICES"; then
        note_once "${id}-hold" "HOLD: ${name} (${service}) unhealthy, amma vəziyyətli servisdir — avtomatik restart edilmir (crash recovery / AOF yüklənməsi kəsilməsin); əl ilə baxın"
        continue
      fi
      if [ "$core_ok" = 0 ] && ! in_list "$service" "$CORE_SERVICES"; then
        log "HOLD: ${name} unhealthy, amma əsas servislər sağlam deyil (${core_bad# }) — restart ötürülür"
        continue
      fi
      if [ "$overloaded" = 1 ]; then
        log "HOLD: ${name} unhealthy, server yüklüdür — restart ötürülür"
        continue
      fi
    elif [ "${image_ref%%:*}" = "$APP_IMAGE_REPOSITORY" ] && { [ -z "$latest_id" ] || [ "$image_id" != "$latest_id" ]; }; then
      note_once "${id}-image" "HOLD: ${name} sonuncu SAĞLAM release olmayan image-dədir (${image_ref}) — start edilmir, converge/deploy həll edir"
      continue
    fi

    if in_list "$service" "$touched"; then
      log "HOLD: ${service} üçün bu keçiddə artıq əməliyyat olub — ${name} növbəti keçiddə"
      continue
    fi
    if [ "$actions" -ge "$MAX_PER_RUN" ]; then
      log "HOLD: keçid limiti (${MAX_PER_RUN}) dolub — ${name} növbəti keçiddə"
      continue
    fi
    key="$(safe_name "$name")"
    recent="$(recent_actions "$key")"
    if [ "$recent" -ge "$MAX_PER_HOUR" ]; then
      if [ ! -e "${STATE_DIR}/noted/limit-${key}" ]; then
        : >"${STATE_DIR}/noted/limit-${key}"
        action_log "LIMIT: ${name} son 1 saatda ${recent} dəfə bərpa olunub (maks. ${MAX_PER_HOUR}) — toxunulmur, əl ilə baxın"
      fi
      continue
    fi
    rm -f "${STATE_DIR}/noted/limit-${key}"

    timeout="$(int_or "$stop_timeout" 10)"
    if [ "$timeout" -gt "$STOP_TIMEOUT_MAX" ]; then
      timeout="$STOP_TIMEOUT_MAX"
    fi
    if [ "$DRY_RUN" = 1 ]; then
      log "DRY-RUN: ${want} ${name} (${service}) — ${reason}"
      actions=$((actions + 1))
      touched="${touched}${service} "
      continue
    fi

    rc=0
    if [ "$want" = restart ]; then
      docker restart -t "$timeout" "$id" >/dev/null </dev/null || rc=$?
    else
      docker start "$id" >/dev/null </dev/null || rc=$?
    fi
    if [ "$rc" -eq 0 ]; then
      date +%s >>"${STATE_DIR}/restarts/${key}"
      rm -f "${STATE_DIR}/streak/${id}"
      action_log "ACTION: ${want} ${name} (${service}) — ${reason}"
    else
      action_log "ERROR: ${want} ${name} alınmadı (çıxış ${rc})"
      failures=$((failures + 1))
    fi
    actions=$((actions + 1))
    touched="${touched}${service} "
  done 3<<EOF
$inventory
EOF

  # Artıq olmayan konteynerlərin state faylları (recreate / scale down) silinir.
  local f base
  for f in "${STATE_DIR}"/streak/* "${STATE_DIR}"/noted/*; do
    [ -e "$f" ] || continue
    base="${f##*/}"
    case "$base" in
      limit-*) continue ;;
    esac
    in_list "${base%%-*}" "$seen" || rm -f "$f"
  done

  if [ "$DRY_RUN" = 1 ]; then
    log "keçid bitdi (DRY-RUN, heç nə dəyişdirilmədi): planlanan əməliyyat ${actions}"
  else
    log "keçid bitdi: əməliyyat ${actions}, xəta ${failures}"
  fi
  [ "$failures" -eq 0 ]
}

main
