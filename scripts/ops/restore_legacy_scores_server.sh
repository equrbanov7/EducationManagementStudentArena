#!/usr/bin/env bash
#
# restore_legacy_scores_server.sh — SERVER addımı: J12 bərpa planının tətbiqi (2026-09-25)
# ======================================================================================
#
# Mənbə (MariaDB) serverdə LAZIM DEYİL: plan lokalda qurulub
# (scripts/ops/restore_legacy_scores_build_plan.sh), bura yalnız plan faylı + sha256 gəlir.
#
# İstifadə (APP_DIR-də, hostda):
#   scripts/ops/restore_legacy_scores_server.sh check   <plan.jsonl.gz> <sha256> <actor>
#   scripts/ops/restore_legacy_scores_server.sh dry-run <plan.jsonl.gz> <sha256> <actor>
#   scripts/ops/restore_legacy_scores_server.sh apply   <plan.jsonl.gz> <sha256> <actor>
#
#   check   — faylın sha256-sı + konteynerə köçürmə (yazı yoxdur)
#   dry-run — canlı bazaya qarşı TAM qərar cədvəli (yazı yoxdur)
#   apply   — əvvəl ehtiyat nüsxə (backup.sh), sonra --apply --i-know-this-is-production,
#             sonra İKİNCİ icra (0 dəyişiklik gözlənilir — idempotentlik sübutu)
#
# Mühit: APP_CONTAINER=educationmanagementstudentarena-app-1
#        BACKUP_CONTAINER=emsarena-postgres-backup  ORG=qku  APP_OWNER=appuser:appgroup
#
# Qeyd: `docker cp` faylı konteynerdə root:root yaradır, tətbiq isə `appuser` (uid 999)
# kimi işləyir — plan 0600 qalır, amma sahibi `appuser` edilir; apply-dan sonra
# konteynerdəki nüsxə silinir (host-dakı nüsxə sübut kimi saxlanılır).
set -euo pipefail

MODE="${1:?check | dry-run | apply}"
PLAN="${2:?plan faylı (.jsonl.gz)}"
SHA="${3:?planın manifestdəki sha256-sı}"
ACTOR="${4:?audit aktoru (superadmin username)}"
APP_CONTAINER="${APP_CONTAINER:-educationmanagementstudentarena-app-1}"
BACKUP_CONTAINER="${BACKUP_CONTAINER:-emsarena-postgres-backup}"
ORG="${ORG:-qku}"
APP_OWNER="${APP_OWNER:-appuser:appgroup}"
IN_CONTAINER="/tmp/$(basename "$PLAN")"

echo "$SHA  $PLAN" | sha256sum -c -
docker cp "$PLAN" "$APP_CONTAINER:$IN_CONTAINER"
docker exec -u 0 "$APP_CONTAINER" sh -c "chown $APP_OWNER '$IN_CONTAINER' && chmod 0600 '$IN_CONTAINER'"

run() {
    docker exec -i "$APP_CONTAINER" python manage.py legacy_repair_lesson_recovery \
        --organization "$ORG" --actor "$ACTOR" --plan "$IN_CONTAINER" --plan-sha256 "$SHA" "$@"
}

case "$MODE" in
check)
    echo "✓ sha256 uyğundur, plan konteynerdədir: $IN_CONTAINER"
    ;;
dry-run)
    run --show 60
    ;;
apply)
    echo "== ehtiyat nüsxə (tətbiqdən ƏVVƏL)"
    docker exec "$BACKUP_CONTAINER" /backup.sh
    echo "== tətbiq"
    run --apply --i-know-this-is-production --show 20
    echo "== ikinci icra (idempotentlik: FAKTİKİ … yaradıldı = 0 gözlənilir)"
    run --apply --i-know-this-is-production --show 5
    docker exec -u 0 "$APP_CONTAINER" rm -f "$IN_CONTAINER"
    ;;
*)
    echo "naməlum rejim: $MODE" >&2
    exit 2
    ;;
esac
