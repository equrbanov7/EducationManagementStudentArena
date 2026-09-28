#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
# EMS Arena — requirements lock fayllarını yenidən yaradır (Audit 2026-09-28 AD-06)
# ═══════════════════════════════════════════════════════════════════════════
# requirements/*.txt əl ilə saxlanılan GİRİŞ fayllarıdır (yalnız birbaşa
# asılılıqlar, `==` pin). Bu skript onlardan TAM (keçid asılılıqları daxil),
# hash-li, universal (linux/macOS, Python 3.11+) lock-lar qurur:
#
#   requirements/production.lock  ← production.txt  (docker/Dockerfile.prod)
#   requirements/test.lock        ← test.txt        (CI unit/RLS/e2e/build)
#
# Quraşdırma həmişə `pip install --require-hashes -r requirements/<x>.lock`.
#
# İstifadə:
#   scripts/deps/lock.sh            # mövcud pin-lər saxlanılır, yalnız yeni/dəyişən
#                                   # giriş üçün həll edilir (minimal diff)
#   scripts/deps/lock.sh --upgrade  # bütün keçid asılılıqları ən son uyğun versiyaya
#   scripts/deps/lock.sh --check    # lock-lar giriş faylları ilə uyğundurmu (CI/əl)
#
# Birbaşa versiyanı dəyişmək: əvvəl requirements/<x>.txt-də pin-i dəyiş, sonra
# bu skripti işlət və HƏR İKİ faylı birlikdə commit et. Dependabot `.txt`
# fayllarını yeniləyir — onun PR-ında da bu skript işlədilməlidir.
# Ətraflı: docs/operations/DEPENDENCY_LOCK.md
# ═══════════════════════════════════════════════════════════════════════════
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
REQ_DIR="$ROOT_DIR/requirements"
UV_VERSION="${UV_VERSION:-0.12.19}"
PYTHON_FLOOR="${LOCK_PYTHON_VERSION:-3.11}"
MODE="${1:-}"

uv_bin() {
  if command -v uv >/dev/null 2>&1; then
    command -v uv
    return
  fi
  local tool_dir="${TMPDIR:-/tmp}/emsarena-uv-${UV_VERSION}"
  if [ ! -x "$tool_dir/bin/uv" ]; then
    python3 -m venv "$tool_dir" >&2
    "$tool_dir/bin/pip" install --quiet "uv==${UV_VERSION}" >&2
  fi
  printf '%s\n' "$tool_dir/bin/uv"
}

UV="$(uv_bin)"

compile() {
  local input="$1" output="$2"
  shift 2
  (
    # Nisbi yol: annotasiyaya (# via --override …) maşından asılı mütləq yol düşməsin.
    cd "$REQ_DIR"
    "$UV" pip compile "$input" \
      --universal \
      --python-version "$PYTHON_FLOOR" \
      --generate-hashes \
      --no-header \
      --annotation-style line \
      --index-url https://pypi.org/simple \
      --quiet \
      --override ../scripts/deps/overrides.txt \
      --output-file "$output" \
      "$@"
  )
}

case "$MODE" in
  --check)
    tmp="$(mktemp -d)"
    trap 'rm -rf "$tmp"' EXIT
    status=0
    for name in production test; do
      cp "$REQ_DIR/${name}.lock" "$tmp/${name}.lock"
      compile "${name}.txt" "$tmp/${name}.lock"
      if ! diff -q "$REQ_DIR/${name}.lock" "$tmp/${name}.lock" >/dev/null; then
        echo "requirements/${name}.lock is out of date — run scripts/deps/lock.sh" >&2
        status=1
      fi
    done
    exit "$status"
    ;;
  --upgrade)
    compile production.txt production.lock --upgrade
    compile test.txt test.lock --upgrade
    ;;
  "")
    compile production.txt production.lock
    compile test.txt test.lock
    ;;
  *)
    echo "Usage: $0 [--upgrade|--check]" >&2
    exit 2
    ;;
esac

echo "Lock files updated: requirements/production.lock requirements/test.lock"
