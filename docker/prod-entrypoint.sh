#!/bin/sh
# ═══════════════════════════════════════════════════════════════════════════
# EMS Arena — Production container entrypoint
# ═══════════════════════════════════════════════════════════════════════════
# 1. Run database migrations and collect static files (idempotent; safe on
#    rolling restarts and required when Docker named volumes persist older
#    static assets across image rebuilds).
# 2. Exec Daphne as PID 1 so Docker signals (SIGTERM/SIGINT) are forwarded
#    directly to the ASGI server for graceful shutdown.
# ═══════════════════════════════════════════════════════════════════════════
set -e

echo "Running database migrations…"
/app/docker/release.sh

echo "Starting Daphne ASGI server…"
exec daphne -b 0.0.0.0 -p 8000 config.asgi:application
