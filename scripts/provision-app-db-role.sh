#!/bin/sh
# ═══════════════════════════════════════════════════════════════════════════
# EMS Arena — NOSUPERUSER tətbiq DB rolunun yaradılması (audit EXAM-P0-01)
# ═══════════════════════════════════════════════════════════════════════════
# PostgreSQL superuser-i FORCE ROW LEVEL SECURITY olduqda belə RLS-i yan
# keçir. Bu skript tətbiq runtime-ı üçün RLS-ə TAM TABE olan ayrıca LOGIN
# rolu yaradır. Miqrasiyalar owner (bootstrap) rolunda qalır
# (MIGRATION_DATABASE_URL).
#
# İstifadə (mövcud production DB üçün, postgres konteynerinin işlədiyi hostda):
#   APP_DATABASE_USER=emsarena_app APP_DATABASE_PASSWORD='...' \
#     ./scripts/provision-app-db-role.sh
#
# Sonra .env-ə əlavə edin və app/worker/beat-i yenidən qaldırın:
#   APP_DATABASE_USER=emsarena_app
#   APP_DATABASE_PASSWORD=...
#
# Skript idempotentdir — rol mövcuddursa yalnız atributları/parolu yeniləyir.
# ═══════════════════════════════════════════════════════════════════════════
set -eu

CONTAINER="${POSTGRES_CONTAINER:-emsarena-postgres}"
APP_ROLE="${APP_DATABASE_USER:?APP_DATABASE_USER tələb olunur}"
APP_PASSWORD="${APP_DATABASE_PASSWORD:?APP_DATABASE_PASSWORD tələb olunur}"

echo "→ '$APP_ROLE' rolu provision olunur…"

docker exec -i \
  -e APP_ROLE="$APP_ROLE" \
  -e APP_PASSWORD="$APP_PASSWORD" \
  "$CONTAINER" sh -c 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
    -v app_role="$APP_ROLE" -v app_password="$APP_PASSWORD" \
    -v owner_role="$POSTGRES_USER" -v db_name="$POSTGRES_DB"' <<'SQL'
-- Rol yoxdursa yarat (psql var-ları dollar-quote daxilində açılmadığı üçün \gexec).
SELECT format('CREATE ROLE %I LOGIN', :'app_role')
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = :'app_role')
\gexec

-- LOGIN, superuser YOX, RLS bypass YOX.
ALTER ROLE :"app_role" WITH LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOREPLICATION;
ALTER ROLE :"app_role" WITH PASSWORD :'app_password';

-- Mövcud obyektlərə DML icazələri (DDL yox — miqrasiyalar owner-də qalır).
GRANT CONNECT ON DATABASE :"db_name" TO :"app_role";
GRANT USAGE ON SCHEMA public TO :"app_role";
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO :"app_role";
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO :"app_role";

-- Gələcək miqrasiyaların yaratdığı cədvəl/sequence-lər üçün default icazələr.
ALTER DEFAULT PRIVILEGES FOR ROLE :"owner_role" IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO :"app_role";
ALTER DEFAULT PRIVILEGES FOR ROLE :"owner_role" IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO :"app_role";

-- Staged-account activation evidence is append-only.  The broad application
-- DML grant above must never turn this ledger into a writable table; the only
-- transition surface is the audited, fixed-search_path activation function.
SELECT format(
    'REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON TABLE '
    'public.accounts_accountactivationevidence FROM %I',
    :'app_role'
)
WHERE to_regclass('public.accounts_accountactivationevidence') IS NOT NULL
\gexec

SELECT format(
    'GRANT EXECUTE ON FUNCTION '
    'public.accounts_activate_staged_identity('
    'uuid,bigint,uuid,uuid,bigint,text,text) TO %I',
    :'app_role'
)
WHERE to_regprocedure(
    'public.accounts_activate_staged_identity('
    'uuid,bigint,uuid,uuid,bigint,text,text)'
) IS NOT NULL
\gexec

-- Registrar group identity changes use a two-phase evidence surface.  The app
-- role may execute begin/finalize, but cannot forge or mutate ledger rows.
SELECT format(
    'REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON TABLE '
    'public.registrar_grouptransferevidence FROM %I',
    :'app_role'
)
WHERE to_regclass('public.registrar_grouptransferevidence') IS NOT NULL
\gexec

SELECT format(
    'GRANT SELECT ON TABLE public.registrar_grouptransferevidence TO %I',
    :'app_role'
)
WHERE to_regclass('public.registrar_grouptransferevidence') IS NOT NULL
\gexec

SELECT format(
    'GRANT EXECUTE ON FUNCTION '
    'public.registrar_begin_student_group_transfer('
    'uuid,uuid,uuid,uuid,uuid,bigint) TO %I',
    :'app_role'
)
WHERE to_regprocedure(
    'public.registrar_begin_student_group_transfer('
    'uuid,uuid,uuid,uuid,uuid,bigint)'
) IS NOT NULL
\gexec

SELECT format(
    'GRANT EXECUTE ON FUNCTION '
    'public.registrar_finalize_student_group_transfer(uuid,uuid) TO %I',
    :'app_role'
)
WHERE to_regprocedure(
    'public.registrar_finalize_student_group_transfer(uuid,uuid)'
) IS NOT NULL
\gexec

-- Yoxlama: atributlar gözlənildiyi kimidirmi?
SELECT rolname, rolsuper, rolbypassrls, rolcanlogin
FROM pg_roles WHERE rolname = :'app_role';
SQL

echo "✓ Hazır. .env-də APP_DATABASE_USER/APP_DATABASE_PASSWORD təyin edib app/worker/beat-i yenidən başladın."
