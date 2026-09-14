#!/bin/sh
# ═══════════════════════════════════════════════════════════════════════════
# EMS Arena — Production container entrypoint
# ═══════════════════════════════════════════════════════════════════════════
# 1. Optionally run database migrations and collect static files. The deploy
#    script runs this once before scaling app replicas; direct compose users
#    keep the old safe default by leaving RUN_RELEASE_ON_START=true.
# 2. Exec Daphne as PID 1 so Docker signals (SIGTERM/SIGINT) are forwarded
#    directly to the ASGI server for graceful shutdown.
# ═══════════════════════════════════════════════════════════════════════════
set -e

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
echo "Starting Daphne ASGI server…"
exec daphne \
  -b 0.0.0.0 \
  -p 8000 \
  --proxy-headers \
  --http-timeout "${DAPHNE_HTTP_TIMEOUT:-900}" \
  --application-close-timeout "${DAPHNE_APPLICATION_CLOSE_TIMEOUT:-120}" \
  config.asgi:application
