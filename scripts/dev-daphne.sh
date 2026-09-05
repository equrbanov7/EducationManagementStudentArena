#!/usr/bin/env bash
# EMSArena — dev daphne-ni ÖN PLANDA başladır (loglar elə terminalda görünür).
#
# NİYƏ AYRICA SKRİPT (2026-09-06):
#   `ddaphne` bir zsh ALIAS-ıdır (~/.zshrc). Alias YALNIZ o faylı oxumuş
#   interaktiv zsh-də mövcuddur: VS Code-un terminalı bash-dırsa, ya da
#   terminal alias əlavə olunmazdan ƏVVƏL açılıbsa — «command not found».
#   Bu skript alias-dan, PATH-dan və cari qovluqdan ASILI DEYİL: hər yerdən,
#   hər shell-dən işləyir.
#
# İstifadə:
#   ./scripts/dev-daphne.sh              # 127.0.0.1:8000, ön planda (Ctrl+C dayandırır)
#   PORT=8010 ./scripts/dev-daphne.sh    # başqa port
#   HOST=0.0.0.0 ./scripts/dev-daphne.sh # LAN-dan görünsün (telefon/başqa kompüter)
#
# Arxa fonda + köhnə prosesin təmizlənməsi lazımdırsa: scripts/restart-daphne.sh
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT="${PORT:-8000}"
# Default 127.0.0.1: dev serveri şəbəkəyə açmaq ŞÜURLU seçim olmalıdır (HOST=0.0.0.0).
HOST="${HOST:-127.0.0.1}"
PY_BIN="$PROJECT_DIR/venv/bin"

cd "$PROJECT_DIR"

if [ ! -x "$PY_BIN/daphne" ]; then
    echo "✗ $PY_BIN/daphne tapılmadı — virtual mühit qurulmayıb?" >&2
    echo "  Həll: python3 -m venv venv && ./venv/bin/pip install -r requirements/local.txt" >&2
    exit 1
fi

# Portu tutan köhnə proses varsa dərhal xəbər ver (səssiz ölümün qarşısını alır).
BUSY="$(lsof -tnP -iTCP:"$PORT" -sTCP:LISTEN 2>/dev/null || true)"
if [ -n "$BUSY" ]; then
    echo "✗ $PORT portu artıq tutulub (PID: $BUSY)." >&2
    echo "  Təmiz restart üçün: ./scripts/restart-daphne.sh" >&2
    echo "  Yalnız öldürmək üçün: kill $BUSY" >&2
    exit 1
fi

export DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE:-config.settings.local}"

echo "→ Daphne: http://$HOST:$PORT  (settings: $DJANGO_SETTINGS_MODULE)"
echo "  Dayandırmaq: Ctrl+C"
exec "$PY_BIN/daphne" -b "$HOST" -p "$PORT" config.asgi:application
