#!/usr/bin/env bash
# «Sistem monitorinqi → Loglar» diaqnostikası — OXU-YALNIZ (sahib 2026-10-17: «loglar boş göstərir»).
#
# İki rejim:
#   * `prod_audit.sh` §13 bunu `source` edir (ok/warn/section köməkçiləri və sayğaclar ortaqdır);
#   * `.github/workflows/prod-audit.yml` input `scope=logs` ilə TƏK işləyir (~40 s).
# Zəncir: promtail (docker_sd) → docker-socket-proxy → dockerd → promtail → Loki ← Django (app).
# Yalnız versiya, status, say, müddət və promtail/Loki-nin ÖZ log mesajlarının (`msg="…"`)
# sayı çap olunur — tətbiq log sətirlərinin məzmunu çap OLUNMUR. Heç nə dəyişmir.
set -uo pipefail
LOGS_DIAG_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if ! declare -F section >/dev/null 2>&1; then
  APP_DIR="${APP_DIR:-/home/wcu/EducationManagementStudentArena}"
  COMPOSE="docker compose -f docker-compose.prod.yml"
  cd "$APP_DIR" || { echo "APP_DIR tapılmadı: $APP_DIR"; exit 1; }
  WARN=0; FAIL=0
  ok()   { echo "- ✅ $*"; }
  warn() { echo "- ⚠️ $*"; WARN=$((WARN+1)); }
  bad()  { echo "- ❌ $*"; FAIL=$((FAIL+1)); }
  section() { echo; echo "## $*"; echo; }
  LOGS_DIAG_STANDALONE=1
  echo "# Prod loglar diaqnostikası — $(date -u +%Y-%m-%dT%H:%M:%SZ) — host \`$(hostname)\`"
fi

section "13. Loglar: promtail → docker-socket-proxy → Loki ← Django (yalnız say/status, məzmun yox)"
DV=$(docker version --format 'server {{.Server.Version}} · API {{.Server.APIVersion}} (min {{.Server.MinAPIVersion}})' 2>/dev/null || echo "oxunmadı")
echo "- ℹ️ Docker: $DV · promtail 3.1.1 Docker klienti API 1.44 danışır (min > 1.44 olsa docker_sd işləməz)"
DMIN=$(docker version --format '{{.Server.MinAPIVersion}}' 2>/dev/null)
if [ -n "$DMIN" ]; then
  awk -v m="$DMIN" 'BEGIN{ split(m,a,"."); exit !((a[1]+0) == 1 && (a[2]+0) <= 44) }' \
    && ok "dockerd minimum API $DMIN ≤ 1.44 (promtail docker_sd uyğundur)" \
    || bad "dockerd minimum API $DMIN > 1.44 — promtail 3.1.1 docker_sd konteynerləri görə bilmir (image yeniləməsi lazımdır)"
fi
for svc in loki promtail docker-socket-proxy; do
  cid=$($COMPOSE ps -q "$svc" 2>/dev/null | head -1)
  if [ -z "$cid" ]; then bad "$svc konteyneri işləmir"; continue; fi
  st=$(docker inspect --format '{{.State.Status}} health={{if .State.Health}}{{.State.Health.Status}}{{else}}n/a{{end}} restarts={{.RestartCount}} oom={{.State.OOMKilled}} başlayıb={{.State.StartedAt}} image={{.Config.Image}}' "$cid" 2>/dev/null)
  case "$st" in running*) ok "$svc: $st";; *) bad "$svc: $st";; esac
done
# promtail/Loki/proxy-nin ÖZ xəta mesajları (son 6 saat) — yalnız `msg="…"` mətni + say.
for svc in promtail loki docker-socket-proxy; do
  cid=$($COMPOSE ps -q "$svc" 2>/dev/null | head -1); [ -n "$cid" ] || continue
  NERR=$(docker logs --since 6h "$cid" 2>&1 | grep -cE 'level=(error|warn)|\[(WARNING|ALERT|NOTICE)\]' || true)
  echo "- ℹ️ $svc son 6 saat: ${NERR:-0} warn/error sətri"
  if [ "${NERR:-0}" -gt 0 ]; then
    echo '```'
    docker logs --since 6h "$cid" 2>&1 | grep -E 'level=(error|warn)' | grep -oE 'msg="[^"]{0,140}"' \
      | sort | uniq -c | sort -rn | head -8
    # 2026-10-17: xətanın SƏBƏBİ (`err="…"`) — komponentin öz xəta mətni (şəxsi məlumat deyil); IP, port,
    # 12+ simvolluq hex id-lər maskalanır ki, hesabatda yalnız xəta növü qalsın.
    docker logs --since 6h "$cid" 2>&1 | grep -E 'level=(error|warn)' | grep -oE 'err="[^"]{0,220}"' \
      | sed -E 's/[0-9]{1,3}(\.[0-9]{1,3}){3}(:[0-9]+)?/<ip>/g; s/[0-9a-f]{12,}/<id>/g' \
      | sort | uniq -c | sort -rn | head -6
    echo '```'
  fi
done
APPC=$($COMPOSE ps -q app 2>/dev/null | head -1)
if [ -z "$APPC" ]; then
  bad "app konteyneri yoxdur — Django tərəfi yoxlanmadı"
else
  echo "### 13.1 Django (app konteyneri) gözü ilə: Loki, promtail, Prometheus"
  echo '```'
  $COMPOSE exec -T --index 1 app python manage.py shell < "$LOGS_DIAG_DIR/prod_logs_probe.py" 2>&1 \
    | grep -v "objects imported" | tail -80
  echo '```'
fi

if [ "${LOGS_DIAG_STANDALONE:-0}" = "1" ]; then
  section "Yekun"
  echo "- ❌ kritik: **$FAIL** · ⚠️ xəbərdarlıq: **$WARN**"
fi
