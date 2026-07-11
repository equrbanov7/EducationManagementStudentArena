#!/bin/sh
# ═══════════════════════════════════════════════════════════════════════════
# Fresh PostgreSQL volume-da NOSUPERUSER tətbiq rolu (audit EXAM-P0-01)
# ═══════════════════════════════════════════════════════════════════════════
# docker-entrypoint-initdb.d yalnız BOŞ data volume-da işləyir. Mövcud
# production DB üçün scripts/provision-app-db-role.sh istifadə edin.
# APP_DATABASE_USER/APP_DATABASE_PASSWORD verilməyibsə heç nə etmir
# (geriyə-uyğunluq: köhnə tək-rollu quraşdırma işləməyə davam edir).
# ═══════════════════════════════════════════════════════════════════════════
set -eu

if [ -z "${APP_DATABASE_USER:-}" ] || [ -z "${APP_DATABASE_PASSWORD:-}" ]; then
  echo "APP_DATABASE_USER/APP_DATABASE_PASSWORD verilməyib — tətbiq rolu yaradılmır."
  exit 0
fi

echo "Tətbiq DB rolu yaradılır: $APP_DATABASE_USER"

psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
  -v app_role="$APP_DATABASE_USER" -v app_password="$APP_DATABASE_PASSWORD" \
  -v owner_role="$POSTGRES_USER" -v db_name="$POSTGRES_DB" <<'SQL'
SELECT format('CREATE ROLE %I LOGIN', :'app_role')
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = :'app_role')
\gexec

ALTER ROLE :"app_role" WITH LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOREPLICATION;
ALTER ROLE :"app_role" WITH PASSWORD :'app_password';

GRANT CONNECT ON DATABASE :"db_name" TO :"app_role";
GRANT USAGE ON SCHEMA public TO :"app_role";
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO :"app_role";
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO :"app_role";

ALTER DEFAULT PRIVILEGES FOR ROLE :"owner_role" IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO :"app_role";
ALTER DEFAULT PRIVILEGES FOR ROLE :"owner_role" IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO :"app_role";
SQL
