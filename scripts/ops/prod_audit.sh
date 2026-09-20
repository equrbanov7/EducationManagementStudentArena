#!/usr/bin/env bash
# Prod server OXU-YALNIZ audit (sahib 2026-09-21): performans + təhlükəsizlik.
# Self-hosted runner (serverin özü) üzərində `.github/workflows/prod-audit.yml`
# tərəfindən işlədilir; Markdown hesabatı stdout-a yazır. Heç nə dəyişmir.
#   APP_DIR — canlı tətbiq qovluğu (docker-compose.prod.yml + .env)
set -uo pipefail
APP_DIR="${APP_DIR:-/home/wcu/EducationManagementStudentArena}"
COMPOSE="docker compose -f docker-compose.prod.yml"
cd "$APP_DIR" || { echo "APP_DIR tapılmadı: $APP_DIR"; exit 1; }

dotenv() { grep -E "^$1=" .env 2>/dev/null | head -1 | cut -d= -f2- | tr -d '"' | tr -d "'"; }
HOST="$(dotenv HEALTHCHECK_HOST)"; HOST="${HOST:-127.0.0.1}"
ADMIN_PREFIX="$(dotenv ADMIN_URL_PREFIX)"; ADMIN_PREFIX="${ADMIN_PREFIX:-manage/}"
WARN=0; FAIL=0
ok()   { echo "- ✅ $*"; }
warn() { echo "- ⚠️ $*"; WARN=$((WARN+1)); }
bad()  { echo "- ❌ $*"; FAIL=$((FAIL+1)); }
section() { echo; echo "## $*"; echo; }

echo "# Prod audit — $(date -u +%Y-%m-%dT%H:%M:%SZ) — host \`$(hostname)\`, Host başlığı \`$HOST\`"

section "1. Host resursları"
echo '```'
uptime; echo; nproc | sed 's/^/CPU: /'; free -m | sed -n 1,3p; df -h / | sed -n 1,2p
echo '```'
LOAD1=$(cut -d' ' -f1 /proc/loadavg); CPUS=$(nproc)
awk -v l="$LOAD1" -v c="$CPUS" 'BEGIN{ if (l > c) exit 1 }' && ok "load1 $LOAD1 ≤ CPU sayı $CPUS" || warn "load1 $LOAD1 > CPU sayı $CPUS"
DISK=$(df --output=pcent / | tail -1 | tr -dc '0-9'); [ "$DISK" -lt 80 ] && ok "disk /: ${DISK}%" || warn "disk /: ${DISK}% (≥80)"
MEMAV=$(free -m | awk '/Mem:/{print $7}'); [ "$MEMAV" -gt 1024 ] && ok "boş yaddaş ${MEMAV} MB" || warn "boş yaddaş cəmi ${MEMAV} MB"
UPG=$(apt list --upgradable 2>/dev/null | grep -c -- "-security" || true); [ "${UPG:-0}" -eq 0 ] && ok "gözləyən security update yoxdur" || warn "$UPG gözləyən security update (apt)"
if command -v needs-restarting >/dev/null 2>&1; then :; fi
[ -f /var/run/reboot-required ] && warn "reboot tələb olunur (/var/run/reboot-required)" || ok "reboot tələb olunmur"

section "2. Açıq portlar (0.0.0.0 / :: üzərində dinləyənlər)"
echo '```'
ss -tlnp 2>/dev/null | awk 'NR==1 || $4 ~ /^(0\.0\.0\.0|\*|\[::\]):/' | head -40
echo '```'
PUB=$(ss -tlnp 2>/dev/null | awk '$4 ~ /^(0\.0\.0\.0|\*|\[::\]):/{split($4,a,":"); print a[length(a)]}' | sort -un | tr '\n' ' ')
for port in $PUB; do
  case "$port" in 22|80|443) ;; *) warn "publik port: $port (yalnız 22/80/443 gözlənilir)";; esac
done
ok "publik portlar: ${PUB:-yoxdur}"
command -v ufw >/dev/null 2>&1 && { echo '```'; sudo -n ufw status 2>/dev/null || ufw status 2>/dev/null || echo "ufw status: sudo icazəsi yoxdur"; echo '```'; }
command -v fail2ban-client >/dev/null 2>&1 && { sudo -n fail2ban-client status 2>/dev/null | sed 's/^/    /' || echo "    fail2ban: status oxunmadı"; } || warn "fail2ban quraşdırılmayıb (SSH brute-force qoruması hostda yoxdur)"

section "3. Konteynerlər"
echo '```'
$COMPOSE ps --format 'table {{.Name}}\t{{.Status}}\t{{.Ports}}' 2>/dev/null | head -30
echo; docker stats --no-stream --format 'table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}' 2>/dev/null | head -25
echo '```'
for c in $($COMPOSE ps -q 2>/dev/null); do
  name=$(docker inspect --format '{{.Name}}' "$c" | sed 's#^/##'); st=$(docker inspect --format '{{.State.Status}} restarts={{.RestartCount}} health={{if .State.Health}}{{.State.Health.Status}}{{else}}n/a{{end}}' "$c")
  case "$st" in running\ restarts=0*) ;; *) warn "$name: $st";; esac
  u=$(docker inspect --format '{{.Config.User}}' "$c"); case "$name" in *app*|*celery*) [ -n "$u" ] && [ "$u" != "root" ] && [ "$u" != "0" ] || warn "$name root kimi işləyir (Config.User='$u')";; esac
done
ok "konteyner yoxlaması bitdi"

section "4. Fayl/konfiq gigiyenası"
P=$(stat -c %a .env 2>/dev/null); [ "$P" = "600" ] || [ "$P" = "640" ] && ok ".env icazəsi $P" || warn ".env icazəsi $P (600 gözlənilir)"
DBG=$(dotenv DEBUG); [ -z "$DBG" ] || [ "$DBG" = "False" ] || [ "$DBG" = "false" ] || [ "$DBG" = "0" ] && ok "DEBUG söndürülüb" || bad "DEBUG=$DBG (.env)"
for k in SECRET_KEY DATABASE_URL; do [ -n "$(dotenv $k)" ] && ok "$k təyin olunub" || bad "$k boşdur"; done
[ "$(dotenv INSECURE_TRANSPORT_OK)" = "1" ] && warn "INSECURE_TRANSPORT_OK=1 (TLS məcburiyyəti söndürülüb)" || ok "TLS məcburiyyəti aktivdir"
[ -n "$(dotenv ADMIN_ALLOWED_IPS)" ] && ok "ADMIN_ALLOWED_IPS təyin olunub" || warn "ADMIN_ALLOWED_IPS boşdur — admin paneli IP ilə məhdudlaşmayıb"
[ "$(dotenv ADMIN_2FA_REQUIRED)" = "False" ] && bad "ADMIN_2FA_REQUIRED=False" || ok "admin 2FA məcburidir"
GS=$(git status --porcelain 2>/dev/null | wc -l | tr -d ' '); [ "$GS" = "0" ] && ok "APP_DIR git ağacı təmizdir" || warn "APP_DIR-də $GS izlənməyən/dəyişmiş fayl (rsync artığı?)"
for f in docker/nginx/certs/origin.key; do [ -f "$f" ] && { p=$(stat -c %a "$f"); [ "$p" = "600" ] || [ "$p" = "640" ] && ok "$f icazəsi $p" || warn "$f icazəsi $p"; }; done

section "5. nginx + HTTP başlıqları (https://127.0.0.1, Host: $HOST)"
$COMPOSE exec -T nginx nginx -t >/dev/null 2>&1 && ok "nginx -t keçdi" || bad "nginx -t xəta verdi"
hdr() { curl -sk -o /dev/null -D - --max-time 15 -H "Host: $HOST" "https://127.0.0.1$1" 2>/dev/null; }
H=$(hdr /accounts/login/)
echo '```'; echo "$H" | grep -iE "^(HTTP|strict-transport|content-security|x-frame|x-content-type|referrer-policy|permissions-policy|server|set-cookie|cross-origin)" | sed 's/\r$//' | cut -c1-200; echo '```'
echo "$H" | grep -qi "^strict-transport-security" && ok "HSTS var" || bad "HSTS başlığı yoxdur"
echo "$H" | grep -qi "^content-security-policy" && ok "CSP var" || bad "CSP başlığı yoxdur"
echo "$H" | grep -qi "^x-frame-options" && ok "X-Frame-Options var" || bad "X-Frame-Options yoxdur"
echo "$H" | grep -qi "^x-content-type-options" && ok "X-Content-Type-Options var" || bad "X-Content-Type-Options yoxdur"
echo "$H" | grep -qi "^referrer-policy" && ok "Referrer-Policy var" || warn "Referrer-Policy yoxdur"
echo "$H" | grep -qi "^permissions-policy" && ok "Permissions-Policy var" || warn "Permissions-Policy yoxdur"
SRV=$(echo "$H" | grep -i "^server:" | head -1 | sed 's/\r$//'); echo "$SRV" | grep -qiE "nginx/[0-9]" && warn "Server başlığı versiya açıqlayır ($SRV) — server_tokens off tövsiyə olunur" || ok "Server versiyası gizlidir ($SRV)"
echo "$H" | grep -i "^set-cookie: csrftoken" | grep -qi "secure" && ok "csrftoken cookie Secure" || warn "csrftoken cookie Secure deyil"
echo "$H" | grep -i "^set-cookie: csrftoken" | grep -qi "samesite" && ok "csrftoken SameSite təyin olunub" || warn "csrftoken SameSite yoxdur"
code() { curl -sk -o /dev/null -w '%{http_code}' --max-time 15 -H "Host: $HOST" "https://127.0.0.1$1" 2>/dev/null; }
echo "| Yol | Status |"; echo "|---|---|"
for p in /ping/ /health/ "/$ADMIN_PREFIX" /metrics/ /accounts/login/ /static/css/design-tokens.css /.env /admin/ /.git/config; do echo "| \`$p\` | $(code "$p") |"; done
[ "$(code /.env)" = "404" ] || [ "$(code /.env)" = "403" ] || bad "/.env açıqdır!"
[ "$(code /.git/config)" = "404" ] || [ "$(code /.git/config)" = "403" ] || bad "/.git/config açıqdır!"
HTTP80=$(curl -s -o /dev/null -w '%{http_code} %{redirect_url}' --max-time 10 -H "Host: $HOST" "http://127.0.0.1/accounts/login/" 2>/dev/null); echo "$HTTP80" | grep -q "^30[12] https" && ok "HTTP→HTTPS yönləndirmə ($HTTP80)" || warn "HTTP→HTTPS yönləndirmə yoxdur ($HTTP80)"
CERT=$(echo | openssl s_client -connect 127.0.0.1:443 -servername "$HOST" 2>/dev/null | openssl x509 -noout -enddate -subject 2>/dev/null | tr '\n' ' '); echo "- sertifikat: \`${CERT:-oxunmadı}\`"
if [ -n "$CERT" ]; then END=$(echo "$CERT" | sed -n 's/.*notAfter=\([^s]*subject\).*/\1/p' | sed 's/subject//'); EXP=$(date -d "$END" +%s 2>/dev/null || echo 0); NOW=$(date +%s); DAYS=$(( (EXP-NOW)/86400 )); [ "$EXP" -gt 0 ] && { [ "$DAYS" -gt 21 ] && ok "sertifikat $DAYS gün etibarlıdır" || warn "sertifikat $DAYS gündən sonra bitir"; }; fi

section "6. Cavab vaxtları (anonim, nginx üzərindən, 5 ölçmə/orta ms)"
echo "| Yol | Status | Orta ms | Maks ms |"; echo "|---|---|---|---|"
for p in /ping/ /accounts/login/ /static/css/design-tokens.css /static/js/ems_early.js; do
  tot=0; mx=0; st=000
  for i in 1 2 3 4 5; do r=$(curl -sk -o /dev/null -w '%{http_code} %{time_total}' --max-time 20 -H "Host: $HOST" "https://127.0.0.1$p" 2>/dev/null); st=${r%% *}; t=${r##* }; ms=$(awk -v t="$t" 'BEGIN{printf "%d", t*1000}'); tot=$((tot+ms)); [ "$ms" -gt "$mx" ] && mx=$ms; done
  echo "| \`$p\` | $st | $((tot/5)) | $mx |"
done

section "7. Django: check --deploy"
echo '```'
$COMPOSE exec -T --index 1 app python manage.py check --deploy 2>&1 | tail -25
echo '```'

section "8. Verilənlər bazası + tətbiq daxili performans zondu"
echo '```'
$COMPOSE exec -T --index 1 -e PROBE_HOST="$HOST" app python manage.py shell < scripts/ops/prod_perf_probe.py 2>&1 | grep -v "objects imported" | tail -120
echo '```'

section "9. nginx access log — son 20000 sətirdə ən yavaş/ən çox 5xx"
LOG=$($COMPOSE logs --no-log-prefix --tail 20000 nginx 2>/dev/null)
echo '```'
echo "$LOG" | grep -oE '" [0-9]{3} ' | sort | uniq -c | sort -rn | head -8 | sed 's/^/status /'
echo "-- 5xx nümunələri:"; echo "$LOG" | grep -E '" 5[0-9]{2} ' | tail -5 | cut -c1-180
echo "-- rt= ən yavaş 8:"; echo "$LOG" | grep -oE '"(GET|POST) [^ ]+ [^"]*" [0-9]{3} .*rt=[0-9.]+' | awk '{match($0,/rt=[0-9.]+/); rt=substr($0,RSTART+3,RLENGTH-3); print rt, $2}' | sort -rn | head -8
echo '```'

section "Yekun"
echo "- ❌ kritik: **$FAIL** · ⚠️ xəbərdarlıq: **$WARN**"
exit 0
