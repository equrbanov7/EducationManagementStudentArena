#!/bin/sh
# ═══════════════════════════════════════════════════════════════════════════
# EMS Arena — celery beat start sarğısı (docker-compose.prod.yml `celery_beat`)
# ═══════════════════════════════════════════════════════════════════════════
# Enerji kəsilməsi (sahib 2026-10-07): PersistentScheduler cədvəli (shelve/dbm)
# /tmp/celerybeat-schedule-dədir — konteynerin yazıla bilən qatı restart-dan və
# host reboot-undan sağ çıxır. Kəsilmə anında yarımçıq yazılmış fayl:
#   - açıla bilmirsə Celery özü silib yenisini yaradır;
#   - AÇILIRSA, amma qeydin pickle-ı pozulubsa (`entries`), setup_schedule()
#     UnpicklingError/EOFError ilə çökür → konteyner dayanır → restart → eyni
#     fayl → CRASH-LOOP (beat işləmir, interval task-lar icra olunmur).
# Həll: beat-dən ƏVVƏL faylı yalnız-oxu rejimində açıb bütün qeydləri oxuyuruq;
# istənilən xəta (və ya yoxlamanın özünün çökməsi/asılması) → fayl(lar) silinir,
# beat təmiz cədvəllə başlayır. İtki yoxdur: interval task-ların növbəti icra vaxtı
# yenidən hesablanır (ən çox bir neçə task bir dəfə tez/gec işləyir).
#
# İstifadə (compose command): sh start.sh celery -A config beat ... --schedule <fayl>
# Arqumentlər olduğu kimi `exec` olunur — skript yalnız `--schedule`/`-s` yolunu oxuyur.
# Image-ə deyil, bind-mount ilə gəlir: rollback-da köhnə image ilə də işləyir.
# Test: tests/test_infra_power_outage_selfheal.py (korlanmış/sağlam cədvəl).
set -eu

if [ "$#" -eq 0 ]; then
  echo "istifadə: start.sh celery -A config beat ... --schedule <fayl>" >&2
  exit 64
fi

schedule=""
prev=""
for arg in "$@"; do
  case "$prev" in
    --schedule|-s) schedule="$arg" ;;
  esac
  case "$arg" in
    --schedule=*) schedule="${arg#--schedule=}" ;;
  esac
  prev="$arg"
done

PYTHON_BIN="${PYTHON_BIN:-python}"
# Tək dırnaq içindədir — Python mətnində tək dırnaq olmamalıdır.
CHECK_PY='
import shelve, sys
try:
    with shelve.open(sys.argv[1], flag="r") as db:
        for key in list(db.keys()):
            db[key]
except Exception as exc:
    print("celery-beat: schedule check failed: %s: %s" % (type(exc).__name__, exc), file=sys.stderr)
    sys.exit(1)
'

schedule_present() {
  for f in "$1" "$1".*; do
    if [ -e "$f" ]; then
      return 0
    fi
  done
  return 1
}

check_schedule() {
  if command -v timeout >/dev/null 2>&1; then
    timeout 60 "$PYTHON_BIN" -c "$CHECK_PY" "$1"
  else
    "$PYTHON_BIN" -c "$CHECK_PY" "$1"
  fi
}

if [ -n "$schedule" ] && schedule_present "$schedule"; then
  if check_schedule "$schedule"; then
    echo "celery-beat: schedule '$schedule' oxunaqlıdır — saxlanılır"
  else
    echo "celery-beat: schedule '$schedule' korlanıb/oxunmur (enerji kəsilməsi?) — silinir, beat təmiz cədvəllə başlayır" >&2
    rm -f "$schedule"
    for f in "$schedule".*; do
      if [ -e "$f" ]; then
        rm -f "$f"
      fi
    done
  fi
fi

exec "$@"
