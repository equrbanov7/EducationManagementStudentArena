#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
# EMS Arena — boot converge (systemd: emsarena-converge.service, oneshot)
# ═══════════════════════════════════════════════════════════════════════════
# Sahib 2026-10-07: «elektrik kəsilib server yenidən yananda sistem özü-özünü
# ayağa qaldırsın». Docker restart siyasəti (unless-stopped) konteynerləri özü
# qaldırır, amma: depends_on sırasını gözləmir, start-ı uğursuz olan konteyneri
# (məs. körpü/mount hazır deyil) bir daha cəhd etmir, yarımçıq deploy-un
# «created» konteynerlərinə toxunmur. Bu skript boot-da bir dəfə:
#   1. docker cavab verənə qədər gözləyir;
#   2. app image-ini seçir — HEÇ VAXT test olunmamış image deyil (aşağıya bax);
#   3. deploy ilə eyni əmri işlədir:
#        RUN_RELEASE_ON_START=false APP_IMAGE=<seçilən> docker compose -f
#        docker-compose.prod.yml up -d --no-build [--pull never]
#        --scale app=$APP_REPLICAS --scale celery_worker=$CELERY_REPLICAS
#      (--remove-orphans YOX — converge heç nə silmir);
#   4. uğursuzluqda CONVERGE_TIMEOUT_SECONDS (600 s) bitənə qədər təkrarlayır;
#      çıxış jurnala düşür: `journalctl -u emsarena-converge`.
#
# Image seçimi (remote_deploy.sh «sonuncu SAĞLAM release» qaydası): deploy hər
# release-i `emsarena-prod:<sha>` ilə qurur və `emsarena-prod:latest` teqini
# YALNIZ health-gate keçəndən sonra ona çevirir (promote_release_image). Ona görə:
#   - app/celery konteynerləri `latest`-in image ID-sini işlədirsə → onların öz
#     teqi saxlanılır (compose heç nəyi yenidən yaratmır, sadəcə start edir);
#   - fərqlidirsə (deploy yarımçıq kəsilib, yeni image hələ sübut olunmayıb) →
#     `emsarena-prod:latest` (sonuncu sağlam release) — konteynerlər ondan yenidən
#     yaradılır (deploy-un öz rollback-ı ilə eyni davranış);
#   - `latest` yoxdursa → yalnız hamısının işlətdiyi tək, lokal mövcud teq; o da
#     yoxdursa converge app image-ini start ETMİR (xəta, jurnalda səbəb).
#   `--no-build` + `--pull never` → heç vaxt yeni image qurulmur/çəkilmir.
#   RUN_RELEASE_ON_START=false → boot-da miqrasiya işləmir (deploy kimi).
#
# Deploy kilidi: /run/emsarena/deploy.lock (remote_deploy.sh saxlayır). Kilid
# deploy-dadırsa converge dayanır — deploy stack-ı özü qaldırır.
# Konfiq: /etc/default/emsarena-selfheal (+ .local), scripts/ops/selfheal/install.sh yazır.
# `--check`: heç nə dəyişmədən planı çap edir + `docker compose config -q`.
# Sirr çap olunmur: .env-dən yalnız APP_REPLICAS / CELERY_REPLICAS oxunur,
# compose konfiqi yalnız `-q` ilə yoxlanır.
set -euo pipefail

CONF_FILE="${SELFHEAL_CONF:-/etc/default/emsarena-selfheal}"
for conf in "$CONF_FILE" "${CONF_FILE}.local"; do
  if [ -r "$conf" ]; then
    # shellcheck source=/dev/null
    . "$conf"
  fi
done

APP_DIR="${APP_DIR:-/home/wcu/EducationManagementStudentArena}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
COMPOSE_PROJECT="${COMPOSE_PROJECT:-}"
APP_IMAGE_REPOSITORY="${APP_IMAGE_REPOSITORY:-emsarena-prod}"
DEPLOY_LOCK_FILE="${DEPLOY_LOCK_FILE:-/run/emsarena/deploy.lock}"
CONVERGE_TIMEOUT_SECONDS="${CONVERGE_TIMEOUT_SECONDS:-600}"
CONVERGE_RETRY_SECONDS="${CONVERGE_RETRY_SECONDS:-20}"
CONVERGE_SETTLE_SECONDS="${CONVERGE_SETTLE_SECONDS:-15}"
CONVERGE_LOCK_WAIT_SECONDS="${CONVERGE_LOCK_WAIT_SECONDS:-60}"
IMAGE_SERVICES="app celery_worker celery_worker_heavy celery_beat"

MODE=run
case "${1:-}" in
  --check) MODE=check ;;
  "") ;;
  *)
    echo "istifadə: $0 [--check]" >&2
    exit 64
    ;;
esac

log() { printf '[converge] %s\n' "$*"; }
now() { date +%s; }
DEADLINE=$(($(now) + CONVERGE_TIMEOUT_SECONDS))
remaining() { echo $((DEADLINE - $(now))); }

in_list() {
  case " $2 " in
    *" $1 "*) return 0 ;;
  esac
  return 1
}

# remote_deploy.sh ilə eyni: .env-i shell kimi source ETMİR, yalnız istənən açarı oxuyur.
dotenv_value() {
  local key="$1"
  local value=""
  [ -f "${APP_DIR}/.env" ] || return 0
  value="$(awk -v wanted="${key}" '
    index($0, wanted "=") == 1 { value = substr($0, length(wanted) + 2) }
    END { print value }
  ' "${APP_DIR}/.env")"
  value="${value%$'\r'}"
  if [[ "$value" == \"*\" && "$value" == *\" ]]; then
    value="${value:1:${#value}-2}"
  elif [[ "$value" == \'*\' && "$value" == *\' ]]; then
    value="${value:1:${#value}-2}"
  fi
  printf '%s' "$value"
}

wait_for_docker() {
  local waited=0
  until docker info >/dev/null 2>&1; do
    if [ "$(remaining)" -le 0 ]; then
      log "XƏTA: docker ${CONVERGE_TIMEOUT_SECONDS} s ərzində cavab vermədi (systemctl status docker)"
      return 1
    fi
    if [ $((waited % 30)) -eq 0 ]; then
      log "docker gözlənilir (${waited} s)..."
    fi
    sleep 5
    waited=$((waited + 5))
  done
  log "docker hazırdır (${waited} s gözlənildi)"
}

# Layihənin image daşıyan konteynerləri (istənilən vəziyyətdə): "servis|teq|image-id" sətirləri.
image_service_containers() {
  local ids
  ids="$(docker ps -aq --filter "label=com.docker.compose.project=${COMPOSE_PROJECT}" 2>/dev/null || true)"
  [ -n "$ids" ] || return 0
  # shellcheck disable=SC2086  # qəsdən: id-lər boşluqla ayrılmış siyahıdır
  docker inspect --format '{{index .Config.Labels "com.docker.compose.service"}}|{{index .Config.Labels "com.docker.compose.oneoff"}}|{{.Config.Image}}|{{.Image}}' $ids 2>/dev/null |
    while IFS='|' read -r service oneoff ref id; do
      if [ "$oneoff" = "True" ] || ! in_list "$service" "$IMAGE_SERVICES"; then
        continue
      fi
      printf '%s|%s|%s\n' "$service" "$ref" "$id"
    done || true
}

resolve_app_image() {
  local latest_ref="${APP_IMAGE_REPOSITORY}:latest"
  local latest_id rows refs ids
  latest_id="$(docker image inspect --format '{{.Id}}' "$latest_ref" 2>/dev/null || true)"
  rows="$(image_service_containers)"
  refs="$(printf '%s\n' "$rows" | awk -F'|' 'NF >= 3 {print $2}' | sort -u)"
  ids="$(printf '%s\n' "$rows" | awk -F'|' 'NF >= 3 {print $3}' | sort -u)"

  if [ -n "$latest_id" ]; then
    if [ -z "$rows" ]; then
      APP_IMAGE="$latest_ref"
      log "image: app/celery konteyneri yoxdur → sonuncu sağlam release ${latest_ref}"
    elif [ "$ids" = "$latest_id" ] && [ "$(printf '%s\n' "$refs" | wc -l | tr -d ' ')" = "1" ]; then
      APP_IMAGE="$refs"
      log "image: konteynerlər sonuncu sağlam release-i işlədir (${APP_IMAGE} = ${latest_ref}) → yenidən yaradılmır"
    else
      APP_IMAGE="$latest_ref"
      log "XƏBƏRDARLIQ: app/celery konteynerləri sonuncu sağlam release olmayan image-dədir ($(printf '%s' "$refs" | tr '\n' ' ')) — yarımçıq deploy? → ${latest_ref}-dən yenidən yaradılır"
    fi
    return 0
  fi

  if [ -n "$rows" ] && [ "$(printf '%s\n' "$refs" | wc -l | tr -d ' ')" = "1" ] &&
    docker image inspect "$refs" >/dev/null 2>&1; then
    APP_IMAGE="$refs"
    log "XƏBƏRDARLIQ: ${latest_ref} teqi yoxdur — konteynerlərin işlətdiyi ${APP_IMAGE} saxlanılır (başqa image start olunmur)"
    return 0
  fi
  log "XƏTA: ${latest_ref} yoxdur və işləyən tək app image-i tapılmadı — test olunmamış image start EDİLMİR. Deploy-u yenidən işlədin."
  return 1
}

LOCK_OPEN=0
open_deploy_lock() {
  local dir="${DEPLOY_LOCK_FILE%/*}"
  if ! command -v flock >/dev/null 2>&1; then
    log "XƏBƏRDARLIQ: flock yoxdur — deploy kilidi yoxlanmadan davam edilir"
    return 0
  fi
  if [ ! -d "$dir" ]; then
    log "XƏBƏRDARLIQ: ${dir} yoxdur (systemd-tmpfiles / selfheal quraşdırılması) — kilidsiz davam edilir"
    return 0
  fi
  if [ ! -e "$DEPLOY_LOCK_FILE" ]; then
    : >"$DEPLOY_LOCK_FILE" 2>/dev/null || true
  fi
  if [ -r "$DEPLOY_LOCK_FILE" ]; then
    exec 9<"$DEPLOY_LOCK_FILE"
    LOCK_OPEN=1
  fi
}

compose_up() {
  local left="$1"
  shift
  if command -v timeout >/dev/null 2>&1; then
    timeout --kill-after=30 "$left" docker compose -f "$COMPOSE_FILE" "$@"
  else
    docker compose -f "$COMPOSE_FILE" "$@"
  fi
}

report_not_running() {
  local ids
  ids="$(docker ps -aq --filter "label=com.docker.compose.project=${COMPOSE_PROJECT}" 2>/dev/null || true)"
  [ -n "$ids" ] || return 0
  # shellcheck disable=SC2086  # qəsdən: id-lər boşluqla ayrılmış siyahıdır
  docker inspect --format '{{.Name}} {{.State.Status}} {{index .Config.Labels "com.docker.compose.oneoff"}}' $ids 2>/dev/null |
    awk '$2 != "running" && $3 != "True" {sub("^/", "", $1); print "  işləmir: " $1 " (" $2 ")"}' || true
}

main() {
  if ! [[ "$CONVERGE_TIMEOUT_SECONDS" =~ ^[0-9]+$ ]] || ! [[ "$CONVERGE_RETRY_SECONDS" =~ ^[0-9]+$ ]]; then
    log "XƏTA: CONVERGE_TIMEOUT_SECONDS / CONVERGE_RETRY_SECONDS tam ədəd olmalıdır"
    return 1
  fi
  log "başladı (rejim: ${MODE}, APP_DIR=${APP_DIR}, limit ${CONVERGE_TIMEOUT_SECONDS} s)"
  wait_for_docker || return 1
  if [ "$MODE" = run ] && [ "$CONVERGE_SETTLE_SECONDS" -gt 0 ] 2>/dev/null; then
    # dockerd boot-da restart siyasəti olan konteynerləri özü qaldırır — onunla yarışmayaq.
    sleep "$CONVERGE_SETTLE_SECONDS"
  fi

  cd "$APP_DIR" || {
    log "XƏTA: APP_DIR tapılmadı: ${APP_DIR}"
    return 1
  }
  if [ ! -f "$COMPOSE_FILE" ] || [ ! -r .env ]; then
    log "XƏTA: ${APP_DIR}/${COMPOSE_FILE} və ya oxunaqlı .env yoxdur"
    return 1
  fi
  if ! docker compose version >/dev/null 2>&1; then
    log "XƏTA: 'docker compose' plugini işləmir"
    return 1
  fi
  if [ -z "$COMPOSE_PROJECT" ]; then
    COMPOSE_PROJECT="$(basename "$APP_DIR" | tr '[:upper:]' '[:lower:]')"
  fi

  local app_replicas celery_replicas
  app_replicas="$(dotenv_value APP_REPLICAS)"
  app_replicas="${app_replicas:-8}"
  celery_replicas="$(dotenv_value CELERY_REPLICAS)"
  celery_replicas="${celery_replicas:-2}"
  if ! [[ "$app_replicas" =~ ^[0-9]+$ ]] || [ "$app_replicas" -lt 1 ] || ! [[ "$celery_replicas" =~ ^[0-9]+$ ]]; then
    log "XƏTA: .env APP_REPLICAS / CELERY_REPLICAS tam ədəd deyil"
    return 1
  fi

  resolve_app_image || return 1
  export APP_IMAGE
  export RUN_RELEASE_ON_START=false

  local -a up_args=(up -d --no-build)
  if docker compose up --help 2>/dev/null | grep -q -- '--pull'; then
    up_args+=(--pull never)
  fi
  up_args+=(--scale "app=${app_replicas}" --scale "celery_worker=${celery_replicas}")
  log "plan: APP_IMAGE=${APP_IMAGE} RUN_RELEASE_ON_START=false docker compose -f ${COMPOSE_FILE} ${up_args[*]} (layihə ${COMPOSE_PROJECT})"

  if [ "$MODE" = check ]; then
    if docker compose -f "$COMPOSE_FILE" config -q; then
      log "check: compose konfiqi keçərlidir (config -q); heç nə dəyişdirilmədi"
      return 0
    fi
    log "XƏTA: docker compose config -q uğursuz oldu"
    return 1
  fi

  open_deploy_lock
  local attempt=1 rc left
  while true; do
    left="$(remaining)"
    if [ "$left" -le 0 ]; then
      log "XƏTA: ${CONVERGE_TIMEOUT_SECONDS} s ərzində converge alınmadı — journalctl -u emsarena-converge; autoheal davam edir"
      return 1
    fi
    if [ "$LOCK_OPEN" = 1 ] && ! flock -w "$CONVERGE_LOCK_WAIT_SECONDS" 9; then
      log "deploy kilidi (${DEPLOY_LOCK_FILE}) başqasındadır — deploy stack-ı özü qaldırır, converge dayanır"
      return 0
    fi
    log "cəhd ${attempt}: docker compose up (qalan ${left} s)"
    rc=0
    compose_up "$left" "${up_args[@]}" || rc=$?
    if [ "$LOCK_OPEN" = 1 ]; then
      flock -u 9 || true
    fi
    if [ "$rc" -eq 0 ]; then
      log "converge tamamlandı (cəhd ${attempt})"
      report_not_running
      return 0
    fi
    log "cəhd ${attempt} uğursuz (çıxış ${rc}); ${CONVERGE_RETRY_SECONDS} s sonra təkrar"
    attempt=$((attempt + 1))
    sleep "$CONVERGE_RETRY_SECONDS"
  done
}

main
