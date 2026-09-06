#!/usr/bin/env bash
# CI-nin LINT işini LOKALDA, push-dan ƏVVƏL eyni ardıcıllıqla qaçırır.
#
# NİYƏ: `.github/workflows/_lint.yml` yeddi qapı işlədir; fayl-fayl `black`
# yoxlamaq kifayət etmir (isort, modul ölçüsü, modul sərhədi, i18n kataloqu və
# RLS worker-atomic əhatəsi repo-genişdir). 2026-09-06-da CI ard-arda dörd dəfə
# məhz bu səbəbdən düşdü.
#
# İstifadə:
#   ./scripts/preflight.sh          # yoxla (heç nə dəyişmir)
#   ./scripts/preflight.sh --fix    # black/isort-u avtomatik tətbiq et, sonra yoxla
set -uo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="$PROJECT_DIR/venv/bin"
cd "$PROJECT_DIR"

FIX=0
[ "${1:-}" = "--fix" ] && FIX=1

FAILED=()
step() {
    local label="$1"; shift
    if "$@" >/tmp/preflight.$$ 2>&1; then
        echo "✓ $label"
    else
        echo "✗ $label"
        tail -6 /tmp/preflight.$$ | sed 's/^/    /'
        FAILED+=("$label")
    fi
    rm -f /tmp/preflight.$$
}

if [ "$FIX" = "1" ]; then
    echo "→ black + isort tətbiq olunur…"
    "$PY/black" -q -l 120 . || true
    "$PY/isort" -q . || true
fi

step "black (format)"            "$PY/black" -l 120 --check .
step "isort (import sırası)"     "$PY/isort" --check-only .
step "flake8 (lint)"             "$PY/flake8" .
step "modul ölçüsü (600 sətir)"  "$PY/python" scripts/check_module_size.py --check
step "modul sərhədi (dövr)"      "$PY/python" scripts/module_deps.py --check
step "i18n kataloqu"             "$PY/python" scripts/check_i18n_catalogs.py
step "RLS worker-atomic"         "$PY/python" scripts/check_worker_atomic_coverage.py

echo
if [ ${#FAILED[@]} -eq 0 ]; then
    echo "✅ Bütün lint qapıları keçdi — push etmək olar."
    exit 0
fi
echo "❌ Düşən qapı(lar): ${FAILED[*]}"
echo "   Formatlaşdırma qapılarını avtomatik düzəltmək üçün: ./scripts/preflight.sh --fix"
exit 1
