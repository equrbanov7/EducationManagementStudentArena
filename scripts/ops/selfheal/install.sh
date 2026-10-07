#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
# EMS Arena — selfheal quraşdırıcısı (HOST-da root ilə; idempotent)
# ═══════════════════════════════════════════════════════════════════════════
# .github/workflows/prod-host-maint.yml → action `selfheal` bunu sudo-suz,
# privileged konteynerdən `nsenter -t 1` ilə host namespace-lərində işlədir:
#   host bash "$GITHUB_WORKSPACE/scripts/ops/selfheal/install.sh" --app-dir … --source …
# Quraşdırır:
#   /usr/local/sbin/emsarena-{converge,autoheal}.sh
#   /etc/systemd/system/emsarena-converge.service   (enabled, boot-da bir dəfə)
#   /etc/systemd/system/emsarena-autoheal.{service,timer} (timer enabled + başladılır)
#   /etc/default/emsarena-selfheal                  (APP_DIR, layihə adı, kilid yolu — sirr yoxdur)
#   /etc/tmpfiles.d/emsarena.conf                   (/run/emsarena: deploy kilidi + autoheal state)
# Vahidlər deploy-u işlədən istifadəçi ilə işləyir (APP_DIR/.env sahibi, docker
# qrupunda); o tapılmasa root. Sonda converge `--check` və autoheal `--dry-run`
# işlədilir — heç bir konteynerə toxunulmur.
# `--disable`: timer + converge söndürülür (fayllar qalır; geri qaytarmaq üçün yenidən install).
# Heç bir sirr çap olunmur (.env oxunmur; yalnız onun sahibi `stat` ilə).
set -euo pipefail

APP_DIR="/home/wcu/EducationManagementStudentArena"
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ACTION=install

usage() {
  echo "istifadə: $0 [--app-dir DIR] [--source DIR] [--disable]" >&2
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --app-dir)
      APP_DIR="${2:?--app-dir qovluq tələb edir}"
      shift 2
      ;;
    --source)
      SRC_DIR="${2:?--source qovluq tələb edir}"
      shift 2
      ;;
    --disable)
      ACTION=disable
      shift
      ;;
    *)
      usage
      exit 64
      ;;
  esac
done

SBIN=/usr/local/sbin
UNIT_DIR=/etc/systemd/system
CONF=/etc/default/emsarena-selfheal
TMPFILES=/etc/tmpfiles.d/emsarena.conf
RUN_DIR=/run/emsarena

if [ "$(id -u)" -ne 0 ]; then
  echo "root lazımdır (prod-host-maint.yml host() — nsenter ilə işlədir)" >&2
  exit 1
fi

if [ "$ACTION" = disable ]; then
  echo "--- selfheal söndürülür"
  systemctl disable --now emsarena-autoheal.timer 2>&1 || true
  systemctl disable emsarena-converge.service 2>&1 || true
  printf 'emsarena-converge.service: %s\n' "$(systemctl is-enabled emsarena-converge.service 2>/dev/null || echo yox)"
  printf 'emsarena-autoheal.timer:   %s\n' "$(systemctl is-enabled emsarena-autoheal.timer 2>/dev/null || echo yox)"
  exit 0
fi

if ! [[ "$APP_DIR" =~ ^/[A-Za-z0-9._/-]+$ ]] || [ ! -d "$APP_DIR" ]; then
  echo "APP_DIR etibarsızdır və ya yoxdur: ${APP_DIR}" >&2
  exit 1
fi
for f in emsarena-converge.sh emsarena-autoheal.sh emsarena-converge.service emsarena-autoheal.service emsarena-autoheal.timer; do
  if [ ! -r "${SRC_DIR}/${f}" ]; then
    echo "mənbə faylı yoxdur: ${SRC_DIR}/${f}" >&2
    exit 1
  fi
  case "$f" in
    *.sh)
      if ! bash -n "${SRC_DIR}/${f}"; then
        echo "sintaksis xətası: ${f}" >&2
        exit 1
      fi
      ;;
  esac
done

# 1) Vahidləri kim işlədir: deploy-un istifadəçisi (.env sahibi — remote_deploy.sh onu 600 edir).
owner="$(stat -c %U "${APP_DIR}/.env" 2>/dev/null || stat -c %U "$APP_DIR")"
RUN_AS=root
if [ -n "$owner" ] && [ "$owner" != root ] && [[ "$owner" =~ ^[a-z_][a-z0-9_-]*$ ]] &&
  id -nG "$owner" 2>/dev/null | tr ' ' '\n' | grep -qx docker; then
  RUN_AS="$owner"
fi
RUN_GROUP=root
if getent group docker >/dev/null 2>&1; then
  RUN_GROUP=docker
fi
RUN_HOME="$(getent passwd "$RUN_AS" | cut -d: -f6)"
RUN_HOME="${RUN_HOME:-/root}"

# 2) Compose layihə adı — işləyən postgres konteynerinin etiketindən (deploy-un istifadə etdiyi ad).
PROJECT="$(docker inspect --format '{{index .Config.Labels "com.docker.compose.project"}}' emsarena-postgres 2>/dev/null || true)"
if [ -z "$PROJECT" ] || [ "$PROJECT" = "<no value>" ] || ! [[ "$PROJECT" =~ ^[a-z0-9][a-z0-9_-]*$ ]]; then
  PROJECT="$(basename "$APP_DIR" | tr '[:upper:]' '[:lower:]')"
fi

echo "--- selfheal quraşdırılır"
echo "APP_DIR=${APP_DIR} · layihə=${PROJECT} · vahidlər ${RUN_AS} istifadəçisi ilə · /run qrupu ${RUN_GROUP}"

STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT

put_file() {
  local src="$1" dst="$2" mode="$3"
  if [ -f "$dst" ] && cmp -s "$src" "$dst"; then
    echo "  eynidir:   ${dst}"
    return 0
  fi
  install -D -m "$mode" -o root -g root "$src" "$dst"
  echo "  yeniləndi: ${dst}"
}

put_file "${SRC_DIR}/emsarena-converge.sh" "${SBIN}/emsarena-converge.sh" 0755
put_file "${SRC_DIR}/emsarena-autoheal.sh" "${SBIN}/emsarena-autoheal.sh" 0755
for unit in emsarena-converge.service emsarena-autoheal.service emsarena-autoheal.timer; do
  sed "s|@RUN_AS@|${RUN_AS}|g" "${SRC_DIR}/${unit}" >"${STAGE}/${unit}"
  put_file "${STAGE}/${unit}" "${UNIT_DIR}/${unit}" 0644
done

cat >"${STAGE}/conf" <<EOF
# /etc/default/emsarena-selfheal — scripts/ops/selfheal/install.sh yaradıb (prod-host-maint → selfheal).
# Yenidən quraşdırmada üzərinə yazılır; öz dəyişikliklərinizi ${CONF}.local-a yazın
# (məs. AUTOHEAL_MAX_RESTARTS_PER_HOUR=3, AUTOHEAL_UNHEALTHY_CHECKS=3). Sirr saxlamır.
APP_DIR=${APP_DIR}
COMPOSE_FILE=docker-compose.prod.yml
COMPOSE_PROJECT=${PROJECT}
APP_IMAGE_REPOSITORY=emsarena-prod
DEPLOY_LOCK_FILE=${RUN_DIR}/deploy.lock
AUTOHEAL_STATE_DIR=${RUN_DIR}/autoheal
AUTOHEAL_PAUSE_FILE=${RUN_DIR}/autoheal.pause
EOF
put_file "${STAGE}/conf" "$CONF" 0644

# /run tmpfs-dir — hər boot-da systemd-tmpfiles yenidən yaradır (deploy kilidi + autoheal state).
printf 'd %s 0775 %s %s -\n' "$RUN_DIR" "$RUN_AS" "$RUN_GROUP" >"${STAGE}/tmpfiles"
put_file "${STAGE}/tmpfiles" "$TMPFILES" 0644
systemd-tmpfiles --create "$TMPFILES"

systemctl daemon-reload
systemd-analyze verify "${UNIT_DIR}/emsarena-converge.service" "${UNIT_DIR}/emsarena-autoheal.service" \
  "${UNIT_DIR}/emsarena-autoheal.timer" 2>&1 | grep -v -i 'docker\|snap' | head -10 || true

as_run_user() {
  if [ "$RUN_AS" = root ]; then
    "$@"
  else
    runuser -u "$RUN_AS" -- env HOME="$RUN_HOME" "$@"
  fi
}

echo "--- converge --check (heç nə dəyişmir)"
as_run_user "${SBIN}/emsarena-converge.sh" --check 2>&1 | tail -n 12 || echo "converge --check uğursuz — yuxarıdakı səbəbə baxın"
echo "--- autoheal --dry-run (heç nə dəyişmir)"
as_run_user "${SBIN}/emsarena-autoheal.sh" --dry-run 2>&1 | tail -n 20 || true

systemctl enable emsarena-converge.service 2>&1 | tail -n 2
systemctl enable --now emsarena-autoheal.timer 2>&1 | tail -n 2

echo "--- nəticə"
printf 'emsarena-converge.service: %s\n' "$(systemctl is-enabled emsarena-converge.service 2>/dev/null || echo yox)"
printf 'emsarena-autoheal.timer:   %s / %s\n' "$(systemctl is-enabled emsarena-autoheal.timer 2>/dev/null || echo yox)" \
  "$(systemctl is-active emsarena-autoheal.timer 2>/dev/null || echo yox)"
systemctl list-timers emsarena-autoheal.timer --all --no-pager 2>/dev/null | head -n 3 || true
ls -ld "$RUN_DIR"
