#!/bin/sh
# ═══════════════════════════════════════════════════════════════════════════
# EMS Arena — Redis konteyner start sarğısı (docker-compose.prod.yml `redis`)
# ═══════════════════════════════════════════════════════════════════════════
# 2026-09-14 infra auditi P3-3: parolu argv-dən çıxarır. Axın:
#   1. docker/redis/redis.conf.tmpl → /tmp/redis.conf (render-template.sh,
#      REDIS_PASSWORD / REDIS_MAXMEMORY; `"`/`\` qaçırılır — redis.conf-un
#      ikiqat dırnaq qaydası ilə eynidir);
#   2. fayl 0400 və (root-la başlayıbsa) `redis` istifadəçisinə verilir;
#   3. image-in öz docker-entrypoint.sh-ı `redis-server <conf>` ilə çağırılır —
#      o, /data-nı chown edir və gosu ilə `redis` istifadəçisinə düşür
#      (imtiyaz azaltma əvvəlki kimi qalır). Compose `command`-ı `sh <bu fayl>`
#      olduğu üçün image entrypoint-i əvvəlcə bu skripti root ilə işlədir.
#
# Təhlükəsizlik auditi 2026-10-07: REDIS_MONITOR_PASSWORD doludursa konfiqə
# redis_exporter üçün ACL istifadəçisi `monitor` əlavə olunur — açar yox, kanal
# yox, yalnız PING / INFO / CLIENT SETNAME / SLOWLOG GET|LEN / LATENCY
# LATEST|HISTOGRAM (redis_exporter-in defolt bayraqlarla göndərdiyi əmrlər).
# CONFIG GET QƏSDƏN verilmir: `CONFIG GET requirepass` əsas parolu qaytarır
# (exporter onsuz da işləyir — dbCount defoltu 16, maxmemory INFO-dan gəlir).
# Səhv ACL qaydası redis-server-i «FATAL» ilə dayandırır və bütün tətbiq düşər —
# ona görə sətir əvvəl müvəqqəti, portsuz (unix socket) redis-server-də yoxlanır;
# yoxlama keçməsə (və ya `timeout` yoxdursa) ACL əlavə OLUNMUR və Redis köhnə
# konfiqlə qalxır (exporter-də deploy fallback-i əsas parola qaytarır).
# REDIS_IMAGE_ENTRYPOINT / REDIS_RENDERED_CONF / REDIS_SERVER_BIN yalnız test üçün override-dır.
set -eu

: "${REDIS_PASSWORD:?REDIS_PASSWORD is required}"
export REDIS_MAXMEMORY="${REDIS_MAXMEMORY:-3gb}"

REDIS_CONF_DIR="${REDIS_CONF_DIR:-/etc/redis}"
REDIS_RENDERED_CONF="${REDIS_RENDERED_CONF:-/tmp/redis.conf}"
REDIS_IMAGE_ENTRYPOINT="${REDIS_IMAGE_ENTRYPOINT:-docker-entrypoint.sh}"
REDIS_SERVER_BIN="${REDIS_SERVER_BIN:-redis-server}"

REDIS_MONITOR_USER="monitor"
REDIS_MONITOR_ACL="on resetkeys resetchannels -@all +ping +info +client|setname +slowlog|get +slowlog|len +latency|latest +latency|histogram"

# $1 = parol. Sətri stdout-a yazır (printf builtin-dir — parol argv-də görünmür).
monitor_acl_line() {
  printf 'user %s %s ">%s"\n' "$REDIS_MONITOR_USER" "$REDIS_MONITOR_ACL" "$1"
}

# ACL sətrini ayrıca, portsuz redis-server-də sınayır: konfiq/ACL xətası → exit 1
# dərhal; düzgün konfiq → server işləyir və `timeout` onu SIGTERM ilə dayandırır (0).
monitor_acl_is_valid() {
  command -v timeout >/dev/null 2>&1 || return 1
  check_dir="$(mktemp -d)"
  {
    printf 'port 0\nunixsocket %s/check.sock\nsave ""\nappendonly no\ndir %s\n' "$check_dir" "$check_dir"
    monitor_acl_line "$1"
  } >"${check_dir}/check.conf"
  rc=0
  timeout 2 "$REDIS_SERVER_BIN" "${check_dir}/check.conf" >/dev/null 2>&1 || rc=$?
  rm -rf "$check_dir"
  [ "$rc" -ne 1 ] && [ "$rc" -ne 126 ] && [ "$rc" -ne 127 ]
}

umask 077
/bin/sh "${REDIS_CONF_DIR}/render-template.sh" \
  "${REDIS_CONF_DIR}/redis.conf.tmpl" "$REDIS_RENDERED_CONF" \
  REDIS_PASSWORD REDIS_MAXMEMORY

monitor_password="${REDIS_MONITOR_PASSWORD:-}"
unset REDIS_MONITOR_PASSWORD
if [ -n "$monitor_password" ]; then
  case "$monitor_password" in
    *[!A-Za-z0-9._~-]*) monitor_reason="REDIS_MONITOR_PASSWORD has characters outside [A-Za-z0-9._~-]" ;;
    *) monitor_reason="" ;;
  esac
  if [ -z "$monitor_reason" ] && [ "${#monitor_password}" -lt 16 ]; then
    monitor_reason="REDIS_MONITOR_PASSWORD is shorter than 16 characters"
  fi
  if [ -z "$monitor_reason" ] && ! monitor_acl_is_valid "$monitor_password"; then
    monitor_reason="ACL self-check failed (redis-server rejected the rule or timeout is missing)"
  fi
  if [ -z "$monitor_reason" ]; then
    monitor_acl_line "$monitor_password" >>"$REDIS_RENDERED_CONF"
    echo "redis: read-only ACL user '${REDIS_MONITOR_USER}' enabled for redis_exporter"
  else
    echo "redis: monitor ACL user NOT enabled (${monitor_reason}); starting with the previous config" >&2
  fi
fi
unset monitor_password

chmod 0400 "$REDIS_RENDERED_CONF"
if [ "$(id -u)" = "0" ]; then
  chown redis:redis "$REDIS_RENDERED_CONF"
fi

# Sirr artıq faylda olduğu üçün redis-server prosesinin mühitindən silinir
# (docker-entrypoint.sh / redis-server ona ehtiyac duymur; healthcheck ayrı
# `exec`-dir və compose-un verdiyi REDISCLI_AUTH-u görür).
unset REDIS_PASSWORD

exec "$REDIS_IMAGE_ENTRYPOINT" redis-server "$REDIS_RENDERED_CONF"
