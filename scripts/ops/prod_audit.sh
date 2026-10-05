#!/usr/bin/env bash
# Prod server OXU-YALNIZ audit (sahib 2026-09-21): performans + təhlükəsizlik.
# Self-hosted runner (serverin özü) üzərində `.github/workflows/prod-audit.yml`
# tərəfindən işlədilir; Markdown hesabatı stdout-a yazır. Heç nə dəyişmir.
#   APP_DIR — canlı tətbiq qovluğu (docker-compose.prod.yml + .env)
# §10 (sahib 2026-10-04): tutum/konfiqurasiya — host/kernel, disk, .env tutum
# açarları, konteyner limitləri, Daphne/Celery/PostgreSQL/PgBouncer/Redis/nginx
# faktiki parametrləri və Prometheus 24s/7g tarixçəsi (resurs boşdur/doymuşdur?).
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
if command -v fail2ban-client >/dev/null 2>&1 || systemctl list-unit-files 2>/dev/null | grep -q '^fail2ban'; then
  FB=$(systemctl is-active fail2ban 2>/dev/null || echo unknown); [ "$FB" = "active" ] && ok "fail2ban aktivdir" || warn "fail2ban quraşdırılıb amma aktiv deyil ($FB)"
else
  warn "fail2ban quraşdırılmayıb (SSH brute-force qoruması hostda yoxdur; 22 publikdir)"
fi
SSHPW=$(sshd -T 2>/dev/null | awk '/^passwordauthentication/{print $2}'); [ -n "$SSHPW" ] && { [ "$SSHPW" = "no" ] && ok "SSH parol girişi bağlıdır" || warn "SSH PasswordAuthentication=$SSHPW (yalnız açar tövsiyə olunur)"; }

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
[ -n "$(dotenv SECRET_KEY)" ] && ok "SECRET_KEY təyin olunub" || bad "SECRET_KEY boşdur"
# DB girişi ya DATABASE_URL, ya da compose-un yığdığı POSTGRES_* ilə gəlir (canlı serverdə ikincidir).
{ [ -n "$(dotenv DATABASE_URL)" ] || [ -n "$(dotenv POSTGRES_PASSWORD)" ]; } && ok "DB girişi (.env) təyin olunub" || bad "nə DATABASE_URL, nə POSTGRES_PASSWORD təyin olunub"
[ "$(dotenv INSECURE_TRANSPORT_OK)" = "1" ] && warn "INSECURE_TRANSPORT_OK=1 (TLS məcburiyyəti söndürülüb)" || ok "TLS məcburiyyəti aktivdir"
[ -n "$(dotenv ADMIN_ALLOWED_IPS)" ] && ok "ADMIN_ALLOWED_IPS təyin olunub" || warn "ADMIN_ALLOWED_IPS boşdur — admin paneli IP ilə məhdudlaşmayıb"
[ "$(dotenv ADMIN_2FA_REQUIRED)" = "False" ] && bad "ADMIN_2FA_REQUIRED=False" || ok "admin 2FA məcburidir"
# Canlı qovluq rsync ilə runner checkout-undan doldurulur; APP_DIR-in öz .git-i köçürülmür
# (köhnə HEAD) — ona görə `git status` yalnış «dəyişib» deyir. Düzgün müqayisə: checkout ↔ APP_DIR
# (checksum, runtime istisnaları ilə). GITHUB_WORKSPACE yoxdursa bu yoxlama ötürülür.
if [ -n "${GITHUB_WORKSPACE:-}" ] && [ -f "$GITHUB_WORKSPACE/scripts/deploy/rsync-excludes.txt" ]; then
  DIFF=$(rsync -rcn --out-format='%n' --exclude-from="$GITHUB_WORKSPACE/scripts/deploy/rsync-excludes.txt" "$GITHUB_WORKSPACE/" "$APP_DIR/" 2>/dev/null | grep -v '/$' | wc -l | tr -d ' ')
  [ "$DIFF" = "0" ] && ok "APP_DIR canlı kodu deploy olunan commit ilə eynidir (rsync checksum)" || { warn "APP_DIR-də $DIFF fayl deploy olunan commit-dən fərqlənir"; echo '```'; rsync -rcn --out-format='%n' --exclude-from="$GITHUB_WORKSPACE/scripts/deploy/rsync-excludes.txt" "$GITHUB_WORKSPACE/" "$APP_DIR/" 2>/dev/null | grep -v '/$' | head -12; echo '```'; }
fi
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
echo "- ℹ️ \`/metrics/\` və \`/health/\` 127.0.0.1-dən 200 gözləniləndir (allow-list daxili şəbəkə); kənar IP-dən 403 olmalıdır — bu zond onu yoxlaya bilmir."
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

# ─────────────────────────────────────────────────────────────────────────────
# 10. Tutum / konfiqurasiya (sahib 2026-10-04): «serverin bütün resursları
# həqiqətən işləyirmi, konfiq yerindədirmi (CPU/RAM/worker/DB/cache)?».
# Hamısı OXU-YALNIZ. Sirr çap olunmur: DB sorğuları konteynerin ÖZ
# $POSTGRES_USER/$POSTGRES_DB mühitində işləyir (parol heç yerə çıxmır), Redis
# REDISCLI_AUTH ilə autentifikasiya edir, pgbouncer.ini yalnız tutum açarları
# üzrə grep olunur ([databases] sətri çap olunmur), .env-dən yalnız ağ siyahıdakı
# sirr olmayan açarlar oxunur. Prometheus 127.0.0.1:${PROMETHEUS_PORT:-9090}
# (compose yalnız loopback-ə publish edir) — anlıq `docker stats` əvəzinə
# 24 saat / 7 gün tarixçə: resursun boş qalması və ya doyması buradan görünür.
# ─────────────────────────────────────────────────────────────────────────────
section "10. Tutum / konfiqurasiya (capacity) — resurslar həqiqətən istifadə olunurmu?"

echo "### 10.1 Host avadanlığı və kernel"
echo '```'
echo "virt: $(systemd-detect-virt 2>/dev/null || echo '?')"
lscpu 2>/dev/null | grep -E '^(Model name|Hypervisor vendor|CPU\(s\)|Thread\(s\) per core|Core\(s\) per socket|Socket\(s\)|NUMA node\(s\)|CPU( max)? MHz)' | sed 's/  */ /g'
echo "nproc: $(nproc) · loadavg: $(cat /proc/loadavg) · $(uptime -p 2>/dev/null)"
top -bn1 2>/dev/null | sed -n '3p'
free -m
echo "swappiness=$(sysctl -n vm.swappiness 2>/dev/null) overcommit_memory=$(sysctl -n vm.overcommit_memory 2>/dev/null) max_map_count=$(sysctl -n vm.max_map_count 2>/dev/null) somaxconn=$(sysctl -n net.core.somaxconn 2>/dev/null) netdev_max_backlog=$(sysctl -n net.core.netdev_max_backlog 2>/dev/null) tcp_max_syn_backlog=$(sysctl -n net.ipv4.tcp_max_syn_backlog 2>/dev/null) file-max=$(sysctl -n fs.file-max 2>/dev/null) nr_open=$(sysctl -n fs.nr_open 2>/dev/null) ip_local_port_range=$(sysctl -n net.ipv4.ip_local_port_range 2>/dev/null | tr '\t' '-')"
echo "THP: $(cat /sys/kernel/mm/transparent_hugepage/enabled 2>/dev/null) · defrag: $(cat /sys/kernel/mm/transparent_hugepage/defrag 2>/dev/null)"
docker info --format 'docker {{.ServerVersion}} · cgroup {{.CgroupDriver}}/v{{.CgroupVersion}} · storage {{.Driver}} · kernel {{.KernelVersion}} · {{.OperatingSystem}} · NCPU {{.NCPU}} · MemTotal {{.MemTotal}} · live-restore {{.LiveRestoreEnabled}}' 2>/dev/null
echo '```'
SWAPUSED=$(free -m | awk '/Swap:/{print $3}'); [ "${SWAPUSED:-0}" -lt 512 ] && ok "swap istifadəsi ${SWAPUSED} MB" || warn "swap istifadəsi ${SWAPUSED} MB (RAM sıxlığı?)"
THP=$(grep -o '\[.*\]' /sys/kernel/mm/transparent_hugepage/enabled 2>/dev/null | tr -d '[]'); case "$THP" in always) warn "THP=always (Redis/PostgreSQL üçün madvise/never tövsiyə olunur)";; "") ;; *) ok "THP=$THP";; esac
OVC=$(sysctl -n vm.overcommit_memory 2>/dev/null); [ "${OVC:-1}" = "1" ] && ok "vm.overcommit_memory=1" || warn "vm.overcommit_memory=${OVC} (Redis AOF rewrite/fork üçün 1 tövsiyə olunur — sahib qərarı)"

echo
echo "### 10.2 Disk və Docker həcmləri"
echo '```'
df -h / /var/lib/docker 2>/dev/null | awk 'NR==1 || !seen[$0]++'
echo; docker system df 2>/dev/null
echo; docker system df -v 2>/dev/null | awk '/^Local Volumes space usage/{f=1} f' | grep -E 'VOLUME NAME|_(postgres_data|redis_data|media_data|static_data|prometheus_data|grafana_data|alertmanager_data|loki_data|promtail_positions|piston_packages)' | awk '{printf "%-62s %s\n", $1, $NF}'
echo '```'

echo
echo "### 10.3 .env tutum açarları (yalnız sirr olmayanlar; — = compose/deploy defoltu)"
echo '```'
for k in APP_REPLICAS CELERY_REPLICAS ASGI_THREADS MAX_INFLIGHT_REQUESTS MAX_INFLIGHT_WAIT_SECONDS CELERY_WORKER_CONCURRENCY CELERY_HEAVY_CONCURRENCY CELERY_PREFETCH_MULTIPLIER APP_MEM_LIMIT CELERY_CPU_LIMIT CELERY_MEM_LIMIT CELERY_HEAVY_MEM_LIMIT CELERY_BEAT_MEM_LIMIT POSTGRES_MAX_CONNECTIONS POSTGRES_SHARED_BUFFERS POSTGRES_EFFECTIVE_CACHE_SIZE POSTGRES_WORK_MEM POSTGRES_MAINTENANCE_WORK_MEM POSTGRES_MEM_LIMIT POSTGRES_JIT POSTGRES_LOG_MIN_DURATION_MS PGBOUNCER_POOL_MODE PGBOUNCER_DEFAULT_POOL_SIZE PGBOUNCER_MIN_POOL_SIZE PGBOUNCER_RESERVE_POOL_SIZE PGBOUNCER_MAX_CLIENT_CONN PGBOUNCER_MAX_DB_CONNECTIONS PGBOUNCER_QUERY_WAIT_TIMEOUT PGBOUNCER_CPU_LIMIT PGBOUNCER_MEM_LIMIT DATABASE_CONN_MAX_AGE RLS_TRANSACTION_SCOPED REDIS_MAXMEMORY REDIS_MEM_LIMIT REDIS_CPU_LIMIT REDIS_CACHE_MAX_CONNECTIONS CHANNEL_LAYER_CAPACITY NGINX_CPU_LIMIT NGINX_MEM_LIMIT CADVISOR_CPU_LIMIT CADVISOR_MEM_LIMIT PROMETHEUS_RETENTION_TIME PROMETHEUS_MEM_LIMIT LOKI_MEM_LIMIT PROMTAIL_MEM_LIMIT GRAFANA_MEM_LIMIT EXAM_START_GLOBAL_CONCURRENCY EXAM_START_PER_EXAM_CONCURRENCY; do
  v="$(dotenv "$k")"; printf '%-34s %s\n' "$k" "${v:-—}"
done
echo '```'

echo
echo "### 10.4 Konteynerlərə tətbiq olunan limitlər (docker inspect) və replika sayı"
echo '```'
$COMPOSE ps --format '{{.Service}}' 2>/dev/null | sort | uniq -c | awk '{printf "%s×%s  ", $2, $1} END{print ""}'
printf '%-56s %6s %8s %6s %8s %s\n' NAME CPUs MEM_MB PIDs RESTART OOM/HEALTH
TOTMEM=0; TOTCPU=0
for c in $($COMPOSE ps -q 2>/dev/null); do
  line=$(docker inspect --format '{{.Name}} {{.HostConfig.NanoCpus}} {{.HostConfig.Memory}} {{if .HostConfig.PidsLimit}}{{.HostConfig.PidsLimit}}{{else}}0{{end}} {{.RestartCount}} {{.State.OOMKilled}} {{if .State.Health}}{{.State.Health.Status}}{{else}}n/a{{end}}' "$c" 2>/dev/null) || continue
  [ -z "$line" ] && continue
  # shellcheck disable=SC2086  # qəsdən: inspect sətrini sahələrə bölürük
  set -- $line
  name=${1#/}; nano=${2:-0}; membytes=${3:-0}
  cpus=$(awk -v n="$nano" 'BEGIN{ if (n>0) printf "%.2f", n/1e9; else printf "∞" }')
  memmb=$(( membytes / 1048576 )); TOTMEM=$((TOTMEM+memmb))
  TOTCPU=$(awk -v a="$TOTCPU" -v n="$nano" 'BEGIN{printf "%.2f", a + (n>0 ? n/1e9 : 0)}')
  printf '%-56s %6s %8s %6s %8s %s\n' "$name" "$cpus" "$([ "$memmb" -gt 0 ] && echo "$memmb" || echo ∞)" "${4:-?}" "${5:-?}" "oom=${6:-?} health=${7:-?}"
done
echo "-- yaddaş tavanlarının cəmi: ${TOTMEM} MB · CPU tavanlarının cəmi (yalnız limitli olanlar): ${TOTCPU} nüvə (app/postgres/heavy qəsdən limitsiz)"
echo '```'
RAMMB=$(free -m | awk '/Mem:/{print $2}')
[ "$TOTMEM" -le "$RAMMB" ] && ok "yaddaş tavanlarının cəmi ${TOTMEM} MB ≤ RAM ${RAMMB} MB" || warn "yaddaş tavanlarının cəmi ${TOTMEM} MB > RAM ${RAMMB} MB (tavan rezervasiya deyil; hamısı eyni anda dolsa OOM-killer işə düşər)"
NEAR=$(docker stats --no-stream --format '{{.Name}} {{.MemPerc}}' 2>/dev/null | tr -d '%' | awk '$2+0 >= 85 {print $1, $2}')
while read -r n p; do [ -n "$n" ] && warn "$n yaddaş limitinin ${p}%-ində (OOM-kill riski → limit artırılmalı və ya istehlak azaldılmalı)"; done <<< "$NEAR"
[ -z "$NEAR" ] && ok "heç bir konteyner yaddaş limitinin 85%-ini keçməyib (anlıq)"

echo
echo "### 10.5 Tətbiq serveri — Daphne (replika başına 1 proses; sync view-lar thread-lərdə, tavan MAX_INFLIGHT_REQUESTS)"
echo '```'
APPN=0; FIRSTAPP=""
for c in $($COMPOSE ps -q app 2>/dev/null); do
  APPN=$((APPN+1)); [ -z "$FIRSTAPP" ] && FIRSTAPP="$c"
  printf '%s: ' "$(docker inspect --format '{{.Name}}' "$c" 2>/dev/null | sed 's#^/##')"
  docker exec "$c" sh -c 'grep -E "^(Threads|VmRSS|VmHWM)" /proc/1/status | tr -s "\t\n" "  "; printf "fds=%s " "$(ls /proc/1/fd 2>/dev/null | wc -l)"; nf=$(sed -n "s/^Max open files *\([0-9]*\) *\([0-9]*\).*/nofile=\1\/\2/p" /proc/1/limits); echo "${nf:-nofile=?}"' 2>/dev/null || echo "(exec alınmadı)"
done
if [ -n "$FIRSTAPP" ]; then
  echo "-- PID 1 komandası (replika 1):"; docker exec "$FIRSTAPP" sh -c 'tr "\0" " " </proc/1/cmdline; echo' 2>/dev/null
  echo "-- tutum mühit açarları (konteyner daxilində, sirr yoxdur):"
  docker exec "$FIRSTAPP" sh -c 'env | grep -E "^(ASGI_THREADS|MAX_INFLIGHT_REQUESTS|MAX_INFLIGHT_WAIT_SECONDS|DAPHNE_HTTP_TIMEOUT|DAPHNE_APPLICATION_CLOSE_TIMEOUT|DATABASE_CONN_MAX_AGE|RLS_TRANSACTION_SCOPED|CHANNEL_LAYER_CAPACITY|REQUEST_QUEUE_GLOBAL_UNSAFE_LIMIT|EXAM_START_GLOBAL_CONCURRENCY|HEALTH_CHECK_CACHE_SECONDS)=" | sort | tr "\n" " "; echo' 2>/dev/null
fi
echo '```'
WANT="$(dotenv APP_REPLICAS)"; echo "- ℹ️ app replikaları: işləyən **$APPN** · .env APP_REPLICAS=${WANT:-— (deploy skripti defoltu 8)}"
INF="$(dotenv MAX_INFLIGHT_REQUESTS)"; INF="${INF:-24}"; POOL="$(dotenv PGBOUNCER_DEFAULT_POOL_SIZE)"; POOL="${POOL:-150}"; RES="$(dotenv PGBOUNCER_RESERVE_POOL_SIZE)"; RES="${RES:-50}"
CW="$(dotenv CELERY_WORKER_CONCURRENCY)"; CW="${CW:-4}"; CH="$(dotenv CELERY_HEAVY_CONCURRENCY)"; CH="${CH:-2}"
CWN=$($COMPOSE ps -q celery_worker 2>/dev/null | wc -l | tr -d ' '); CHN=$($COMPOSE ps -q celery_worker_heavy 2>/dev/null | wc -l | tr -d ' ')
NEED=$(( APPN*INF + CWN*CW + CHN*CH + 1 ))
echo "- ℹ️ eyni-anlı DB bağlantı tələbatı (tavan): app ${APPN}×${INF} + celery ${CWN}×${CW} + heavy ${CHN}×${CH} + beat 1 = **${NEED}** · PgBouncer hovuzu ${POOL} + ${RES} rezerv = $((POOL+RES))"
[ "$NEED" -le $((POOL+RES)) ] && ok "tavan tələbat ${NEED} ≤ hovuz $((POOL+RES))" || warn "tavan tələbat ${NEED} > hovuz $((POOL+RES)) — doyma anında PgBouncer növbəsi (QUERY_WAIT_TIMEOUT) işə düşər"

echo
echo "### 10.6 Celery worker-ləri (pool, concurrency, prefetch, növbələr)"
echo '```'
for s in celery_worker celery_worker_heavy celery_beat; do
  for c in $($COMPOSE ps -q "$s" 2>/dev/null); do
    printf '%s: ' "$(docker inspect --format '{{.Name}}' "$c" 2>/dev/null | sed 's#^/##')"
    docker exec "$c" sh -c 'n=$(ls -d /proc/[0-9]* | wc -l); rss=$(awk "/VmRSS/{s+=\$2} END{print int(s/1024)}" /proc/[0-9]*/status 2>/dev/null); echo "proseslər=$n rss_cəmi=${rss}MB"' 2>/dev/null || echo "(exec alınmadı)"
  done
done
echo "-- celery inspect stats (pool; broker bloku qəsdən çap olunmur):"
$COMPOSE exec -T --index 1 celery_worker celery -A config inspect stats --timeout 10 2>/dev/null | grep -E '^-> |"implementation"|"max-concurrency"|"max-tasks-per-child"|"prefetch_count"' | sed 's/^ *//'
echo "-- celery inspect active_queues:"
$COMPOSE exec -T --index 1 celery_worker celery -A config inspect active_queues --timeout 10 2>/dev/null | grep -E "^-> |'name': '" | sed -E "s/^ *\* \{'name': '([^']+)'.*/   növbə: \1/" | head -12
echo '```'

echo
echo "### 10.7 PostgreSQL — pg_settings, bağlantılar, keş, checkpoint, temp fayllar, pg_stat_statements"
echo '```'
$COMPOSE exec -T postgres sh -c 'psql -q -X -U "$POSTGRES_USER" -d "$POSTGRES_DB" -AtF " | "' 2>&1 <<'SQL'
\echo -- versiya
SELECT version();
\echo -- əsas parametrlər (name | setting | unit)
SELECT name, setting, unit FROM pg_settings WHERE name IN ('shared_buffers','effective_cache_size','work_mem','maintenance_work_mem','max_connections','superuser_reserved_connections','max_wal_size','min_wal_size','checkpoint_completion_target','checkpoint_timeout','wal_buffers','random_page_cost','effective_io_concurrency','max_worker_processes','max_parallel_workers','max_parallel_workers_per_gather','autovacuum_max_workers','autovacuum_naptime','jit','huge_pages','temp_buffers','track_io_timing','log_min_duration_statement','log_lock_waits','idle_in_transaction_session_timeout','statement_timeout','shared_preload_libraries','data_checksums') ORDER BY name;
\echo -- bağlantılar: cəmi | aktiv | idle | idle-in-tx | max_connections | istifadə %
SELECT count(*), count(*) FILTER (WHERE state='active'), count(*) FILTER (WHERE state='idle'), count(*) FILTER (WHERE state LIKE 'idle in transaction%'), current_setting('max_connections')::int, round(100.0*count(*)/current_setting('max_connections')::int,1) FROM pg_stat_activity WHERE backend_type='client backend';
\echo -- bağlantılar rol / tətbiq / vəziyyət üzrə (usename | application_name | state | n)
SELECT usename, left(coalesce(application_name,''),30), state, count(*) FROM pg_stat_activity WHERE backend_type='client backend' GROUP BY 1,2,3 ORDER BY 4 DESC LIMIT 12;
\echo -- baza ölçüsü | keş hit % | commit | rollback | temp_files | temp_bytes | deadlocks | stats_reset  (temp_files çoxdursa work_mem azdır)
SELECT pg_size_pretty(pg_database_size(current_database())), round(100*blks_hit/nullif(blks_hit+blks_read,0),2), xact_commit, xact_rollback, temp_files, pg_size_pretty(temp_bytes), deadlocks, stats_reset::timestamp(0) FROM pg_stat_database WHERE datname=current_database();
\echo -- checkpoint-lər: timed | requested | write_s | sync_s | buffers_checkpoint | buffers_backend | stats_reset  (requested ≫ timed → max_wal_size azdır)
SELECT checkpoints_timed, checkpoints_req, round(checkpoint_write_time/1000), round(checkpoint_sync_time/1000), buffers_checkpoint, buffers_backend, stats_reset::timestamp(0) FROM pg_stat_bgwriter;
\echo -- ən böyük 6 cədvəl (ümumi ölçü, indekslər daxil | canlı sətir)
SELECT relname, pg_size_pretty(pg_total_relation_size(relid)), n_live_tup FROM pg_stat_user_tables ORDER BY pg_total_relation_size(relid) DESC LIMIT 6;
\echo -- heç istifadə olunmayan indekslər (idx_scan=0, unique deyil, >5 MB) — ilk 6
SELECT s.relname, s.indexrelname, pg_size_pretty(pg_relation_size(s.indexrelid)) FROM pg_stat_user_indexes s JOIN pg_index i ON i.indexrelid=s.indexrelid WHERE s.idx_scan=0 AND NOT i.indisunique AND pg_relation_size(s.indexrelid) > 5*1024*1024 ORDER BY pg_relation_size(s.indexrelid) DESC LIMIT 6;
\echo -- pg_stat_statements: ümumi vaxta görə ilk 10 (total_s | calls | mean_ms | rows | sorğu[80]) — mətn normallaşdırılmışdır ($1), parametr/PII yoxdur
SELECT round(total_exec_time/1000)::bigint, calls, round(mean_exec_time::numeric,1), rows, left(regexp_replace(query, '\s+', ' ', 'g'), 80) FROM pg_stat_statements WHERE dbid=(SELECT oid FROM pg_database WHERE datname=current_database()) AND query NOT ILIKE '%pg_stat_statements%' ORDER BY total_exec_time DESC LIMIT 10;
\echo -- pg_stat_statements statistikasının başlanğıcı
SELECT stats_reset::timestamp(0) FROM pg_stat_statements_info;
\echo -- isti cədvəllərin indeksləri (cədvəl | indeks | idx_scan | ölçü | unique) — PG16 fast-path kilid limiti 16-dır; çox indeks → LWLock:LockManager
SELECT s.relname, s.indexrelname, s.idx_scan, pg_size_pretty(pg_relation_size(s.indexrelid)), i.indisunique FROM pg_stat_user_indexes s JOIN pg_index i ON i.indexrelid=s.indexrelid WHERE s.relname IN ('registrar_studentacademicrecord','accounts_userprofile','exams_examattempt','exams_exam','organizations_membership','exams_examquestion','courses_course','auth_user','exams_examanswer') ORDER BY s.relname, s.idx_scan;
SQL
echo '```'

echo
echo "### 10.8 PgBouncer — konfiq (pgbouncer.ini, yalnız tutum açarları; canlı hovuz statistikası 10.11-də)"
echo '```'
$COMPOSE exec -T pgbouncer sh -c 'grep -hE "^(pool_mode|max_client_conn|default_pool_size|min_pool_size|reserve_pool_size|reserve_pool_timeout|max_db_connections|max_user_connections|server_idle_timeout|server_lifetime|query_wait_timeout|server_reset_query|max_prepared_statements|listen_backlog|so_reuseport|ignore_startup_parameters)[ =]" /etc/pgbouncer/pgbouncer.ini 2>/dev/null || echo "pgbouncer.ini oxunmadı"' 2>/dev/null
echo '```'

echo
echo "### 10.9 Redis — yaddaş, müştərilər, statistika, keyspace, AOF"
echo '```'
rc() { $COMPOSE exec -T redis redis-cli "$@" 2>/dev/null | tr -d '\r'; }
rc INFO memory | grep -E '^(used_memory_human|used_memory_rss_human|used_memory_peak_human|used_memory_dataset_perc|maxmemory_human|maxmemory_policy|mem_fragmentation_ratio|allocator_frag_ratio|total_system_memory_human)'
rc INFO clients | grep -E '^(connected_clients|blocked_clients|maxclients|clients_in_timeout_table)'
rc INFO stats | grep -E '^(total_connections_received|rejected_connections|evicted_keys|expired_keys|keyspace_hits|keyspace_misses|instantaneous_ops_per_sec|total_commands_processed)'
rc INFO persistence | grep -E '^(aof_enabled|aof_last_bgrewrite_status|aof_last_write_status|aof_current_size|rdb_last_bgsave_status|rdb_changes_since_last_save|loading)'
rc INFO keyspace | grep -E '^db'
printf 'io-threads=%s maxclients=%s hz=%s\n' "$(rc CONFIG GET io-threads | sed -n 2p)" "$(rc CONFIG GET maxclients | sed -n 2p)" "$(rc CONFIG GET hz | sed -n 2p)"
echo '```'
RU=$(rc INFO memory | awk -F: '/^used_memory:/{print $2}'); RM=$(rc INFO memory | awk -F: '/^maxmemory:/{print $2}')
if [ -n "$RU" ] && [ -n "$RM" ] && [ "$RM" -gt 0 ] 2>/dev/null; then RP=$((RU*100/RM)); RPF=$(awk -v u="$RU" -v m="$RM" 'BEGIN{printf "%.2f", 100*u/m}'); [ "$RP" -lt 70 ] && ok "redis yaddaşı maxmemory-nin ${RPF}%-i ($((RU/1048576)) MB / $((RM/1048576)) MB)" || warn "redis yaddaşı maxmemory-nin ${RPF}%-i (noeviction → limitdə yazma xətası)"; fi

echo
echo "### 10.10 nginx — worker-lər, bağlantı tavanı, gzip/http2/keepalive, stub_status"
echo '```'
$COMPOSE exec -T nginx nginx -T 2>/dev/null | grep -E '^\s*(worker_processes|worker_connections|worker_rlimit_nofile|multi_accept|use |keepalive_timeout|keepalive_requests|gzip on|gzip_comp_level|gzip_static|http2|sendfile|tcp_nopush|tcp_nodelay|client_max_body_size|proxy_buffering|proxy_buffers|proxy_buffer_size|limit_conn |limit_req_zone|resolver|open_file_cache)' | sed 's/^\s*//' | sort | uniq -c | sort -rn | awk '{c=$1; $1=""; printf "%s  (×%s)\n", substr($0,2), c}'
NGX=$($COMPOSE ps -q nginx 2>/dev/null | head -1)
echo "-- işləyən nginx worker prosesləri: $([ -n "$NGX" ] && docker top "$NGX" 2>/dev/null | grep -c 'worker process' || echo '?') · host nproc $(nproc)"
echo "-- nginx fayl deskriptoru limiti (worker_rlimit_nofile yoxdursa Docker defoltu; worker_connections bundan böyük olmamalıdır):"
[ -n "$NGX" ] && docker exec "$NGX" sh -c 'for p in 1 $(pgrep -f "worker process" 2>/dev/null | head -1); do printf "pid %s: " "$p"; grep "Max open files" /proc/$p/limits 2>/dev/null | tr -s " "; done' 2>/dev/null
echo "-- stub_status (Active = açıq müştəri bağlantıları, WS daxil):"; $COMPOSE exec -T nginx wget -qO- http://127.0.0.1:8081/stub_status 2>/dev/null
echo '```'

echo
echo "### 10.11 Prometheus — son 24 saat / 7 gün istifadə tarixçəsi (anlıq deyil) + Monitorinq səhifəsinin mənbə yoxlaması"
PROM_PORT="$(dotenv PROMETHEUS_PORT)"; PROM_PORT="${PROM_PORT:-9090}"; PROM="http://127.0.0.1:${PROM_PORT}"
AM_PORT="$(dotenv ALERTMANAGER_PORT)"; AM_PORT="${AM_PORT:-9093}"
# promq "<PromQL>" [printf-format] → tək seriya: dəyər; çox seriya: "etiketlər = dəyər" sətirləri; boş: —; xəta: n/a
promq() {
  local out fmt="${2:-%.1f}"
  out=$(curl -sG --max-time 25 "$PROM/api/v1/query" --data-urlencode "query=$1" 2>/dev/null) || { echo "n/a"; return; }
  if command -v python3 >/dev/null 2>&1; then
    # DİQQƏT: aşağıdakı Python mətni bash tək dırnaq içindədir — içində TƏK DIRNAQ OLMAMALIDIR.
    printf '%s' "$out" | python3 -c '
import json, sys
fmt = sys.argv[1]
try:
    res = json.load(sys.stdin).get("data", {}).get("result", [])
except Exception:
    print("n/a"); sys.exit()
if not res:
    print("—"); sys.exit()
def f(v):
    try:
        return fmt % float(v)
    except Exception:
        return str(v)
if len(res) == 1:
    print(f(res[0]["value"][1])); sys.exit()
for r in res:
    lbl = ",".join(k + "=" + str(v) for k, v in sorted(r.get("metric", {}).items()) if k != "__name__")
    print((lbl if lbl else "*") + " = " + f(r["value"][1]))
' "$fmt"
  else
    printf '%s' "$out" | sed -n 's/.*"value":\[[0-9.e+]*,"\([^"]*\)"\].*/\1/p' | head -1
  fi
}
if curl -s --max-time 5 "$PROM/-/ready" >/dev/null 2>&1; then
  CRE='name=~"emsarena-.+|educationmanagementstudentarena-.+"'
  echo '```'
  echo "CPU: 24s orta $(promq '100*(1-avg(rate(node_cpu_seconds_total{mode="idle"}[24h])))')% · 7g maks (5 dəq) $(promq 'max_over_time((100*(1-avg(rate(node_cpu_seconds_total{mode="idle"}[5m]))))[7d:5m])')% · steal 24s $(promq '100*avg(rate(node_cpu_seconds_total{mode="steal"}[24h]))' '%.2f')% · iowait 24s $(promq '100*avg(rate(node_cpu_seconds_total{mode="iowait"}[24h]))' '%.2f')%"
  echo "RAM: indi $(promq '100*(1-node_memory_MemAvailable_bytes/node_memory_MemTotal_bytes)')% · 7g maks $(promq 'max_over_time((100*(1-node_memory_MemAvailable_bytes/node_memory_MemTotal_bytes))[7d:5m])')% · swap 7g maks $(promq 'max_over_time((node_memory_SwapTotal_bytes-node_memory_SwapFree_bytes)[7d:5m])/1048576' '%.0f') MB"
  echo "load1: 7g maks $(promq 'max_over_time(node_load1[7d:1m])' '%.2f') (nüvə: $(nproc)) · disk I/O məşğulluğu 24s orta $(promq '100*avg(rate(node_disk_io_time_seconds_total{device!~"loop.*|dm-.*"}[24h]))')% · 7g maks $(promq 'max_over_time((100*avg(rate(node_disk_io_time_seconds_total{device!~"loop.*|dm-.*"}[5m])))[7d:5m])')%"
  echo "HTTP: 24s orta $(promq 'sum(rate(http_requests_total[24h]))' '%.2f') r/s · 7g maks (5 dəq) $(promq 'max_over_time(sum(rate(http_requests_total[5m]))[7d:5m])' '%.1f') r/s · 7g cəmi $(promq 'sum(increase(http_requests_total[7d]))' '%.0f') sorğu"
  echo "Gecikmə p95: 24s $(promq 'histogram_quantile(0.95, sum by (le)(rate(http_request_duration_seconds_bucket[24h])))*1000' '%.0f') ms · 7g maks (1 saat pəncərə) $(promq 'max_over_time((histogram_quantile(0.95, sum by (le)(rate(http_request_duration_seconds_bucket[1h]))))[7d:1h])*1000' '%.0f') ms"
  echo "Xətalar 7g: 5xx $(promq 'sum(increase(http_requests_total{status_code=~"5.."}[7d])) or vector(0)' '%.0f') · 503 (inflight shed) $(promq 'sum(increase(http_requests_total{status_code="503"}[7d])) or vector(0)' '%.0f') · 429 $(promq 'sum(increase(http_requests_total{status_code="429"}[7d])) or vector(0)' '%.0f')"
  echo "PostgreSQL bağlantı: indi $(promq 'sum(pg_stat_activity_count)' '%.0f') · 7g maks $(promq 'max_over_time(sum(pg_stat_activity_count)[7d:1m])' '%.0f') · max_connections (exporter) $(promq 'pg_settings_max_connections' '%.0f')"
  echo "PgBouncer: server aktiv indi $(promq 'sum(pgbouncer_pools_server_active_connections)' '%.0f') · 7g maks $(promq 'max_over_time(sum(pgbouncer_pools_server_active_connections)[7d:1m])' '%.0f') · müştəri aktiv 7g maks $(promq 'max_over_time(sum(pgbouncer_pools_client_active_connections)[7d:1m])' '%.0f') · gözləyən 7g maks $(promq 'max_over_time(sum(pgbouncer_pools_client_waiting_connections)[7d:1m])' '%.0f') · maxwait 7g $(promq 'max_over_time(max(pgbouncer_pools_client_maxwait_seconds)[7d:1m])' '%.1f') s"
  echo "Redis: yaddaş indi $(promq 'redis_memory_used_bytes/1048576' '%.0f') MB · 7g maks $(promq 'max_over_time(redis_memory_used_bytes[7d:5m])/1048576' '%.0f') MB · maxmemory $(promq 'redis_memory_max_bytes/1048576' '%.0f') MB · müştəri indi $(promq 'redis_connected_clients' '%.0f') · 7g maks $(promq 'max_over_time(redis_connected_clients[7d:1m])' '%.0f') · 24s orta $(promq 'rate(redis_commands_processed_total[24h])' '%.0f') əmr/s"
  # emsarena_celery_* / emsarena_backup_* gauge-ları HƏR app replikası eyni keşdən verir (collectors.py) →
  # replika başına seriya; max() ilə yığılır (köhnə replika IP-ləri 7g pəncərədə qalır).
  echo "Celery: onlayn worker $(promq 'max(emsarena_celery_workers_online)' '%.0f') · növbə 7g maks $(promq 'max_over_time(sum(emsarena_celery_queue_length)[7d:1m])' '%.0f') · aktiv task 7g maks $(promq 'max(max_over_time(emsarena_celery_active_tasks[7d:1m]))' '%.0f') · backup yaşı $(promq 'max(emsarena_backup_age_seconds)/3600' '%.1f') saat"
  echo "Prometheus TSDB: $(promq 'prometheus_tsdb_storage_blocks_bytes/1048576' '%.0f') MB · seriya $(promq 'prometheus_tsdb_head_series' '%.0f') · retention $(v=$(dotenv PROMETHEUS_RETENTION_TIME); echo "${v:-15d (defolt)}")"
  echo
  echo "-- konteyner CPU, 7 gün maks (5 dəq pəncərə, 10 dəq addım; % bir nüvə — 100 = tam bir nüvə):"
  promq "topk(14, max_over_time((sum by (name)(rate(container_cpu_usage_seconds_total{$CRE}[5m])))[7d:10m])*100)" '%.1f'
  echo "-- konteyner yaddaşı (working set) 7 gün maks, öz limitinin %-i:"
  promq "topk(14, 100*max_over_time((sum by (name)(container_memory_working_set_bytes{$CRE}))[7d:10m]) / on(name) (sum by (name)(container_spec_memory_limit_bytes{$CRE}) > 0))" '%.1f'
  echo '```'
  echo "#### Monitorinq səhifəsinin (apps/monitoring) məlumat mənbələri"
  TG=$(curl -s --max-time 10 "$PROM/api/v1/targets?state=active" 2>/dev/null)
  NUP=$(printf '%s' "$TG" | grep -o '"health":"up"' | wc -l | tr -d ' '); NALL=$(printf '%s' "$TG" | grep -o '"health":"' | wc -l | tr -d ' ')
  if [ "${NALL:-0}" -gt 0 ]; then
    [ "$NUP" = "$NALL" ] && ok "Prometheus scrape hədəfləri: $NUP/$NALL up" || { warn "Prometheus scrape hədəfləri: $NUP/$NALL up"; echo '```'; printf '%s' "$TG" | grep -o '"scrapeUrl":"[^"]*"\|"health":"[a-z]*"\|"lastError":"[^"]*"' | paste - - - | grep -v '"health":"up"' | cut -c1-200 | head -10; echo '```'; }
  else
    warn "Prometheus /api/v1/targets oxunmadı"
  fi
  APPT=$(promq 'count(up{job="emsarena-app"})' '%.0f'); [ "$APPT" = "$APPN" ] && ok "emsarena-app scrape hədəfi $APPT = işləyən app replikası $APPN" || warn "emsarena-app scrape hədəfi $APPT ≠ işləyən app replikası $APPN (dns_sd; köhnə IP və ya replika itirilib)"
  CADN=$(promq "count(count by (name)(container_last_seen{$CRE}))" '%.0f'); RUNN=$($COMPOSE ps -q 2>/dev/null | wc -l | tr -d ' ')
  case "$CADN" in ''|*[!0-9]*) warn "cAdvisor container_last_seen seriyası yoxdur — «Konteynerlər» tabı boş qalır";; *) [ "$CADN" -ge "$RUNN" ] && ok "cAdvisor $CADN konteyner görür (compose-da $RUNN işləyir)" || warn "cAdvisor yalnız $CADN konteyner görür, compose-da $RUNN işləyir";; esac
  PGMAX=$(promq 'pg_settings_max_connections' '%.0f'); case "$PGMAX" in ''|—|n/a) warn "postgres_exporter pg_settings_max_connections vermir — səhifədə max_connections «—» görünür";; *) ok "pg_settings_max_connections=$PGMAX (exporter)";; esac
  BK=$(promq 'max(emsarena_backup_age_seconds)' '%.0f'); case "$BK" in ''|*[!0-9]*) warn "emsarena_backup_age_seconds yoxdur — səhifədə backup yaşı bilinmir (beat kollektoru işləməyib?)";; *) ok "backup yaşı metriki var ($((BK/3600)) saat)";; esac
  CWO=$(promq 'max(emsarena_celery_workers_online)' '%.0f'); case "$CWO" in ''|*[!0-9]*) warn "emsarena_celery_workers_online yoxdur — Celery paneli boşdur";; *) ok "Celery statistikası Prometheus-da var (onlayn worker: $CWO)";; esac
  # «Server» tabının rəqəmləri host ilə üst-üstə düşürmü? (node_exporter: pid host + rootfs=/host, amma bridge şəbəkə)
  PCORES=$(promq 'count(count(node_cpu_seconds_total) by (cpu))' '%.0f'); [ "$PCORES" = "$(nproc)" ] && ok "node_exporter nüvə sayı $PCORES = nproc $(nproc)" || warn "node_exporter nüvə sayı $PCORES ≠ nproc $(nproc)"
  PDISK=$(promq '100*(1-node_filesystem_avail_bytes{mountpoint="/",fstype!~"tmpfs|overlay"}/node_filesystem_size_bytes{mountpoint="/",fstype!~"tmpfs|overlay"})' '%.0f'); DFP=$(df --output=pcent / | tail -1 | tr -dc '0-9')
  case "$PDISK" in ''|*[!0-9]*) warn "node_exporter kök disk seriyası yoxdur (mountpoint=\"/\") — səhifədə disk % boşdur";; *) [ $(( PDISK > DFP ? PDISK - DFP : DFP - PDISK )) -le 2 ] && ok "node_exporter disk ${PDISK}% ≈ df ${DFP}%" || warn "node_exporter disk ${PDISK}% ≠ df ${DFP}% (mountpoint/fstype seçicisi)";; esac
  NETALL=$(promq 'count by (device)(node_network_receive_bytes_total)' '%.0f' | sed -n 's/^device=\([^ ,]*\).*/\1/p' | tr '\n' ' ')
  NETDEV=$(promq 'count by (device)(node_network_receive_bytes_total{device!~"lo|veth.*|br.*"})' '%.0f' | sed -n 's/^device=\([^ ,]*\).*/\1/p' | tr '\n' ' ')
  echo "- ℹ️ node_exporter şəbəkə cihazları (hamısı): ${NETALL:-—}"
  HOSTNICS=""; for d in /sys/class/net/*; do d=${d##*/}; case "$d" in lo|veth*|br-*|docker*|'*') ;; *) HOSTNICS="$HOSTNICS$d ";; esac; done
  match=0; for d in $HOSTNICS; do case " $NETDEV " in *" $d "*) match=1;; esac; done
  [ "$match" = 1 ] && ok "node_exporter host NIC-lərini görür (exporter: ${NETDEV:-—}; host: ${HOSTNICS:-—})" || warn "node_exporter host şəbəkə ad-məkanında DEYİL (exporter cihazları: ${NETDEV:-—}; host NIC: ${HOSTNICS:-—}) — Server tabındakı şəbəkə RX/TX qrafiki host NIC-i deyil, exporter konteynerinin öz trafikini göstərir (compose: node_exporter üçün network_mode: host lazımdır)"
  AL=$(curl -s --max-time 10 "http://127.0.0.1:${AM_PORT}/api/v2/alerts?active=true&silenced=false&inhibited=false" 2>/dev/null | grep -o '"alertname":"[^"]*"' | sed 's/"alertname":"//; s/"$//' | sort | uniq -c | awk '{printf "%s×%s ", $2, $1}')
  NONWD=$(printf '%s' "$AL" | tr ' ' '\n' | grep -vc '^Watchdog×\|^$')
  [ "${NONWD:-0}" -eq 0 ] && ok "Alertmanager aktiv alert: ${AL:-yoxdur} (Watchdog gözləniləndir)" || warn "Alertmanager aktiv alertlər: ${AL}"
else
  warn "Prometheus ${PROM} əlçatmaz — tarixçə ölçülmədi, Monitorinq səhifəsi də degraded göstərər"
fi

section "Yekun"
echo "- ❌ kritik: **$FAIL** · ⚠️ xəbərdarlıq: **$WARN**"
exit 0
