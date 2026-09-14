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
# REDIS_IMAGE_ENTRYPOINT / REDIS_RENDERED_CONF yalnız test üçün override-dır.
set -eu

: "${REDIS_PASSWORD:?REDIS_PASSWORD is required}"
export REDIS_MAXMEMORY="${REDIS_MAXMEMORY:-3gb}"

REDIS_CONF_DIR="${REDIS_CONF_DIR:-/etc/redis}"
REDIS_RENDERED_CONF="${REDIS_RENDERED_CONF:-/tmp/redis.conf}"
REDIS_IMAGE_ENTRYPOINT="${REDIS_IMAGE_ENTRYPOINT:-docker-entrypoint.sh}"

umask 077
/bin/sh "${REDIS_CONF_DIR}/render-template.sh" \
  "${REDIS_CONF_DIR}/redis.conf.tmpl" "$REDIS_RENDERED_CONF" \
  REDIS_PASSWORD REDIS_MAXMEMORY
chmod 0400 "$REDIS_RENDERED_CONF"
if [ "$(id -u)" = "0" ]; then
  chown redis:redis "$REDIS_RENDERED_CONF"
fi

# Sirr artıq faylda olduğu üçün redis-server prosesinin mühitindən silinir
# (docker-entrypoint.sh / redis-server ona ehtiyac duymur; healthcheck ayrı
# `exec`-dir və compose-un verdiyi REDISCLI_AUTH-u görür).
unset REDIS_PASSWORD

exec "$REDIS_IMAGE_ENTRYPOINT" redis-server "$REDIS_RENDERED_CONF"
