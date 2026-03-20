#!/bin/sh
# ═══════════════════════════════════════════════════════════════════════════
# EMS Arena — Production container entrypoint
# ═══════════════════════════════════════════════════════════════════════════
# 1. Run database migrations (idempotent; safe on rolling restarts).
# 2. Exec Daphne as PID 1 so Docker signals (SIGTERM/SIGINT) are forwarded
#    directly to the ASGI server for graceful shutdown.
# ═══════════════════════════════════════════════════════════════════════════
set -e

echo "Running database migrations…"
/app/docker/release.sh

echo "Starting Daphne ASGI server…"
exec daphne -b 0.0.0.0 -p 8000 config.asgi:application
