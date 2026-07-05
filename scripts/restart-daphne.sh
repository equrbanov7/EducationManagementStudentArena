#!/bin/zsh
# EMSArena dev daphne-ni ETİBARLI şəkildə yenidən başladır.
#
# Problem: daphne kodu avtomatik yeniləmir və köhnə proses portu tutub qalanda
# yeni daphne səssizcə ölür — köhnə dizayn görünməyə davam edir.
# Bu skript: 8000-dəki BÜTÜN prosesləri öldürür → portun boşalmasını gözləyir →
# təzə daphne başladır → HTTP cavabını yoxlayır. Uğursuzluqda qışqırır.
#
# İstifadə:  ./scripts/restart-daphne.sh
set -euo pipefail

PORT=8000
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LOG_FILE="/tmp/emsarena-daphne.log"

cd "$PROJECT_DIR"

echo "→ Port $PORT təmizlənir..."
# screen sessiyası varsa bağla (adı ilə), sonra portdakı hər şeyi öldür.
screen -S emsarena-daphne -X quit 2>/dev/null || true
PIDS=$(lsof -tnP -iTCP:$PORT -sTCP:LISTEN 2>/dev/null || true)
if [[ -n "$PIDS" ]]; then
    echo "  köhnə proseslər: $PIDS"
    kill $PIDS 2>/dev/null || true
    sleep 2
    # Hələ də sağdırsa güclə öldür.
    PIDS=$(lsof -tnP -iTCP:$PORT -sTCP:LISTEN 2>/dev/null || true)
    if [[ -n "$PIDS" ]]; then
        kill -9 $PIDS 2>/dev/null || true
        sleep 1
    fi
fi

if [[ -n "$(lsof -tnP -iTCP:$PORT -sTCP:LISTEN 2>/dev/null || true)" ]]; then
    echo "✗ Port $PORT boşalmadı — əl ilə yoxlayın: lsof -nP -iTCP:$PORT" >&2
    exit 1
fi

# Tətbiq olunmamış migrasiya varsa avtomatik tətbiq et — əks halda yeni kod
# köhnə sxemlə 500 verir (2026-07-06: teacher_note sütunu halı).
echo "→ Migrasiyalar yoxlanılır..."
if ! ./venv/bin/python manage.py migrate --check >/dev/null 2>&1; then
    echo "  tətbiq olunmamış migrasiya tapıldı — migrate işlədilir..."
    ./venv/bin/python manage.py migrate 2>&1 | tail -3
fi

echo "→ Daphne başladılır (log: $LOG_FILE)..."
screen -dmS emsarena-daphne zsh -lc "cd '$PROJECT_DIR' && exec env DJANGO_SETTINGS_MODULE=config.settings.local ./venv/bin/daphne -b 0.0.0.0 -p $PORT config.asgi:application >> '$LOG_FILE' 2>&1"

# Serverin qalxmasını gözlə (maks 15s).
for i in {1..15}; do
    sleep 1
    if [[ -n "$(lsof -tnP -iTCP:$PORT -sTCP:LISTEN 2>/dev/null || true)" ]]; then
        HTTP=$(curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:$PORT/accounts/login/" || echo "000")
        if [[ "$HTTP" == "200" ]]; then
            NEW_PID=$(lsof -tnP -iTCP:$PORT -sTCP:LISTEN | head -1)
            echo "✓ Daphne işləyir (PID $NEW_PID, HTTP $HTTP) — http://127.0.0.1:$PORT"
            exit 0
        fi
    fi
done

echo "✗ Daphne qalxmadı — log-a baxın: tail -30 $LOG_FILE" >&2
tail -15 "$LOG_FILE" >&2 || true
exit 1
