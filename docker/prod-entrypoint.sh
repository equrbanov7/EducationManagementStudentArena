#!/bin/sh
# ═══════════════════════════════════════════════════════════════════════════
# EMS Arena — Production container entrypoint
# ═══════════════════════════════════════════════════════════════════════════
# 1. Optionally run database migrations and collect static files. The deploy
#    script runs this once before scaling app replicas; direct compose users
#    keep the old safe default by leaving RUN_RELEASE_ON_START=true.
# 2. Exec the ASGI server as PID 1 so Docker signals (SIGTERM/SIGINT) are
#    forwarded directly to it for graceful shutdown.
#
# ASGI_SERVER=daphne (DEFOLT, prod dəyişmir) — tək Daphne prosesi.
# ASGI_SERVER=uvicorn (opt-in, A/B) — ASGI_WORKERS sayda uvicorn worker prosesi
#   (GIL-i aşmaq üçün konteyner başına >1 nüvə). Daphne ilə eyni müştəri İP-si,
#   WS limitləri və graceful-shutdown büdcəsi. Bax docs/operations/ASGI_SERVER.md.
# ═══════════════════════════════════════════════════════════════════════════
set -e

ASGI_SERVER="${ASGI_SERVER:-daphne}"
case "$ASGI_SERVER" in
  daphne | uvicorn) ;;
  *)
    echo "ASGI_SERVER='$ASGI_SERVER' tanınmır (daphne|uvicorn)." >&2
    exit 64
    ;;
esac
ASGI_WORKERS="${ASGI_WORKERS:-1}"
case "$ASGI_WORKERS" in
  '' | *[!0-9]* | 0*)
    echo "ASGI_WORKERS='$ASGI_WORKERS' müsbət tam ədəd olmalıdır." >&2
    exit 64
    ;;
esac
if [ "$ASGI_SERVER" = "daphne" ] && [ "$ASGI_WORKERS" != "1" ]; then
  echo "ASGI_WORKERS=$ASGI_WORKERS yalnız ASGI_SERVER=uvicorn ilə işləyir (Daphne tək prosesdir)." >&2
  exit 64
fi
# config/asgi.py ASGI_THREADS-i uvicorn altında da tətbiq etmək üçün oxuyur.
export ASGI_SERVER ASGI_WORKERS

if [ "${RUN_RELEASE_ON_START:-true}" = "true" ]; then
  echo "Running database migrations and collectstatic…"
  /app/docker/release.sh
else
  echo "Skipping release tasks in this app replica."
fi

if [ -n "${PROMETHEUS_MULTIPROC_DIR:-}" ]; then
  rm -rf "${PROMETHEUS_MULTIPROC_DIR:?}"/*
  mkdir -p "$PROMETHEUS_MULTIPROC_DIR"
fi

# 2026-09-14 infra auditi P3-12: `--proxy-headers` ilə Daphne X-Forwarded-For /
# X-Forwarded-Proto başlıqlarından scope["client"] və scope["scheme"] qurur —
# WS consumer-ləri (məs. live_exam `_get_scope_ip` rate-limit kimliyi) nginx-in
# IP-si əvəzinə real müştəri IP-sini görür. Təhlükəsizdir, çünki nginx XFF-i
# `$remote_addr` ilə OVERWRITE edir (append yox — tests/test_proxy_trust_
# configuration.py) və :8000 yalnız docker şəbəkəsindən əlçatandır; Daphne
# vergüllü siyahının İLK elementini götürür. Bax docs/operations/deployment.md
# «Daphne proxy headers».
#
# Uvicorn ekvivalenti (ASGI_SERVER=uvicorn) — hər bayraq Daphne davranışını təkrarlayır:
#   --proxy-headers --forwarded-allow-ips '*'  Daphne kimi HƏR peer-ə etibar edir və
#       XFF-in İLK elementini götürür (port 0) → scope["client"]/REMOTE_ADDR eynidir.
#   --lifespan off                Django/Channels lifespan scope-u dəstəkləmir.
#   --ws-max-size 1048576         Daphne --websocket-max-message-size defoltu (1 MiB).
#   --ws-ping-interval 20 / --ws-ping-timeout 30   Daphne --ping-interval/--ping-timeout.
#   --ws-per-message-deflate false Daphne (autobahn) sıxılma təklif etmir; 5000 WS ×
#       deflate konteksti yaddaş/CPU yeyərdi.
#   --timeout-graceful-shutdown   DAPHNE_APPLICATION_CLOSE_TIMEOUT (120 s) — compose
#       stop_grace_period (130 s) invariantı eyni qalır. SIGTERM-də WS-lər 1012 alır.
#   --timeout-worker-healthcheck  supervisor worker-i pipe ping-ə cavab verməyəndə
#       SIGKILL edir; 5 s defoltu CPU sıçrayışında imtahan təqdimini öldürə bilərdi.
#   Access log: Daphne (verbosity 1) stdout-a yazır → uvicorn-da da açıqdır.
#   DAPHNE_HTTP_TIMEOUT-un uvicorn-da ekvivalenti yoxdur — nginx proxy_read_timeout
#   (≤ 900 s) sorğu müddətini məhdudlaşdırır.
if [ "$ASGI_SERVER" = "uvicorn" ]; then
  if [ "${UVICORN_ACCESS_LOG:-true}" = "true" ]; then
    UVICORN_ACCESS_LOG_FLAG="--access-log"
  else
    UVICORN_ACCESS_LOG_FLAG="--no-access-log"
  fi
  echo "Starting Uvicorn ASGI server (${ASGI_WORKERS} worker)…"
  exec uvicorn \
    --host 0.0.0.0 \
    --port 8000 \
    --workers "$ASGI_WORKERS" \
    --lifespan off \
    --proxy-headers \
    --forwarded-allow-ips "${ASGI_FORWARDED_ALLOW_IPS:-*}" \
    --loop "${UVICORN_LOOP:-auto}" \
    --http "${UVICORN_HTTP:-auto}" \
    --ws websockets-sansio \
    --ws-max-size 1048576 \
    --ws-ping-interval 20 \
    --ws-ping-timeout 30 \
    --ws-per-message-deflate false \
    --timeout-keep-alive "${UVICORN_TIMEOUT_KEEP_ALIVE:-5}" \
    --timeout-graceful-shutdown "${DAPHNE_APPLICATION_CLOSE_TIMEOUT:-120}" \
    --timeout-worker-healthcheck "${UVICORN_WORKER_HEALTHCHECK_TIMEOUT:-60}" \
    "$UVICORN_ACCESS_LOG_FLAG" \
    config.asgi:application
fi

echo "Starting Daphne ASGI server…"
exec daphne \
  -b 0.0.0.0 \
  -p 8000 \
  --proxy-headers \
  --http-timeout "${DAPHNE_HTTP_TIMEOUT:-900}" \
  --application-close-timeout "${DAPHNE_APPLICATION_CLOSE_TIMEOUT:-120}" \
  config.asgi:application
