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
#   REUSE=1 ./scripts/dev-daphne.sh      # işləyirsə toxunma, sadəcə ünvanı yaz
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

# Portu tutan proses varsa: ÖZ köhnə daphne-mizdirsə əvəz edirik, yad prosesdirsə
# toxunmuruq. Əvvəl skript sadəcə xəta verib çıxırdı — nəticədə əvvəlki
# sessiyadan qalan daphne portu tutur, `ddaphne` isə hər dəfə «port tutulub»
# deyirdi və istifadəçi «girə bilmirəm» sanırdı (sahib şikayəti 2026-09-06).
BUSY="$(lsof -tnP -iTCP:"$PORT" -sTCP:LISTEN 2>/dev/null || true)"
if [ -n "$BUSY" ]; then
    OURS=""
    FOREIGN=""
    for pid in $BUSY; do
        CMD="$(ps -p "$pid" -o command= 2>/dev/null || true)"
        case "$CMD" in
            *"$PROJECT_DIR"*daphne*|*daphne*config.asgi*) OURS="$OURS $pid" ;;
            *) FOREIGN="$FOREIGN $pid ($CMD)" ;;
        esac
    done
    if [ -n "$FOREIGN" ]; then
        echo "✗ $PORT portunu YAD proses tutub:$FOREIGN" >&2
        echo "  Başqa portda qaldır:  PORT=8010 $0" >&2
        exit 1
    fi
    if [ "${REUSE:-}" = "1" ]; then
        echo "→ Onsuz da işləyir: http://$HOST:$PORT  (PID:$OURS)"
        exit 0
    fi
    echo "→ Köhnə daphne dayandırılır (PID:$OURS) …"
    # shellcheck disable=SC2086
    kill $OURS 2>/dev/null || true
    for _ in 1 2 3 4 5 6 7 8 9 10; do
        sleep 0.4
        lsof -tnP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1 || break
    done
    if lsof -tnP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
        # shellcheck disable=SC2086
        kill -9 $OURS 2>/dev/null || true
        sleep 1
    fi
fi

export DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE:-config.settings.local}"

echo "→ Daphne: http://$HOST:$PORT  (settings: $DJANGO_SETTINGS_MODULE)"
echo "  Dayandırmaq: Ctrl+C"
exec "$PY_BIN/daphne" -b "$HOST" -p "$PORT" config.asgi:application
