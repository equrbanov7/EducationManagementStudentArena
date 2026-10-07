#!/bin/sh
# ═══════════════════════════════════════════════════════════════════════════
# EMS Arena — PgBouncer start sarğısı (docker-compose.prod.yml `pgbouncer`)
# ═══════════════════════════════════════════════════════════════════════════
# Təhlükəsizlik auditi 2026-10-07: pgbouncer_exporter əvvəl owner/superuser
# (ADMIN_USERS) ilə admin konsola qoşulurdu — exporter-in ələ keçməsi PAUSE /
# KILL / SHUTDOWN və owner parolu demək idi. İndi MONITOR_DB_USER və
# MONITOR_DB_PASSWORD İKİSİ DƏ verilibsə:
#   1. userlist.txt-ə `"<user>" "<parol>"` sətri yazılır (auth_type
#      scram-sha-256 düz parolla işləyir; image entrypoint-i owner sətrini
#      əvvəlki kimi özü əlavə edir);
#   2. STATS_USERS-ə istifadəçi əlavə olunur → pgbouncer.ini `stats_users`
#      (yalnız SHOW əmrləri; admin_users-ə DÜŞMÜR).
# Biri boşdursa / dəyər təhlükəsiz deyilsə heç nə dəyişmir: image entrypoint-i
# köhnə kimi işləyir və exporter compose fallback-i ilə owner girişində qalır.
# Parol çap olunmur; pgbouncer prosesinin mühitindən silinir.
# PGBOUNCER_IMAGE_ENTRYPOINT / AUTH_FILE yalnız test üçün override-dır.
set -eu

auth_file="${AUTH_FILE:-/etc/pgbouncer/userlist.txt}"
image_entrypoint="${PGBOUNCER_IMAGE_ENTRYPOINT:-/entrypoint.sh}"

monitor_user="${MONITOR_DB_USER:-}"
monitor_password="${MONITOR_DB_PASSWORD:-}"
unset MONITOR_DB_PASSWORD

if [ -n "$monitor_user" ] && [ -n "$monitor_password" ]; then
  reason=""
  case "$monitor_user" in
    [!a-z_]* | *[!a-z0-9_]*) reason="MONITOR_DB_USER is not a plain lower-case identifier" ;;
  esac
  # Yalnız URI/userlist/psql üçün qaçırmasız simvollar (prod-secrets-generate urlsafe yaradır).
  case "$monitor_password" in
    *[!A-Za-z0-9._~-]*) reason="MONITOR_DB_PASSWORD has characters outside [A-Za-z0-9._~-]" ;;
  esac
  if [ "${#monitor_password}" -lt 16 ]; then
    reason="MONITOR_DB_PASSWORD is shorter than 16 characters"
  fi
  # Owner adı ilə eyni olsa image entrypoint-i owner sətrini yazmazdı (artıq var sayardı) →
  # bütün tətbiq bağlantıları monitor parolu ilə yoxlanardı. Heç vaxt.
  case ",${ADMIN_USERS:-postgres}," in
    *",${monitor_user},"*) reason="MONITOR_DB_USER equals a pgbouncer admin user" ;;
  esac

  if [ -z "$reason" ]; then
    (umask 077 && touch "$auth_file")
    # Image-dəki fayl 644-dür; parollar konteyner daxilində də yalnız pgbouncer istifadəçisinə.
    chmod 600 "$auth_file" 2>/dev/null || true
    if ! grep -q "^\"${monitor_user}\" " "$auth_file"; then
      (umask 077 && printf '"%s" "%s"\n' "$monitor_user" "$monitor_password" >>"$auth_file")
    fi
    STATS_USERS="${STATS_USERS:+${STATS_USERS},}${monitor_user}"
    export STATS_USERS
    echo "pgbouncer: stats-only console user '${monitor_user}' enabled"
  else
    echo "pgbouncer: monitor user NOT enabled (${reason}); exporter stays on the owner login" >&2
  fi
fi
unset monitor_password

exec "$image_entrypoint" "$@"
