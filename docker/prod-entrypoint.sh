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

echo "Starting Daphne ASGI server…"
exec daphne -b 0.0.0.0 -p 8000 config.asgi:application
