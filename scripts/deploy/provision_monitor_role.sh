#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
# EMS Arena — exporter-lər üçün least-privilege PostgreSQL rolu (idempotent)
# ═══════════════════════════════════════════════════════════════════════════
# Təhlükəsizlik auditi 2026-10-07: postgres_exporter və pgbouncer_exporter
# owner/superuser (POSTGRES_USER) ilə qoşulurdu — exporter-in ələ keçməsi bütün
# baza üzərində superuser demək idi. Bu skript `.env`-dəki MONITOR_DB_PASSWORD
# ilə ayrıca rol yaradır/yeniləyir:
#   LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOREPLICATION,
#   CONNECTION LIMIT 5, GRANT pg_monitor, default_transaction_read_only=on,
#   statement_timeout=30s, lock_timeout=5s.
# remote_deploy.sh hər deploy-da postgres sağlam olandan sonra çağırır; əl ilə:
#   APP_DIR=/home/wcu/EducationManagementStudentArena bash scripts/deploy/provision_monitor_role.sh
#
# Sirr qaydaları: parol YALNIZ .env-dən oxunur, heç vaxt argv-yə (docker/psql
# arqumenti) düşmür — psql-ə stdin ilə (`\set`) ötürülür; skriptdə `set -x` yoxdur;
# sessiyada server loglaması və pg_stat_statements utility izləməsi söndürülür
# ki, ALTER ROLE … PASSWORD mətni log/statistikaya düşməsin; xəta çıxışında parol
# maskalanır.
#
# Çıxış kodu: 0 — rol hazırdır (və ya MONITOR_DB_PASSWORD yoxdur → heç nə edilmədi);
#             1 — konfiqurasiya təhlükəsiz deyil / psql xətası (deploy fallback edir).
# ═══════════════════════════════════════════════════════════════════════════
set -euo pipefail

APP_DIR="${APP_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
ENV_FILE="${ENV_FILE:-${APP_DIR}/.env}"

# remote_deploy.sh dotenv_value ilə eyni ayrışdırma — .env shell kimi source edilmir.
dotenv_value() {
  local key="$1"
  local value=""
  [ -f "$ENV_FILE" ] || return 0
  value="$(awk -v wanted="${key}" '
    index($0, wanted "=") == 1 { value = substr($0, length(wanted) + 2) }
    END { print value }
  ' "$ENV_FILE")"
  value="${value%$'\r'}"
  if [[ "$value" == \"*\" && "$value" == *\" ]]; then
    value="${value:1:${#value}-2}"
  elif [[ "$value" == \'*\' && "$value" == *\' ]]; then
    value="${value:1:${#value}-2}"
  fi
  printf '%s' "$value"
}

password="$(dotenv_value MONITOR_DB_PASSWORD)"
monitor_role="${MONITOR_DB_USER:-$(dotenv_value MONITOR_DB_USER)}"
monitor_role="${monitor_role:-emsarena_monitor}"
owner_role="$(dotenv_value POSTGRES_USER)"
app_role="$(dotenv_value APP_DATABASE_USER)"

if [ -z "$password" ]; then
  echo "MONITOR_DB_PASSWORD is not set in ${ENV_FILE}; monitor role not provisioned (exporters keep the owner login)."
  exit 0
fi
if ! [[ "$password" =~ ^[A-Za-z0-9._~-]{16,128}$ ]]; then
  echo "ERROR: MONITOR_DB_PASSWORD must be 16-128 characters of [A-Za-z0-9._~-] (generate it with prod-secrets-generate)." >&2
  exit 1
fi
if ! [[ "$monitor_role" =~ ^[a-z_][a-z0-9_]{0,62}$ ]]; then
  echo "ERROR: MONITOR_DB_USER '${monitor_role}' is not a plain lower-case identifier." >&2
  exit 1
fi
if [ "$monitor_role" = "$owner_role" ] || [ "$monitor_role" = "$app_role" ] || [ "$monitor_role" = "postgres" ]; then
  echo "ERROR: MONITOR_DB_USER '${monitor_role}' must be a dedicated role (not POSTGRES_USER / APP_DATABASE_USER / postgres)." >&2
  exit 1
fi

out="$(mktemp)"
trap 'rm -f "$out"' EXIT
# remote_deploy.sh ilə eyni compose layihəsi (layihə adı + .env qovluqdan gəlir).
cd "$APP_DIR"

# Rol adları sirr deyil (argv-də ola bilər); parol yalnız stdin-in ilk sətrindədir.
# Simvol dəsti yuxarıda yoxlanıb — tək dırnaq / backslash ola bilməz.
if ! {
  printf "\\\\set monitor_password '%s'\n" "$password"
  cat <<'SQL'
\set VERBOSITY terse
\set SHOW_CONTEXT never
-- ALTER ROLE … PASSWORD mətni server loguna / pg_stat_statements-ə düşməsin.
SET log_statement = 'none';
SET log_min_duration_statement = -1;
SET log_min_error_statement = 'panic';
SET pg_stat_statements.track_utility = off;
SET password_encryption = 'scram-sha-256';
BEGIN;

-- Mövcud imtiyazlı / sahibli / başqa rola üzv rolu monitor kimi yenidən istifadə etmə.
SELECT (
    :'monitor_role' = :'owner_role'
    OR EXISTS (SELECT FROM pg_roles WHERE rolname = :'monitor_role'
               AND (rolsuper OR rolbypassrls OR rolcreatedb OR rolcreaterole OR rolreplication))
    OR EXISTS (SELECT FROM pg_auth_members m
               JOIN pg_roles r ON r.oid = m.member
               JOIN pg_roles g ON g.oid = m.roleid
               WHERE r.rolname = :'monitor_role' AND g.rolname <> 'pg_monitor')
    OR EXISTS (SELECT FROM pg_shdepend d JOIN pg_roles r ON r.oid = d.refobjid
               WHERE d.refclassid = 'pg_authid'::regclass AND d.deptype = 'o'
                 AND r.rolname = :'monitor_role')
) AS unsafe_existing_role \gset
\if :unsafe_existing_role
    \echo 'ERROR: monitor role must be a dedicated unprivileged account (only pg_monitor membership, owns nothing).'
    DO $$ BEGIN RAISE EXCEPTION 'Refusing unsafe monitor role'; END $$;
\endif

SELECT format('CREATE ROLE %I LOGIN', :'monitor_role')
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = :'monitor_role')
\gexec

ALTER ROLE :"monitor_role" WITH LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOREPLICATION INHERIT CONNECTION LIMIT 5;
ALTER ROLE :"monitor_role" WITH PASSWORD :'monitor_password';
ALTER ROLE :"monitor_role" SET default_transaction_read_only = on;
ALTER ROLE :"monitor_role" SET statement_timeout = '30s';
ALTER ROLE :"monitor_role" SET lock_timeout = '5s';
GRANT pg_monitor TO :"monitor_role";
GRANT CONNECT ON DATABASE :"db_name" TO :"monitor_role";

SELECT format('monitor role %s: superuser=%s bypassrls=%s pg_monitor=%s',
              rolname, rolsuper, rolbypassrls, pg_has_role(rolname, 'pg_monitor', 'MEMBER'))
FROM pg_roles WHERE rolname = :'monitor_role';
COMMIT;
SQL
} | docker compose -f "$COMPOSE_FILE" exec -T postgres \
  sh -c "exec psql -X -q -At -v ON_ERROR_STOP=1 -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -v owner_role=\"\$POSTGRES_USER\" -v db_name=\"\$POSTGRES_DB\" -v monitor_role=${monitor_role}" \
  >"$out" 2>&1; then
  sanitized="$(cat "$out")"
  sanitized="${sanitized//"$password"/***}"
  echo "ERROR: monitor role provisioning failed:" >&2
  printf '%s\n' "$sanitized" | tail -n 20 >&2
  exit 1
fi

summary="$(grep -E '^monitor role ' "$out" | tail -n 1 || true)"
summary="${summary//"$password"/***}"
echo "${summary:-monitor role ${monitor_role} provisioned}"
