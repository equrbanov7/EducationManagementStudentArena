#!/bin/sh
set -eu

# Keep database schema and collected static assets in sync with the latest
# image/code before the web container starts serving traffic.
#
# EXAM-P0-01: miqrasiyalar DDL (ALTER TABLE və s.) tələb etdiyi üçün owner
# rolu ilə işləyir — MIGRATION_DATABASE_URL varsa runtime DATABASE_URL-i
# əvəz edir. Rol-yoxlama check-i bu addım üçün söndürülür, çünki owner-in
# superuser olması burada qanunidir.
if [ -n "${MIGRATION_DATABASE_URL:-}" ]; then
  export DATABASE_URL="$MIGRATION_DATABASE_URL"
  export EMS_DB_ROLE_ENFORCE="off"
fi
python manage.py migrate --noinput
python manage.py collectstatic --noinput
