#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
# EMS Arena — istehsal bazasını hazır dump-dan doldurmaq (ilk deploy BOŞ bazaya
# getdiyi üçün; deployment.md §5.2 A3). Serverdə, APP_DIR içində işlədilir.
#
#   SEED_DUMP=/path/to/emsarena_db.dump EXPECTED_USERS=8443 \
#     bash scripts/deploy/seed_database.sh
#
# Addımlar: mövcud bazanın ehtiyat dump-ı → yazanları dayandır → DROP/CREATE →
# pg_restore → tətbiq rolu provision → release.sh (miqrasiya başa + collectstatic)
# → qaldır → sağlamlıq + sətir sayı yoxlaması. Uğursuz addım → skript dayanır,
# heç nə «yarım» qalmır: bərpa uğursuz olsa baza yenə boşdur, ehtiyat dump yerindədir.
#
# `SEED_CONFIRM=SEED` olmadan işləmir (bu skript mövcud bazanı SİLİR).
# ═══════════════════════════════════════════════════════════════════════════
set -euo pipefail

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
SEED_DUMP="${SEED_DUMP:?SEED_DUMP (pg_dump -Fc faylı) tələb olunur}"
EXPECTED_USERS="${EXPECTED_USERS:-}"
RESTORE_JOBS="${RESTORE_JOBS:-4}"
PG_CONTAINER="${POSTGRES_CONTAINER:-emsarena-postgres}"
BACKUP_CONTAINER="${BACKUP_CONTAINER:-emsarena-postgres-backup}"
WRITERS=(app celery_worker celery_worker_heavy celery_beat pgbouncer postgres_exporter pgbouncer_exporter)

if [ "${SEED_CONFIRM:-}" != "SEED" ]; then
  echo "SEED_CONFIRM=SEED təyin edilməyib — bu skript mövcud bazanı silir; şüurlu təsdiq lazımdır." >&2
  exit 1
fi
if [ ! -s "$SEED_DUMP" ]; then
  echo "Dump faylı yoxdur və ya boşdur: $SEED_DUMP" >&2
  exit 1
fi
if ! docker exec "$PG_CONTAINER" sh -c 'exit 0' >/dev/null 2>&1; then
  echo "Postgres konteyneri ($PG_CONTAINER) işləmir." >&2
  exit 1
fi

dotenv_value() {
  local key="$1" value=""
  [ -f .env ] || return 0
  value="$(awk -v wanted="${key}" 'index($0, wanted "=") == 1 { value = substr($0, length(wanted) + 2) } END { print value }' .env)"
  value="${value%$'\r'}"
  if [[ "$value" == \"*\" && "$value" == *\" ]]; then value="${value:1:${#value}-2}"; fi
  if [[ "$value" == \'*\' && "$value" == *\' ]]; then value="${value:1:${#value}-2}"; fi
  printf '%s' "$value"
}

APP_DB_USER="$(dotenv_value APP_DATABASE_USER)"
APP_DB_PASSWORD="$(dotenv_value APP_DATABASE_PASSWORD)"

echo "→ 1/7 Mövcud bazanın ehtiyat dump-ı (postgres-backup /backup.sh)…"
if docker exec "$BACKUP_CONTAINER" /backup.sh; then
  echo "   ehtiyat dump alındı (backups/last/)."
else
  echo "   XƏBƏRDARLIQ: ehtiyat dump alınmadı — baza boşdursa problem deyil; əks halda DAYANIN." >&2
  [ "${SEED_ALLOW_NO_BACKUP:-}" = "1" ] || exit 1
fi

echo "→ 2/7 Yazanlar dayandırılır: ${WRITERS[*]}"
docker compose -f "$COMPOSE_FILE" stop "${WRITERS[@]}"

echo "→ 3/7 Baza yenidən yaradılır (DROP … WITH (FORCE) → CREATE)…"
docker exec -i "$PG_CONTAINER" sh -c '
  set -e
  psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d postgres \
    -c "DROP DATABASE IF EXISTS \"$POSTGRES_DB\" WITH (FORCE);" \
    -c "CREATE DATABASE \"$POSTGRES_DB\" OWNER \"$POSTGRES_USER\";"
'

echo "→ 4/7 pg_restore (-j $RESTORE_JOBS)…"
docker cp "$SEED_DUMP" "$PG_CONTAINER:/tmp/seed.dump"
# --no-owner/--no-privileges: obyektlər owner rolunun olur; app rolunun GRANT-ları 5-ci addımda.
# pg_restore bəzi zərərsiz xəbərdarlıqlar (extension şərhləri) verə bilər — çıxış kodu ilə qərar veririk.
if ! docker exec -i "$PG_CONTAINER" sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner --no-privileges --exit-on-error -j '"$RESTORE_JOBS"' /tmp/seed.dump'; then
  docker exec "$PG_CONTAINER" rm -f /tmp/seed.dump
  echo "pg_restore UĞURSUZ — baza natamamdır; ehtiyat dump backups/last/-dadır, tətbiq qaldırılmadı." >&2
  exit 1
fi
docker exec "$PG_CONTAINER" rm -f /tmp/seed.dump
docker exec -i "$PG_CONTAINER" sh -c 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "ANALYZE;"' >/dev/null

echo "→ 5/7 Tətbiq DB rolu (NOBYPASSRLS) yeni bazada provision olunur…"
if [ -n "$APP_DB_USER" ] && [ -n "$APP_DB_PASSWORD" ]; then
  APP_DATABASE_USER="$APP_DB_USER" APP_DATABASE_PASSWORD="$APP_DB_PASSWORD" POSTGRES_CONTAINER="$PG_CONTAINER" \
    bash scripts/provision-app-db-role.sh
else
  echo "   APP_DATABASE_USER/PASSWORD .env-də yoxdur — rol provision atlandı (tətbiq owner rolu ilə işləyəcək, W011)." >&2
fi

echo "→ 6/7 pgbouncer qaldırılır, release.sh (migrate + collectstatic)…"
docker compose -f "$COMPOSE_FILE" up -d pgbouncer
docker compose -f "$COMPOSE_FILE" run --rm -T -e RUN_RELEASE_ON_START=false app /app/docker/release.sh

echo "→ 7/7 Tətbiq qaldırılır və yoxlanılır…"
# Replika sayı deploy ilə eynidir (`up -d app` --scale-siz 1-ə endirirdi — 2026-09-15 düzəlişi).
APP_REPLICAS="${APP_REPLICAS:-$(dotenv_value APP_REPLICAS)}"; APP_REPLICAS="${APP_REPLICAS:-8}"
CELERY_REPLICAS="${CELERY_REPLICAS:-$(dotenv_value CELERY_REPLICAS)}"; CELERY_REPLICAS="${CELERY_REPLICAS:-2}"
docker compose -f "$COMPOSE_FILE" up -d --scale app="$APP_REPLICAS" --scale celery_worker="$CELERY_REPLICAS" "${WRITERS[@]}"
docker compose -f "$COMPOSE_FILE" up -d nginx
users="$(docker exec -i "$PG_CONTAINER" sh -c 'psql -At -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "select count(*) from auth_user;"')"
org="$(docker exec -i "$PG_CONTAINER" sh -c 'psql -At -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "select name || '"'"' / '"'"' || slug from organizations_organization order by created_at limit 1;"')"
legacy="$(docker exec -i "$PG_CONTAINER" sh -c 'psql -At -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "select count(*) from auth_user where username like '"'"'myedu.%'"'"';"')"
echo "   auth_user=${users} · təşkilat=${org} · myedu qalıq=${legacy}"
if [ -n "$EXPECTED_USERS" ] && [ "$users" != "$EXPECTED_USERS" ]; then
  echo "Gözlənilən istifadəçi sayı ${EXPECTED_USERS}, tapıldı ${users} — YOXLAYIN." >&2
  exit 1
fi
if [ "$legacy" != "0" ]; then
  echo "Hələ ${legacy} legacy myedu.* istifadəçi adı var — rename_legacy_usernames --apply işlədin." >&2
  exit 1
fi
docker compose -f "$COMPOSE_FILE" ps --format '{{.Name}} {{.Status}}' | grep -E 'app-|celery|pgbouncer|postgres' || true
echo "Seed tamamlandı."
