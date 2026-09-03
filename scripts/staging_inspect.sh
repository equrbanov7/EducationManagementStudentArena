#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
# EMS Arena — Staging Inspection mühiti
# ═══════════════════════════════════════════════════════════════════════════
# Legacy köçürmə məşqinin (rehearsal) nəticələrini HƏQİQİ EMS Arena UI-ında
# nəzərdən keçirmək üçün ayrılmış lokal mühit:
#
#   * ayrıca PostgreSQL (docker-compose.staging.yml, 127.0.0.1:55433) —
#     dev DB-dən də, agent sandbox-undan da tam izolyasiya;
#   * ayrıca settings modulu (config/settings/staging_inspect.py) — iki
#     kilidlə səhv bazaya qoşulmanın qarşısını alır;
#   * runserver production-dakı kimi NOSUPERUSER/NOBYPASSRLS tətbiq rolu ilə
#     işləyir, yəni RLS davranışı güzgülənir. Miqrasiyalar owner rolundadır.
#
# İKİ NÖV HƏDƏF BAZA (ikisi də EYNİ konteynerdə):
#   1. bootstrap bazası  — emsarena_staging (initdb yaradır, sabitdir);
#   2. rehearsal bazaları — emsarena_rehearsal_<12 hex>, orkestrator-un
#      fail-closed hədəf qapısını (ad şablonu + 'disposable' GUC + loopback
#      non-5432 + NOSUPERUSER rol + dolu django_migrations) ödəyir.
#
# İstifadə:
#   scripts/staging_inspect.sh migrate            # bootstrap bazası
#   scripts/staging_inspect.sh manage <əmr>       # ixtiyari manage.py əmri
#   scripts/staging_inspect.sh rehearsal-init     # yeni rehearsal bazası
#   STAGING_POSTGRES_DB=emsarena_rehearsal_ab12cd34ef56 \
#       scripts/staging_inspect.sh serve          # məşq datasına bax
# ═══════════════════════════════════════════════════════════════════════════
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="${ROOT_DIR}/docker-compose.staging.yml"
PROJECT_NAME="${EMS_STAGING_PROJECT:-emsarena-staging}"
STAGING_CONTAINER="${EMS_STAGING_CONTAINER:-emsarena-staging-pg}"
STAGING_IMAGE="${EMS_STAGING_IMAGE:-postgres:16-alpine}"

# Orkestratorun hədəf qapısı ilə eyni şablon (fail-closed).
REHEARSAL_DB_RE='^emsarena_rehearsal_[a-f0-9]{12}$'
REHEARSAL_GUC="emsarena.rehearsal_target"
REHEARSAL_GUC_VALUE="disposable"

# --- Konfiqurasiya (hamısı env ilə override oluna bilər) --------------------
# Bootstrap bazası initdb tərəfindən yaradılır və DƏYİŞMİR: compose env-i və
# healthcheck ona bağlıdır. Konteynerin POSTGRES_DB-si həmişə budur.
STAGING_BOOTSTRAP_DB="${STAGING_BOOTSTRAP_DB:-emsarena_staging}"
# Django-nun hədəf bazası — STAGING_POSTGRES_DB (və ya STAGING_DB_NAME) ilə
# override olunur; bütün komandalar (serve/migrate/superuser/psql/dsn) bunu
# oxuyur.
STAGING_DB_NAME="${STAGING_DB_NAME:-${STAGING_POSTGRES_DB:-$STAGING_BOOTSTRAP_DB}}"
STAGING_DB_PORT="${STAGING_DB_PORT:-55433}"
STAGING_OWNER_USER="${STAGING_OWNER_USER:-emsarena_staging}"
STAGING_OWNER_PASSWORD="${STAGING_OWNER_PASSWORD:-emsarena_staging_password}"
STAGING_APP_USER="${STAGING_APP_USER:-emsarena_app}"
STAGING_APP_PASSWORD="${STAGING_APP_PASSWORD:-emsarena_staging_app_password}"
INSPECT_PORT="${EMS_INSPECT_PORT:-8100}"
STAGING_SUPERUSER_USERNAME="${STAGING_SUPERUSER_USERNAME:-staging_admin}"
STAGING_SUPERUSER_EMAIL="${STAGING_SUPERUSER_EMAIL:-staging-admin@emsarena.local}"

# docker-compose.staging.yml eyni dəyərləri görsün deyə ixrac edirik.
# DİQQƏT: POSTGRES_DB həmişə bootstrap bazasıdır — əks halda hədəf bazanı
# dəyişdikdə compose konteyneri yenidən yaradar və healthcheck sınar.
export STAGING_POSTGRES_DB="$STAGING_BOOTSTRAP_DB"
export STAGING_POSTGRES_USER="$STAGING_OWNER_USER"
export STAGING_POSTGRES_PASSWORD="$STAGING_OWNER_PASSWORD"
export STAGING_POSTGRES_PORT="$STAGING_DB_PORT"

usage() {
    cat <<'USAGE'
Usage: scripts/staging_inspect.sh <command> [args...]

Commands:
  up                    Ayrılmış staging PostgreSQL-i qaldır və healthy olmasını gözlə.
  migrate               up + bütün miqrasiyalar (owner rolu) + tətbiq rolunun provision-u.
  superuser [--auto]    Django superadmin yarat (interaktiv, və ya --auto ilə
                        avtomatik parol — parol BİR DƏFƏ ekrana yazılır).
  serve [args...]       up + miqrasiya/check qapıları + runserver 127.0.0.1:<PORT>
                        (tətbiq rolu ilə, yəni RLS production kimi işləyir).
  psql [args...]        Owner rolu ilə hədəf bazada psql aç.
  dsn [--owner]         Hədəf baza üçün tətbiq (default) / owner DSN-ini çap et.
  reset [--yes]         DİQQƏT: volume-u silib bazanı sıfırdan qurur (bütün data itir).
  down                  Konteyneri dayandır (data volume-da qalır).
  status                compose ps + rehearsal bazalarının siyahısı.

  rehearsal-init        Yeni birdəfəlik məşq bazası yarat: emsarena_rehearsal_<12 hex>,
                        'disposable' GUC, tam miqrasiya, tətbiq rolu grant-ları və
                        superadmin. Sonda DSN-ləri və serve komandasını çap edir.
  rehearsal-list        Konteynerdəki məşq bazaları + ölçüləri.
  rehearsal-drop <ad> [--yes]
                        Şablona uyğun məşq bazasını sil (başqa adı QƏBUL ETMİR).
  help                  Bu mətn.

Hədəf baza seçimi:
  Bütün komandalar STAGING_POSTGRES_DB (və ya STAGING_DB_NAME) dəyişənini oxuyur:

      STAGING_POSTGRES_DB=emsarena_rehearsal_ab12cd34ef56 \
          scripts/staging_inspect.sh serve

  İcazə verilən adlar YALNIZ: emsarena_staging (bootstrap) və
  emsarena_rehearsal_<12 hex>. Başqa ad fail-closed rədd olunur.
  Konteynerin öz POSTGRES_DB env-i həmişə bootstrap bazası olaraq qalır.

Environment overrides:
  STAGING_POSTGRES_DB / STAGING_DB_NAME   (hədəf baza; default emsarena_staging)
  STAGING_DB_PORT=55433
  STAGING_OWNER_USER=emsarena_staging
  STAGING_OWNER_PASSWORD=emsarena_staging_password
  STAGING_APP_USER=emsarena_app
  STAGING_APP_PASSWORD=emsarena_staging_app_password
  EMS_INSPECT_PORT=8100
  EMS_INSPECT_PYTHON=<python yolu>   (default: .venv/bin/python, sonra venv/bin/python)
  STAGING_SUPERUSER_USERNAME / STAGING_SUPERUSER_EMAIL
USAGE
}

compose() {
    docker compose -f "$COMPOSE_FILE" -p "$PROJECT_NAME" "$@"
}

ensure_docker() {
    if ! command -v docker >/dev/null 2>&1; then
        echo "Docker tələb olunur (staging inspection PostgreSQL)." >&2
        exit 1
    fi
    if ! docker compose version >/dev/null 2>&1; then
        echo "Docker Compose v2 tələb olunur." >&2
        exit 1
    fi
}

resolve_python() {
    if [ -n "${EMS_INSPECT_PYTHON:-}" ]; then
        echo "$EMS_INSPECT_PYTHON"
    elif [ -x "${ROOT_DIR}/.venv/bin/python" ]; then
        echo "${ROOT_DIR}/.venv/bin/python"
    elif [ -x "${ROOT_DIR}/venv/bin/python" ]; then
        echo "${ROOT_DIR}/venv/bin/python"
    else
        echo "python3"
    fi
}

is_rehearsal_db() {
    [[ $1 =~ $REHEARSAL_DB_RE ]]
}

# Fail-closed: launcher yalnız bootstrap və ya rehearsal bazasına toxuna bilər.
assert_allowed_db() {
    local name="$1"
    if [ "$name" = "$STAGING_BOOTSTRAP_DB" ] || is_rehearsal_db "$name"; then
        return 0
    fi
    echo "İcazəsiz hədəf baza: '${name}'." >&2
    echo "Yalnız '${STAGING_BOOTSTRAP_DB}' və ya emsarena_rehearsal_<12 hex> qəbul olunur." >&2
    exit 1
}

owner_dsn_for() {
    printf 'postgres://%s:%s@127.0.0.1:%s/%s\n' \
        "$STAGING_OWNER_USER" "$STAGING_OWNER_PASSWORD" "$STAGING_DB_PORT" "$1"
}

app_dsn_for() {
    printf 'postgres://%s:%s@127.0.0.1:%s/%s\n' \
        "$STAGING_APP_USER" "$STAGING_APP_PASSWORD" "$STAGING_DB_PORT" "$1"
}

# manage <DATABASE_URL> <EMS_DB_ROLE_ENFORCE> [manage.py args...]
#
# .env-ə TOXUNMURUQ: local.py-dakı load_dotenv() override=False ilə işlədiyi
# üçün burada ixrac etdiyimiz dəyişənlər .env dəyərlərini üstələyir.
# EMS_STAGING_DB_NAME DSN-dən çıxarılır ki, settings interlock-u hədəf bazanı
# (bootstrap və ya rehearsal) qəbul etsin; port isə SABİT qalır.
manage() {
    local db_url="$1"
    shift
    local enforce="$1"
    shift
    local db_name="${db_url##*/}"
    assert_allowed_db "$db_name"
    local py
    py="$(resolve_python)"

    EMS_STAGING_INSPECT=1 \
    DJANGO_SETTINGS_MODULE=config.settings.staging_inspect \
    DATABASE_URL="$db_url" \
    EMS_STAGING_DB_NAME="$db_name" \
    EMS_STAGING_DB_PORT="$STAGING_DB_PORT" \
    EMS_DB_ROLE_ENFORCE="$enforce" \
    DEBUG=True \
    USE_REDIS=False \
    ENABLE_NGROK=False \
    ALLOWED_HOSTS="localhost,127.0.0.1" \
    SITE_URL="http://127.0.0.1:${INSPECT_PORT}" \
        "$py" "${ROOT_DIR}/manage.py" "$@"
}

# psql_admin <db> [psql args...] — owner rolu ilə, konteynerin içindən.
psql_admin() {
    local db="$1"
    shift
    docker exec -i -e PGPASSWORD="$STAGING_OWNER_PASSWORD" "$STAGING_CONTAINER" \
        psql -v ON_ERROR_STOP=1 -U "$STAGING_OWNER_USER" -d "$db" "$@"
}

wait_healthy() {
    local tries="${1:-60}"
    local status
    while [ "$tries" -gt 0 ]; do
        status="$(docker inspect -f '{{.State.Health.Status}}' "$STAGING_CONTAINER" 2>/dev/null || echo unknown)"
        if [ "$status" = "healthy" ]; then
            return 0
        fi
        sleep 1
        tries=$((tries - 1))
    done
    echo "PostgreSQL healthy olmadı (konteyner: $STAGING_CONTAINER)." >&2
    compose ps >&2 || true
    return 1
}

do_up() {
    compose up -d postgres
    wait_healthy 60
    echo "✓ Staging PostgreSQL hazırdır: 127.0.0.1:${STAGING_DB_PORT} (hədəf baza: ${STAGING_DB_NAME})"
}

# ---------------------------------------------------------------------------
# Tətbiq rolunun provision-u
# ---------------------------------------------------------------------------
# scripts/provision-app-db-role.sh konteynerin İÇİNDƏ `psql -U $POSTGRES_USER
# -d $POSTGRES_DB` işlədir, yəni grant-ları konteynerin öz POSTGRES_DB-sinə
# (bootstrap bazasına) tətbiq edir. Grant-lar isə baza-spesifikdir.
#
# Rehearsal bazası üçün SQL-i dublikat etmirik (dublikat sürüşərsə append-only
# ledger REVOKE-ları səssizcə itə bilər). Əvəzində eyni skripti hədəf bazaya
# yönəldirik: PG konteynerinin şəbəkə namespace-ini paylaşan qısa ömürlü
# sidecar qaldırılır, onun POSTGRES_DB-si hədəf bazadır.
provision_app_role_for_db() {
    local target_db="$1"
    assert_allowed_db "$target_db"

    if [ "$target_db" = "$STAGING_BOOTSTRAP_DB" ]; then
        echo "→ Tətbiq rolu ('${STAGING_APP_USER}') provision olunur → ${target_db}…"
        POSTGRES_CONTAINER="$STAGING_CONTAINER" \
        APP_DATABASE_USER="$STAGING_APP_USER" \
        APP_DATABASE_PASSWORD="$STAGING_APP_PASSWORD" \
            "${ROOT_DIR}/scripts/provision-app-db-role.sh"
        return
    fi

    local sidecar="emsarena-staging-provision-$$"
    echo "→ Tətbiq rolu ('${STAGING_APP_USER}') provision olunur → ${target_db} (sidecar)…"
    docker rm -f "$sidecar" >/dev/null 2>&1 || true
    docker run -d --name "$sidecar" \
        --network "container:${STAGING_CONTAINER}" \
        -e PGHOST=127.0.0.1 \
        -e PGPORT=5432 \
        -e PGPASSWORD="$STAGING_OWNER_PASSWORD" \
        -e POSTGRES_USER="$STAGING_OWNER_USER" \
        -e POSTGRES_DB="$target_db" \
        --entrypoint sleep \
        "$STAGING_IMAGE" 600 >/dev/null

    local rc=0
    POSTGRES_CONTAINER="$sidecar" \
    APP_DATABASE_USER="$STAGING_APP_USER" \
    APP_DATABASE_PASSWORD="$STAGING_APP_PASSWORD" \
        "${ROOT_DIR}/scripts/provision-app-db-role.sh" || rc=$?
    docker rm -f "$sidecar" >/dev/null 2>&1 || true
    return "$rc"
}

do_manage() {
    # İxtiyari `manage.py` alt-komandası hədəf bazaya qarşı (owner rolu ilə).
    # `migrate`/`serve` üçün ayrıca funksiyalar var; bu, `shell`, `showmigrations`,
    # `createsuperuser`, `dbshell` kimi gündəlik əməllər üçündür.
    if [ "$#" -eq 0 ]; then
        echo "İstifadə: $0 manage <əmr> [arqumentlər]   (məs. manage showmigrations)" >&2
        return 2
    fi
    do_up
    manage "$(owner_dsn_for "$STAGING_DB_NAME")" off "$@"
}

do_migrate() {
    do_up
    # Miqrasiyalar owner (superuser) rolu ilə işləyir — bu qanunidir, ona görə
    # RLS rol yoxlaması bu addımda "off".
    manage "$(owner_dsn_for "$STAGING_DB_NAME")" off migrate "$@"
    provision_app_role_for_db "$STAGING_DB_NAME"
}

do_serve() {
    do_up
    local app_url
    app_url="$(app_dsn_for "$STAGING_DB_NAME")"

    # Qapı 1 — sxem tam tətbiq olunubmu? (tətbiq rolu ilə oxunur)
    if ! manage "$app_url" error migrate --check >/dev/null 2>&1; then
        echo "Staging bazasının ('${STAGING_DB_NAME}') sxemi tam deyil (tətbiq olunmamış" >&2
        echo "miqrasiyalar var və ya tətbiq rolu hələ provision olunmayıb)." >&2
        if is_rehearsal_db "$STAGING_DB_NAME"; then
            echo "Run: scripts/staging_inspect.sh rehearsal-init" >&2
        else
            echo "Run: scripts/staging_inspect.sh migrate" >&2
        fi
        exit 1
    fi

    # Qapı 2 — DB check-ləri (RLS rol yoxlaması daxil, enforce=error).
    # Bu qapı superuser/BYPASSRLS rolu ilə xidmət göstərməyi bloklayır;
    # ONU KEÇMƏK ÜÇÜN enforce-u endirməyin — rolu düzəldin.
    manage "$app_url" error check --database default

    echo "→ Staging inspection: http://127.0.0.1:${INSPECT_PORT}/"
    echo "  (DB: ${STAGING_DB_NAME}@127.0.0.1:${STAGING_DB_PORT}, rol: ${STAGING_APP_USER})"
    manage "$app_url" error runserver "127.0.0.1:${INSPECT_PORT}" --noreload "$@"
}

# auto_superuser <owner_dsn> → parolu STDOUT-a yazır (loglar STDERR-ə).
auto_superuser() {
    local owner_dsn="$1"
    shift
    local py password
    py="$(resolve_python)"
    password="$("$py" -c 'import secrets; print(secrets.token_urlsafe(24))')"

    DJANGO_SUPERUSER_USERNAME="$STAGING_SUPERUSER_USERNAME" \
    DJANGO_SUPERUSER_EMAIL="$STAGING_SUPERUSER_EMAIL" \
    DJANGO_SUPERUSER_PASSWORD="$password" \
        manage "$owner_dsn" off createsuperuser --noinput "$@" >&2

    printf '%s\n' "$password"
}

print_superuser_banner() {
    local db="$1" password="$2"
    cat <<EOF

═══════════════════════════════════════════════════════════════
  Staging inspection superadmin (YALNIZ lokal staging bazası)
  Bu parol BİR DƏFƏ göstərilir — indi yadda saxlayın.

    Baza:     ${db}
    URL:      http://127.0.0.1:${INSPECT_PORT}/accounts/login/muellim/
    Username: ${STAGING_SUPERUSER_USERNAME}
    Password: ${password}
═══════════════════════════════════════════════════════════════
EOF
}

do_superuser() {
    local auto=0
    if [ "${1:-}" = "--auto" ]; then
        auto=1
        shift
    fi
    do_up
    local owner_url
    owner_url="$(owner_dsn_for "$STAGING_DB_NAME")"

    if [ "$auto" -eq 0 ]; then
        manage "$owner_url" off createsuperuser "$@"
        return
    fi

    local password
    password="$(auto_superuser "$owner_url" "$@")"
    print_superuser_banner "$STAGING_DB_NAME" "$password"
}

do_reset() {
    local confirmed=0
    if [ "${1:-}" = "--yes" ]; then
        confirmed=1
        shift
    fi
    if [ "$confirmed" -eq 0 ]; then
        if [ -t 0 ]; then
            printf 'Staging volume-u SİLİNƏCƏK (bütün məşq datası itir). Davam? [yes/N] '
            local answer
            read -r answer
            [ "$answer" = "yes" ] || { echo "Ləğv edildi."; exit 1; }
        else
            echo "reset destruktivdir: interaktiv olmayan mühitdə --yes tələb olunur." >&2
            exit 1
        fi
    fi
    compose down -v
    STAGING_DB_NAME="$STAGING_BOOTSTRAP_DB"
    do_migrate "$@"
}

# ---------------------------------------------------------------------------
# Rehearsal (məşq) bazaları — orkestratorun fail-closed hədəf qapısı üçün
# ---------------------------------------------------------------------------
rehearsal_init() {
    do_up
    local py name owner_url app_url password
    py="$(resolve_python)"
    name="$("$py" -c 'import secrets; print("emsarena_rehearsal_" + secrets.token_hex(6))')"
    assert_allowed_db "$name"

    echo "→ Məşq bazası yaradılır: ${name}"
    # CREATE DATABASE tranzaksiyada işləmir — hər biri ayrıca -c ilə.
    psql_admin postgres -c "CREATE DATABASE \"${name}\" OWNER \"${STAGING_OWNER_USER}\";" >/dev/null
    psql_admin postgres \
        -c "ALTER DATABASE \"${name}\" SET ${REHEARSAL_GUC} = '${REHEARSAL_GUC_VALUE}';" >/dev/null

    owner_url="$(owner_dsn_for "$name")"
    app_url="$(app_dsn_for "$name")"

    echo "→ Miqrasiyalar tətbiq olunur (owner rolu)… bu bir neçə dəqiqə çəkir."
    manage "$owner_url" off migrate

    provision_app_role_for_db "$name"

    echo "→ Superadmin yaradılır…"
    password="$(auto_superuser "$owner_url")"

    echo
    echo "→ Orkestrator hədəf qapısının yoxlanışı:"
    rehearsal_verify "$name"

    print_superuser_banner "$name" "$password"

    cat <<EOF

Məşq bazası hazırdır.

  Baza adı:   ${name}
  Owner DSN:  ${owner_url}
  App DSN:    ${app_url}

  UI-da baxmaq üçün:
    STAGING_POSTGRES_DB=${name} scripts/staging_inspect.sh serve

  psql:
    STAGING_POSTGRES_DB=${name} scripts/staging_inspect.sh psql
EOF
}

rehearsal_verify() {
    local name="$1"
    local guc migrations role_attrs
    guc="$(psql_admin "$name" -tAc "SELECT coalesce(current_setting('${REHEARSAL_GUC}', true), '(NULL)');")"
    migrations="$(psql_admin "$name" -tAc "SELECT count(*) FROM django_migrations;")"
    role_attrs="$(psql_admin "$name" -tAc \
        "SELECT rolsuper::text || '/' || rolbypassrls::text FROM pg_roles WHERE rolname = '${STAGING_APP_USER}';")"

    if is_rehearsal_db "$name"; then
        echo "  [1] ad şablonu emsarena_rehearsal_<12 hex> ....... OK (${name})"
    else
        echo "  [1] ad şablonu ................................... FAIL (${name})"
    fi
    echo "  [2] ${REHEARSAL_GUC} .............. ${guc}"
    echo "  [3] loopback host + non-5432 port ................ 127.0.0.1:${STAGING_DB_PORT}"
    echo "  [4] ${STAGING_APP_USER} rolsuper/rolbypassrls ............ ${role_attrs}"
    echo "  [5] django_migrations sətir sayı ................. ${migrations}"
}

rehearsal_list() {
    psql_admin postgres -c "
        SELECT datname AS baza,
               pg_size_pretty(pg_database_size(datname)) AS olcu,
               coalesce((
                   SELECT split_part(s, '=', 2)
                   FROM unnest(coalesce(d.setconfig, ARRAY[]::text[])) AS s
                   WHERE s LIKE '${REHEARSAL_GUC}=%'
               ), '(yoxdur)') AS rehearsal_target
        FROM pg_database
        LEFT JOIN pg_db_role_setting d ON d.setdatabase = pg_database.oid AND d.setrole = 0
        WHERE datname ~ '${REHEARSAL_DB_RE}'
        ORDER BY datname;"
}

rehearsal_drop() {
    local name="${1:-}"
    if [ -z "$name" ]; then
        echo "İstifadə: scripts/staging_inspect.sh rehearsal-drop <baza-adı> [--yes]" >&2
        exit 2
    fi
    shift
    if ! is_rehearsal_db "$name"; then
        echo "RƏDD EDİLDİ: '${name}' məşq bazası şablonuna uyğun deyil." >&2
        echo "Yalnız emsarena_rehearsal_<12 hex> bazaları silinə bilər." >&2
        exit 1
    fi

    local confirmed=0
    if [ "${1:-}" = "--yes" ]; then
        confirmed=1
    fi
    if [ "$confirmed" -eq 0 ]; then
        if [ -t 0 ]; then
            printf "'%s' bazası SİLİNƏCƏK. Davam? [yes/N] " "$name"
            local answer
            read -r answer
            [ "$answer" = "yes" ] || { echo "Ləğv edildi."; exit 1; }
        else
            echo "rehearsal-drop destruktivdir: interaktiv olmayan mühitdə --yes tələb olunur." >&2
            exit 1
        fi
    fi
    # Baza birdəfəlikdir ('disposable'), ona görə açıq sessiyalar zorla bağlanır.
    psql_admin postgres -c "DROP DATABASE IF EXISTS \"${name}\" WITH (FORCE);"
    echo "✓ Silindi: ${name}"
}

assert_allowed_db "$STAGING_DB_NAME"

command="${1:-help}"
if [ "$#" -gt 0 ]; then
    shift
fi

ensure_docker
cd "$ROOT_DIR"

case "$command" in
    up)
        do_up
        ;;
    migrate)
        do_migrate "$@"
        ;;
    manage)
        do_manage "$@"
        ;;
    superuser)
        do_superuser "$@"
        ;;
    serve)
        do_serve "$@"
        ;;
    psql)
        do_up >/dev/null
        compose exec postgres psql -U "$STAGING_OWNER_USER" -d "$STAGING_DB_NAME" "$@"
        ;;
    dsn)
        if [ "${1:-}" = "--owner" ]; then
            owner_dsn_for "$STAGING_DB_NAME"
        else
            app_dsn_for "$STAGING_DB_NAME"
        fi
        ;;
    reset)
        do_reset "$@"
        ;;
    down)
        compose down
        ;;
    status)
        compose ps
        echo
        echo "Məşq bazaları:"
        rehearsal_list
        ;;
    rehearsal-init)
        rehearsal_init "$@"
        ;;
    rehearsal-list)
        do_up >/dev/null
        rehearsal_list
        ;;
    rehearsal-drop)
        do_up >/dev/null
        rehearsal_drop "$@"
        ;;
    help | -h | --help)
        usage
        ;;
    *)
        echo "Naməlum komanda: $command" >&2
        usage >&2
        exit 2
        ;;
esac
