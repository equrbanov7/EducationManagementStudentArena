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

# Audit 2026-09-28 DB-02: rol səviyyəli timeout-lar (env ilə dəyişdirilə bilər;
# `0` = limitsiz). Format: rəqəm + ixtiyari vahid (ms, s, min, h).
APP_DB_STATEMENT_TIMEOUT="${APP_DB_STATEMENT_TIMEOUT:-60s}"
APP_DB_LOCK_TIMEOUT="${APP_DB_LOCK_TIMEOUT:-10s}"
APP_DB_IDLE_IN_TRANSACTION_TIMEOUT="${APP_DB_IDLE_IN_TRANSACTION_TIMEOUT:-120s}"
for _timeout in "$APP_DB_STATEMENT_TIMEOUT" "$APP_DB_LOCK_TIMEOUT" "$APP_DB_IDLE_IN_TRANSACTION_TIMEOUT"; do
  if ! printf '%s' "$_timeout" | grep -Eq '^[0-9]+(ms|s|min|h)?$'; then
    echo "ERROR: yararsız DB timeout dəyəri: '$_timeout' (gözlənilən: 60s, 500ms, 2min, 0)" >&2
    exit 1
  fi
done

echo "Tətbiq DB rolu yaradılır: $APP_DATABASE_USER"

psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
  -v app_role="$APP_DATABASE_USER" -v app_password="$APP_DATABASE_PASSWORD" \
  -v owner_role="$POSTGRES_USER" -v db_name="$POSTGRES_DB" \
  -v statement_timeout="$APP_DB_STATEMENT_TIMEOUT" -v lock_timeout="$APP_DB_LOCK_TIMEOUT" \
  -v idle_in_tx_timeout="$APP_DB_IDLE_IN_TRANSACTION_TIMEOUT" <<'SQL'
BEGIN;

-- Refuse to repurpose an owner, privileged account, or role with memberships.
-- A dedicated runtime account must not inherit another role or own objects.
SELECT (
    :'app_role' = :'owner_role'
    OR EXISTS (SELECT FROM pg_roles WHERE rolname = :'app_role'
               AND (rolsuper OR rolbypassrls OR rolcreatedb OR rolcreaterole OR rolreplication))
    OR EXISTS (SELECT FROM pg_auth_members m JOIN pg_roles r ON r.oid = m.member
               WHERE r.rolname = :'app_role')
    OR EXISTS (SELECT FROM pg_shdepend d JOIN pg_roles r ON r.oid = d.refobjid
               WHERE d.refclassid = 'pg_authid'::regclass AND d.deptype = 'o'
                 AND r.rolname = :'app_role')
) AS unsafe_existing_role \gset
\if :unsafe_existing_role
    \echo 'ERROR: app role must be a dedicated unprivileged non-owner account.'
    -- ON_ERROR_STOP makes PostgreSQL 16 psql exit nonzero and rolls back.
    DO $$ BEGIN RAISE EXCEPTION 'Refusing unsafe app role'; END $$;
\endif

SELECT format('CREATE ROLE %I LOGIN', :'app_role')
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = :'app_role')
\gexec

ALTER ROLE :"app_role" WITH LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOREPLICATION;
ALTER ROLE :"app_role" WITH PASSWORD :'app_password';

-- Audit 2026-09-28 DB-02: rol səviyyəli timeout-lar (idempotent). İlişən sorğu,
-- kilid gözləməsi və ya açıq qalmış transaction artıq yazıçıları sonsuz
-- bloklamır və PgBouncer server bağlantısını tutmur. Uzun işlər limiti yalnız
-- öz transaction/sessiyası üçün genişləndirir (core/db_timeouts.py
-- long_statement). Owner (miqrasiya) roluna toxunulmur. Yeni dəyər yalnız YENİ
-- backend sessiyalarına şamil olunur (PgBouncer hovuzu server_lifetime ərzində
-- yenilənir).
ALTER ROLE :"app_role" SET statement_timeout = :'statement_timeout';
ALTER ROLE :"app_role" SET lock_timeout = :'lock_timeout';
ALTER ROLE :"app_role" SET idle_in_transaction_session_timeout = :'idle_in_tx_timeout';

GRANT CONNECT ON DATABASE :"db_name" TO :"app_role";
GRANT USAGE ON SCHEMA public TO :"app_role";
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO :"app_role";
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO :"app_role";

ALTER DEFAULT PRIVILEGES FOR ROLE :"owner_role" IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO :"app_role";
ALTER DEFAULT PRIVILEGES FOR ROLE :"owner_role" IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO :"app_role";
COMMIT;
SQL
