#!/usr/bin/env bash
#
# restore_legacy_scores_build_plan.sh — LOKAL addım: J12 bərpa planını qur (2026-09-25)
# ==================================================================================
#
# Nə edir (heç nəyi production-a YAZMIR):
#   1. köhnə MyEdu dump-unu (sha256 yoxlanılır) lokal, 127.0.0.1-ə bağlı, atılabilən
#      MariaDB konteynerinə yükləyir və @@GLOBAL.read_only=1 edir; yalnız SELECT
#      icazəli ayrıca istifadəçi yaradır;
#   2. production-un TƏZƏ pg_dump-unu (serverdən gətirilmiş, -Fc) lokal agent
#      Postgres-də ATILABİLƏN bazaya bərpa edir və ona
#      emsarena.rehearsal_target='disposable' markeri qoyur;
#   3. `legacy_repair_lesson_recovery --build-plan` işlədir → plan + manifest.
#
# İstifadə:
#   scripts/ops/restore_legacy_scores_build_plan.sh <prod.dump> <çıxış qovluğu> [actor]
#
# Mühit (defoltlar lokal agent sandbox-una uyğundur):
#   LEGACY_DUMP=~/Downloads/myedudb.sql      MARIADB_CONTAINER=ems-legacy-mariadb-restore
#   MARIADB_PORT=50310                        AGENT_PG=emsarena-agent-postgres
#   AGENT_PG_URL=postgres://emsarena_agent:emsarena_agent_password@127.0.0.1:55432
#   PLAN_DB=ems_restore_plan_<tarix>         ORG=qku
#
# ⚠️ Plan faylı şəxsi akademik məlumat daşıyır — repoya/buluda/mesajlaşmaya QOYMAYIN.
set -euo pipefail

PROD_DUMP="${1:?production pg_dump (-Fc) faylı}"
OUT_DIR="${2:?plan üçün çıxış qovluğu}"
ACTOR="${3:-superadmin}"
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
LEGACY_DUMP="${LEGACY_DUMP:-$HOME/Downloads/myedudb.sql}"
LEGACY_SHA256="177ef2269027395fd3a80fc1dd592aab565dda7cbca5f6f08785313881d68fe0"
MARIADB_CONTAINER="${MARIADB_CONTAINER:-ems-legacy-mariadb-restore}"
MARIADB_PORT="${MARIADB_PORT:-50310}"
AGENT_PG="${AGENT_PG:-emsarena-agent-postgres}"
AGENT_PG_URL="${AGENT_PG_URL:-postgres://emsarena_agent:emsarena_agent_password@127.0.0.1:55432}"
PLAN_DB="${PLAN_DB:-ems_restore_plan_$(date -u +%Y%m%d%H%M)}"
ORG="${ORG:-qku}"
STAMP="$(date -u +%Y%m%dT%H%MZ)"

mkdir -p "$OUT_DIR" && chmod 700 "$OUT_DIR"
SECRETS="$OUT_DIR/.secrets" && mkdir -p "$SECRETS" && chmod 700 "$SECRETS"
[ -f "$SECRETS/root.pw" ] || { openssl rand -hex 24 >"$SECRETS/root.pw"; chmod 600 "$SECRETS/root.pw"; }
[ -f "$SECRETS/ro.pw" ] || { openssl rand -hex 24 >"$SECRETS/ro.pw"; chmod 600 "$SECRETS/ro.pw"; }

echo "== 1/3 köhnə mənbə: sha256 + MariaDB konteyneri"
echo "$LEGACY_SHA256  $LEGACY_DUMP" | shasum -a 256 -c -
if ! docker ps --format '{{.Names}}' | grep -qx "$MARIADB_CONTAINER"; then
    docker run -d --name "$MARIADB_CONTAINER" -p "127.0.0.1:${MARIADB_PORT}:3306" \
        -e MARIADB_ROOT_PASSWORD="$(cat "$SECRETS/root.pw")" -e MARIADB_DATABASE=myedudb \
        -v "${MARIADB_CONTAINER}-data:/var/lib/mysql" mariadb:10.6 \
        --innodb-buffer-pool-size=3G --innodb-log-file-size=1G --innodb-flush-log-at-trx-commit=0 \
        --innodb-doublewrite=0 --skip-log-bin --max-allowed-packet=1G \
        --character-set-server=utf8mb4 --collation-server=utf8mb4_general_ci
    until docker exec "$MARIADB_CONTAINER" sh -c 'mariadb -uroot -p"$MARIADB_ROOT_PASSWORD" -e "select 1"' >/dev/null 2>&1; do
        sleep 2
    done
    docker exec -i "$MARIADB_CONTAINER" sh -c 'exec mariadb -uroot -p"$MARIADB_ROOT_PASSWORD" --max-allowed-packet=1G myedudb' \
        <"$LEGACY_DUMP"
fi
RO_PW="$(cat "$SECRETS/ro.pw")"
docker exec "$MARIADB_CONTAINER" sh -c "mariadb -uroot -p\"\$MARIADB_ROOT_PASSWORD\" -e \"
    CREATE USER IF NOT EXISTS 'ems_ro'@'%' IDENTIFIED BY '$RO_PW';
    GRANT SELECT, SHOW VIEW ON myedudb.* TO 'ems_ro'@'%'; FLUSH PRIVILEGES;
    SET GLOBAL read_only = 1; SELECT @@GLOBAL.read_only AS read_only;\""

echo "== 2/3 production nüsxəsi → atılabilən baza $PLAN_DB (marker ilə)"
psql "$AGENT_PG_URL/postgres" -X -v ON_ERROR_STOP=1 -c "CREATE DATABASE $PLAN_DB"
docker cp "$PROD_DUMP" "$AGENT_PG:/tmp/restore_prod.dump"
if head -c 5 "$PROD_DUMP" | grep -q "PGDMP"; then
    # pg_dump -Fc (custom) formatı
    docker exec "$AGENT_PG" pg_restore -U emsarena_agent -d "$PLAN_DB" --no-owner --no-privileges -j 4 /tmp/restore_prod.dump
else
    # emsarena-postgres-backup /backup.sh: `pg_dump -Z6` → gzip-lənmiş düz SQL (.sql.gz).
    # Serverdəki rollara (OWNER/GRANT) aid xətalar atılabilən klonda gözləniləndir.
    docker exec "$AGENT_PG" sh -c 'gunzip -c /tmp/restore_prod.dump 2>/dev/null || cat /tmp/restore_prod.dump' |
        docker exec -i "$AGENT_PG" psql -q -U emsarena_agent -d "$PLAN_DB" >/dev/null
fi
docker exec "$AGENT_PG" rm -f /tmp/restore_prod.dump
psql "$AGENT_PG_URL/postgres" -X -v ON_ERROR_STOP=1 \
    -c "ALTER DATABASE $PLAN_DB SET emsarena.rehearsal_target = 'disposable'"

echo "== 3/3 J12 planı (klona yazır; production-a YOX)"
cd "$REPO"
export DATABASE_URL="$AGENT_PG_URL/$PLAN_DB" USE_REDIS=False
export LEGACY_MARIADB_SOURCE_ATTEST_ENABLED=1 LEGACY_MARIADB_SOURCE_LOCAL_DISPOSABLE=local-container-only
export LEGACY_MARIADB_SOURCE_HOST=127.0.0.1 LEGACY_MARIADB_SOURCE_PORT="$MARIADB_PORT"
export LEGACY_MARIADB_SOURCE_USER=ems_ro LEGACY_MARIADB_SOURCE_PASSWORD="$RO_PW"
export LEGACY_MARIADB_SOURCE_DATABASE=myedudb LEGACY_MARIADB_SOURCE_READ_TIMEOUT=300
venv/bin/python manage.py migrate --check
caffeinate -dimsu venv/bin/python manage.py legacy_repair_lesson_recovery \
    --organization "$ORG" --actor "$ACTOR" \
    --build-plan "$OUT_DIR/j12_plan_${STAMP}.jsonl.gz" --source-dump "$LEGACY_DUMP"
( cd "$OUT_DIR" && shasum -a 256 "j12_plan_${STAMP}.jsonl.gz" >"j12_plan_${STAMP}.jsonl.gz.sha256" )
echo "Hazırdır: $OUT_DIR/j12_plan_${STAMP}.jsonl.gz (+ .manifest.json, .sha256). Klon: $PLAN_DB (atılabilən)."
