#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/emsarena/app}"
VENV_DIR="${VENV_DIR:-/opt/emsarena/venv}"
SERVICE_NAME="${SERVICE_NAME:-emsarena.service}"

# Docker Compose reads .env itself, but this deploy script also owns DNS/TLS
# preflights. Read only explicitly requested, non-secret keys instead of
# sourcing the whole file as shell code.
dotenv_value() {
  local key="$1"
  local value=""
  [ -f "${APP_DIR}/.env" ] || return 0
  value="$(awk -v wanted="${key}" '
    index($0, wanted "=") == 1 { value = substr($0, length(wanted) + 2) }
    END { print value }
  ' "${APP_DIR}/.env")"
  value="${value%$'\r'}"
  if [[ "$value" == \"*\" && "$value" == *\" ]]; then
    value="${value:1:${#value}-2}"
  elif [[ "$value" == \'*\' && "$value" == *\' ]]; then
    value="${value:1:${#value}-2}"
  fi
  printf '%s' "$value"
}

DEPLOY_MODE="${DEPLOY_MODE:-$(dotenv_value DEPLOY_MODE)}"
DEPLOY_MODE="${DEPLOY_MODE:-docker}"
if [ -z "${APP_BASE_URL:-}" ]; then
  APP_BASE_URL="$(dotenv_value APP_BASE_URL)"
fi
if [ -z "${APP_BASE_URL:-}" ]; then
  if [ "$DEPLOY_MODE" = "docker" ]; then
    APP_BASE_URL="https://127.0.0.1"
  else
    APP_BASE_URL="http://127.0.0.1"
  fi
fi
HEALTHCHECK_HOST="${HEALTHCHECK_HOST:-$(dotenv_value HEALTHCHECK_HOST)}"
HEALTHCHECK_HOST="${HEALTHCHECK_HOST:-127.0.0.1}"
ORIGIN_HEALTHCHECK_INSECURE_TLS="${ORIGIN_HEALTHCHECK_INSECURE_TLS:-$(dotenv_value ORIGIN_HEALTHCHECK_INSECURE_TLS)}"
ORIGIN_HEALTHCHECK_INSECURE_TLS="${ORIGIN_HEALTHCHECK_INSECURE_TLS:-true}"
EDGE_PROXY_MODE="${EDGE_PROXY_MODE:-$(dotenv_value EDGE_PROXY_MODE)}"
EDGE_PROXY_MODE="${EDGE_PROXY_MODE:-direct}"
DIRECT_ORIGIN_IPS="${DIRECT_ORIGIN_IPS:-$(dotenv_value DIRECT_ORIGIN_IPS)}"
TLS_CERT_MIN_VALIDITY_SECONDS="${TLS_CERT_MIN_VALIDITY_SECONDS:-$(dotenv_value TLS_CERT_MIN_VALIDITY_SECONDS)}"
TLS_CERT_MIN_VALIDITY_SECONDS="${TLS_CERT_MIN_VALIDITY_SECONDS:-604800}"
TLS_ALLOW_SELF_SIGNED_LOCAL="${TLS_ALLOW_SELF_SIGNED_LOCAL:-$(dotenv_value TLS_ALLOW_SELF_SIGNED_LOCAL)}"
TLS_ALLOW_SELF_SIGNED_LOCAL="${TLS_ALLOW_SELF_SIGNED_LOCAL:-false}"
PING_PATH="${PING_PATH:-/ping/}"
HEALTH_PATH="${HEALTH_PATH:-/health/}"
DISABLE_LEGACY_DAPHNE_SERVICE="${DISABLE_LEGACY_DAPHNE_SERVICE:-true}"
DEPLOY_TIMEOUT_SECONDS="${DEPLOY_TIMEOUT_SECONDS:-300}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
NGINX_CONFIG_FILE="${NGINX_CONFIG_FILE:-${APP_DIR}/docker/nginx/nginx.conf}"
APP_REPLICAS="${APP_REPLICAS:-$(dotenv_value APP_REPLICAS)}"
APP_REPLICAS="${APP_REPLICAS:-8}"
CELERY_REPLICAS="${CELERY_REPLICAS:-$(dotenv_value CELERY_REPLICAS)}"
CELERY_REPLICAS="${CELERY_REPLICAS:-2}"
# P1-08 (Codex audit, 2026-09-13): image daxilində `manage.py check --deploy`
# preflight-ının səviyyəsi. WARNING → xəbərdarlıq (security.W004/W008/W012/
# W016 …) da deploy-u dayandırır; ERROR → yalnız xəta dayandırır, xəbərdarlıqlar
# ucadan çap olunur. 2026-09-14 infra auditi P3-16: defolt WARNING-ə çəkildi —
# CI (_security.yml) eyni yoxlamanı `--fail-level WARNING` ilə bloklayır, prod
# host isə ERROR ilə keçirdi (yəni CI-də qırmızı olan konfiq prod-da keçirdi).
# Müvəqqəti yumşaltma: .env və ya mühitdə DEPLOY_CHECK_FAIL_LEVEL=ERROR.
DEPLOY_CHECK_FAIL_LEVEL="${DEPLOY_CHECK_FAIL_LEVEL:-$(dotenv_value DEPLOY_CHECK_FAIL_LEVEL)}"
DEPLOY_CHECK_FAIL_LEVEL="${DEPLOY_CHECK_FAIL_LEVEL:-WARNING}"
# 2026-09-14 infra auditi P2-5: deploy-öncəsi DB dump (SKIP_PREDEPLOY_BACKUP=1
# ilə keçilə bilər), uğursuz health-gate-də əvvəlki image-ə avtomatik geri
# qayıtma (DEPLOY_ROLLBACK_ON_FAILURE=false ilə söndürülə bilər) və saxlanılan
# köhnə release teqlərinin sayı (rollback üçün ən azı 1 lazımdır).
SKIP_PREDEPLOY_BACKUP="${SKIP_PREDEPLOY_BACKUP:-$(dotenv_value SKIP_PREDEPLOY_BACKUP)}"
SKIP_PREDEPLOY_BACKUP="${SKIP_PREDEPLOY_BACKUP:-0}"
DEPLOY_ROLLBACK_ON_FAILURE="${DEPLOY_ROLLBACK_ON_FAILURE:-$(dotenv_value DEPLOY_ROLLBACK_ON_FAILURE)}"
DEPLOY_ROLLBACK_ON_FAILURE="${DEPLOY_ROLLBACK_ON_FAILURE:-true}"
DEPLOY_KEEP_RELEASE_IMAGES="${DEPLOY_KEEP_RELEASE_IMAGES:-$(dotenv_value DEPLOY_KEEP_RELEASE_IMAGES)}"
DEPLOY_KEEP_RELEASE_IMAGES="${DEPLOY_KEEP_RELEASE_IMAGES:-3}"
APP_IMAGE_REPOSITORY="${APP_IMAGE_REPOSITORY:-emsarena-prod}"

# Per-run, user-writable temp files. Fixed /tmp/emsarena-* paths collided with
# files owned by a different user (e.g. a previous root deploy) and failed with
# "Permission denied" when the CI runner (github-runner) re-ran the deploy.
DEPLOY_TMP="$(mktemp -d 2>/dev/null || mktemp -d -t emsarena-deploy)"
trap 'rm -rf "$DEPLOY_TMP"' EXIT
PING_JSON="${DEPLOY_TMP}/ping.json"
HEALTH_JSON="${DEPLOY_TMP}/health.json"
COMPOSE_CONFIG="${DEPLOY_TMP}/compose-config.yml"

if ! [[ "$APP_REPLICAS" =~ ^[0-9]+$ ]] || [ "$APP_REPLICAS" -lt 1 ]; then
  echo "APP_REPLICAS must be a positive integer." >&2
  exit 1
fi

if ! [[ "$CELERY_REPLICAS" =~ ^[0-9]+$ ]] || [ "$CELERY_REPLICAS" -lt 0 ]; then
  echo "CELERY_REPLICAS must be zero or a positive integer." >&2
  exit 1
fi

# "direct": publik domen birbaşa bu serverə baxır (DNS+publik-CA TLS preflight).
# "lan": müəssisədaxili yerləşdirmə — publik DNS yoxdur, host özəl IP-dir,
#        self-signed sertifikata TLS_ALLOW_SELF_SIGNED_LOCAL=true ilə icazə.
# Proxy/CDN rejimləri dəstəklənmir (real müştəri IP-ləri itir).
if [ "$EDGE_PROXY_MODE" != "direct" ] && [ "$EDGE_PROXY_MODE" != "lan" ]; then
  echo "EDGE_PROXY_MODE must be 'direct' or 'lan'; proxy/CDN modes are not supported by this deployment." >&2
  exit 1
fi

case "$DEPLOY_CHECK_FAIL_LEVEL" in
  DEBUG|INFO|WARNING|ERROR|CRITICAL) ;;
  *)
    echo "DEPLOY_CHECK_FAIL_LEVEL must be one of DEBUG, INFO, WARNING, ERROR, CRITICAL." >&2
    exit 1
    ;;
esac

if ! [[ "$DEPLOY_KEEP_RELEASE_IMAGES" =~ ^[0-9]+$ ]] || [ "$DEPLOY_KEEP_RELEASE_IMAGES" -lt 1 ]; then
  echo "DEPLOY_KEEP_RELEASE_IMAGES must be a positive integer (the previous release tag is needed for rollback)." >&2
  exit 1
fi

if ! [[ "$TLS_CERT_MIN_VALIDITY_SECONDS" =~ ^[0-9]+$ ]] || [ "$TLS_CERT_MIN_VALIDITY_SECONDS" -lt 3600 ]; then
  echo "TLS_CERT_MIN_VALIDITY_SECONDS must be an integer of at least 3600." >&2
  exit 1
fi

if [ "$TLS_ALLOW_SELF_SIGNED_LOCAL" != "true" ] && [ "$TLS_ALLOW_SELF_SIGNED_LOCAL" != "false" ]; then
  echo "TLS_ALLOW_SELF_SIGNED_LOCAL must be 'true' or 'false'." >&2
  exit 1
fi

if [ "$(id -u)" -eq 0 ]; then
  SUDO=""
else
  SUDO="sudo"
fi

cd "$APP_DIR"

if [ ! -f "${APP_DIR}/.env" ]; then
  echo "Missing ${APP_DIR}/.env. Create it once on the server before enabling CD." >&2
  exit 1
fi

curl_headers=(
  -H "Host: ${HEALTHCHECK_HOST}"
)
curl_options=(-sS)
if [ "$ORIGIN_HEALTHCHECK_INSECURE_TLS" = "true" ]; then
  case "$APP_BASE_URL" in
    https://127.0.0.1*|https://localhost*|https://\[::1\]*)
      # Origin/self-signed certificates are not public trust anchors.  TLS
      # verification is disabled only for the loopback deployment probe.
      curl_options+=(--insecure)
      ;;
    *)
      echo "ORIGIN_HEALTHCHECK_INSECURE_TLS=true is allowed only for a loopback APP_BASE_URL." >&2
      exit 1
      ;;
  esac
fi

wait_for_http() {
  local url="$1"
  local expected_codes="$2"
  local body_file="$3"
  local max_attempts=$((DEPLOY_TIMEOUT_SECONDS / 5))
  local attempt=1
  local status

  if [ "$max_attempts" -lt 1 ]; then
    max_attempts=1
  fi

  while true; do
    status="$(curl "${curl_options[@]}" -o "$body_file" -w '%{http_code}' "${curl_headers[@]}" "$url" || true)"
    if [[ " ${expected_codes} " == *" ${status} "* ]]; then
      return 0
    fi

    if [ "$attempt" -ge "$max_attempts" ]; then
      echo "Endpoint ${url} did not become ready within ${DEPLOY_TIMEOUT_SECONDS}s." >&2
      echo "Last status: ${status}" >&2
      cat "$body_file" >&2 || true
      return 1
    fi

    echo "Waiting for ${url} (${attempt}/${max_attempts})... HTTP ${status}"
    sleep 5
    attempt=$((attempt + 1))
  done
}

refresh_nginx_upstream() {
  local host_config_hash=""
  local container_config_hash=""

  # nginx.conf single-file bind mount-dur. Deploy rsync atomic rename etdikdə
  # işləyən container köhnə (deleted) inode-a bağlı qala bilər; bu halda
  # `nginx -s reload` də köhnə konfiqi yenidən oxuyur. Host/container hash
  # fərqi bunu aşkarlayır və yalnız nginx-i yeni mount ilə recreate edir.
  if [ -f "$NGINX_CONFIG_FILE" ]; then
    host_config_hash="$(sha256sum "$NGINX_CONFIG_FILE" | awk '{print $1}')"
    container_config_hash="$(
      docker compose -f "$COMPOSE_FILE" exec -T nginx \
        sha256sum /etc/nginx/conf.d/default.conf 2>/dev/null | awk '{print $1}' || true
    )"
  fi

  if [ -n "$host_config_hash" ] &&
    [ -n "$container_config_hash" ] &&
    [ "$host_config_hash" != "$container_config_hash" ]; then
    echo "nginx bind mount is stale; validating the synced config before recreate..."
    docker compose -f "$COMPOSE_FILE" run --rm --no-deps nginx nginx -t
    docker compose -f "$COMPOSE_FILE" up -d --no-deps --force-recreate nginx
    return 0
  fi

  # Docker Compose can recreate the app container without recreating nginx.
  # nginx resolves upstream names at config load time, so a deploy can leave it
  # proxying to the old app container IP until the proxy is reloaded.
  echo "Refreshing nginx upstream DNS for the current app container..."
  if docker compose -f "$COMPOSE_FILE" exec -T nginx nginx -s reload; then
    return 0
  fi

  echo "nginx reload failed; recreating nginx without touching dependencies." >&2
  docker compose -f "$COMPOSE_FILE" up -d --no-deps --force-recreate nginx
}

reload_prometheus_config() {
  # prometheus.yml / alerts.yml are bind-mounted read-only. `docker compose up -d`
  # does NOT recreate the container when only the mounted file *content* changed,
  # so without this step a deploy leaves Prometheus serving its old in-memory
  # config (new scrape jobs / alert rules never take effect). SIGHUP makes it
  # re-read the config; the directory mount (see docker-compose.prod.yml) ensures
  # it sees the freshly-synced files. Fall back to a recreate if the reload fails.
  echo "Reloading Prometheus configuration..."
  if docker compose -f "$COMPOSE_FILE" exec -T prometheus kill -HUP 1 2>/dev/null; then
    return 0
  fi
  echo "Prometheus SIGHUP reload failed; recreating prometheus." >&2
  docker compose -f "$COMPOSE_FILE" up -d --no-deps --force-recreate prometheus
}

recreate_alertmanager() {
  # alertmanager.tmpl.yml is rendered by docker/render-template.sh in the
  # container ENTRYPOINT into /tmp/alertmanager.yml, so neither a bind-mount
  # content change nor SIGHUP
  # picks up a new template — only a recreate re-runs the render. Without this
  # a deploy that changes the webhook contract (2026-09-12: token moved from
  # `?token=` to the `Authorization: Bearer` header) would leave Alertmanager
  # posting the old form and every notification would 403 silently.
  echo "Recreating alertmanager (config template is rendered at container start)..."
  docker compose -f "$COMPOSE_FILE" up -d --no-deps --force-recreate alertmanager \
    || echo "Alertmanager recreate failed; incident webhook may be stale." >&2
}

legacy_deploy() {
  if [ ! -x "${VENV_DIR}/bin/python" ]; then
    echo "Missing virtualenv at ${VENV_DIR}." >&2
    exit 1
  fi

  if [ "$DISABLE_LEGACY_DAPHNE_SERVICE" = "true" ] && [ "$SERVICE_NAME" != "daphne.service" ]; then
    if systemctl list-unit-files | grep -q '^daphne\.service'; then
      $SUDO systemctl disable --now daphne.service || true
    fi
  fi

  DJANGO_SETTINGS_MODULE=config.settings.production "${VENV_DIR}/bin/pip" install -r requirements/production.txt
  DJANGO_SETTINGS_MODULE=config.settings.production "${VENV_DIR}/bin/python" manage.py migrate --noinput
  DJANGO_SETTINGS_MODULE=config.settings.production "${VENV_DIR}/bin/python" manage.py collectstatic --noinput

  $SUDO systemctl restart "$SERVICE_NAME"
  $SUDO systemctl is-active --quiet "$SERVICE_NAME"

  wait_for_http "${APP_BASE_URL}${PING_PATH}" "200" "$PING_JSON" || {
    $SUDO systemctl status "$SERVICE_NAME" --no-pager || true
    journalctl -u "$SERVICE_NAME" -n 200 --no-pager || true
    exit 1
  }

  wait_for_http "${APP_BASE_URL}${HEALTH_PATH}" "200 207" "$HEALTH_JSON" || {
    $SUDO systemctl status "$SERVICE_NAME" --no-pager || true
    journalctl -u "$SERVICE_NAME" -n 200 --no-pager || true
    exit 1
  }

  $SUDO systemctl status "$SERVICE_NAME" --no-pager | sed -n '1,20p'
}

preflight_direct_dns() {
  if [ -z "$DIRECT_ORIGIN_IPS" ]; then
    echo "DIRECT_ORIGIN_IPS is required for a direct-edge deployment." >&2
    exit 1
  fi
  if ! command -v python3 >/dev/null 2>&1; then
    echo "python3 is required for the direct-edge DNS preflight." >&2
    exit 1
  fi

  python3 - "$HEALTHCHECK_HOST" "$DIRECT_ORIGIN_IPS" <<'PY'
import ipaddress
import socket
import sys

hostname, raw_expected = sys.argv[1:]
try:
    expected = {ipaddress.ip_address(token) for token in raw_expected.replace(",", " ").split()}
except ValueError as exc:
    raise SystemExit(f"DIRECT_ORIGIN_IPS contains an invalid address: {exc}") from exc

if not expected:
    raise SystemExit("DIRECT_ORIGIN_IPS must contain at least one public address.")
if any(not address.is_global for address in expected):
    raise SystemExit("DIRECT_ORIGIN_IPS may contain only globally routable public addresses.")

try:
    answers = socket.getaddrinfo(hostname, 443, type=socket.SOCK_STREAM)
except socket.gaierror as exc:
    raise SystemExit(f"Public DNS lookup failed for {hostname}: {exc}") from exc

resolved = {ipaddress.ip_address(answer[4][0]) for answer in answers}
if resolved != expected:
    expected_text = ", ".join(sorted(map(str, expected)))
    resolved_text = ", ".join(sorted(map(str, resolved))) or "<none>"
    raise SystemExit(
        f"Direct-edge DNS mismatch for {hostname}: expected [{expected_text}], resolved [{resolved_text}]."
    )

print(f"Direct-edge DNS preflight passed for {hostname} ({', '.join(sorted(map(str, resolved)))})")
PY
}

validate_origin_cert() {
  local cert_dir="${APP_DIR}/docker/nginx/certs"
  local cert_file="${cert_dir}/origin.crt"
  local key_file="${cert_dir}/origin.key"

  if [ ! -s "$cert_file" ] || [ ! -s "$key_file" ]; then
    echo "Missing direct-edge TLS certificate/key: ${cert_file}, ${key_file}." >&2
    echo "Provision a public-CA full chain and private key before deploying; no self-signed certificate is generated." >&2
    exit 1
  fi
  bash "${APP_DIR}/scripts/deploy/validate_direct_tls.sh" \
    "$cert_file" \
    "$key_file" \
    "$HEALTHCHECK_HOST" \
    "$TLS_CERT_MIN_VALIDITY_SECONDS" \
    "$TLS_ALLOW_SELF_SIGNED_LOCAL" \
    "" \
    "$EDGE_PROXY_MODE"
}

remove_edge_firewall_family() {
  local tool="$1"
  local chain="$2"
  local iface="$3"
  local port

  command -v "$tool" >/dev/null 2>&1 || return 0
  $SUDO "$tool" -S DOCKER-USER >/dev/null 2>&1 || return 0
  for port in 80 443; do
    while $SUDO "$tool" -C DOCKER-USER -i "$iface" -p tcp -m conntrack --ctstate NEW --ctorigdstport "$port" -j "$chain" 2>/dev/null; do
      $SUDO "$tool" -D DOCKER-USER -i "$iface" -p tcp -m conntrack --ctstate NEW --ctorigdstport "$port" -j "$chain"
    done
    # Remove the historical jump that did not include --ctstate.
    while $SUDO "$tool" -C DOCKER-USER -i "$iface" -p tcp -m conntrack --ctorigdstport "$port" -j "$chain" 2>/dev/null; do
      $SUDO "$tool" -D DOCKER-USER -i "$iface" -p tcp -m conntrack --ctorigdstport "$port" -j "$chain"
    done
  done
  if $SUDO "$tool" -S "$chain" >/dev/null 2>&1; then
    $SUDO "$tool" -F "$chain"
    $SUDO "$tool" -X "$chain"
  fi
}

remove_legacy_edge_firewall() {
  local iface
  iface="$(ip -4 route show default 2>/dev/null | awk '{print $5; exit}')"
  if [ -z "$iface" ]; then
    echo "Unable to determine the public network interface." >&2
    exit 1
  fi

  # One-time cleanup for hosts upgraded from the retired proxy deployment.
  remove_edge_firewall_family iptables EMSARENA-CF-WEB "$iface"
  remove_edge_firewall_family ip6tables EMSARENA-CF-WEB6 "$iface"
}

app_replicas_ready() {
  local ids=()
  local id
  local status
  local total=0
  local ready=0
  local summary=""

  mapfile -t ids < <(docker compose -f "$COMPOSE_FILE" ps -q app)

  for id in "${ids[@]}"; do
    [ -n "$id" ] || continue
    status="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$id" 2>/dev/null || true)"
    total=$((total + 1))
    summary="${summary}${id:0:12}:${status:-unknown} "
    if [ "$status" = "healthy" ] || [ "$status" = "running" ]; then
      ready=$((ready + 1))
    fi
  done

  APP_HEALTH_SUMMARY="${ready}/${total} app replica(s) ready (${summary:-none})"
  [ "$total" -ge "$APP_REPLICAS" ] && [ "$ready" -eq "$total" ]
}

worker_services_ready() {
  # §22 (Codex audit, 2026-09-13): celery_worker / celery_worker_heavy /
  # celery_beat artıq compose-da healthcheck daşıyır — deploy qapısı yalnız
  # app replikalarını yox, onları da gözləyir. Gözlənilən say: worker →
  # CELERY_REPLICAS (0 ola bilər), heavy və beat → 1. Healthcheck-siz
  # konteyner (məs. override ilə söndürülübsə) «running» ilə keçir.
  local spec service expected ids id status total=0 ready=0 summary=""
  for spec in "celery_worker:${CELERY_REPLICAS}" "celery_worker_heavy:1" "celery_beat:1"; do
    service="${spec%%:*}"
    expected="${spec##*:}"
    mapfile -t ids < <(docker compose -f "$COMPOSE_FILE" ps -q "$service" 2>/dev/null || true)
    local seen=0
    for id in "${ids[@]}"; do
      [ -n "$id" ] || continue
      status="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}nohc:{{.State.Status}}{{end}}' "$id" 2>/dev/null || true)"
      seen=$((seen + 1))
      total=$((total + 1))
      summary="${summary}${service}/${id:0:12}:${status:-unknown} "
      if [ "$status" = "healthy" ] || [ "$status" = "nohc:running" ]; then
        ready=$((ready + 1))
      fi
    done
    if [ "$seen" -lt "$expected" ]; then
      summary="${summary}${service}:${seen}/${expected}-present "
      total=$((total + expected - seen))
    fi
  done

  WORKER_HEALTH_SUMMARY="${ready}/${total} worker container(s) healthy (${summary:-none})"
  [ "$ready" -eq "$total" ]
}

resolve_build_git_sha() {
  # P1-07 (Codex audit, 2026-09-13): image-ə yazılacaq mənbə commit-i.
  # Üstünlük: açıq BUILD_GIT_SHA → GITHUB_SHA (CI deploy job-u; kod məhz bu
  # commit-dən rsync olunub) → APP_DIR-in öz .git-i (əl ilə klon) → unknown.
  # APP_DIR-in .git-i yoxdursa `git -C` işlədilmir: valideyn qovluqdakı
  # yad repo-nun HEAD-i götürülməsin.
  local sha="${BUILD_GIT_SHA:-}"
  if [ -z "$sha" ]; then
    sha="${GITHUB_SHA:-}"
  fi
  if [ -z "$sha" ] && [ -d "${APP_DIR}/.git" ] && command -v git >/dev/null 2>&1; then
    sha="$(git -C "$APP_DIR" rev-parse HEAD 2>/dev/null || true)"
  fi
  if ! [[ "$sha" =~ ^[0-9a-f]{7,64}$ ]]; then
    sha="unknown"
  fi
  BUILD_GIT_SHA="$sha"
  export BUILD_GIT_SHA
  echo "Build source commit: ${BUILD_GIT_SHA}"
}

preflight_django_deploy_check() {
  # P1-08 (Codex audit, 2026-09-13): fail-closed deploy preflight. Köhnə
  # axında TLS bayraqları söndürülmüş .env yalnız konteyner qalxanda
  # (production.py ImproperlyConfigured) üzə çıxırdı — və INSECURE_TRANSPORT_OK=1
  # onu da susdururdu. İndi (1) prod hostun .env-ində INSECURE_TRANSPORT_OK
  # doğru dəyərlə OLA BİLMƏZ (o yalnız CI-nin düz-HTTP prod-smoke yığını
  # üçündür); (2) qurulmuş image daxilində, real .env ilə `manage.py check
  # --deploy` işlədilir — xəta → deploy dayanır, xəbərdarlıqlar ucadan çıxır.
  local insecure_ok report
  insecure_ok="$(dotenv_value INSECURE_TRANSPORT_OK | tr '[:upper:]' '[:lower:]')"
  case "$insecure_ok" in
    1|true|yes|on)
      echo "INSECURE_TRANSPORT_OK=${insecure_ok} is set in ${APP_DIR}/.env." >&2
      echo "That flag exists only for the plain-HTTP CI smoke stack; a production host must serve HTTPS" >&2
      echo "with SECURE_SSL_REDIRECT / SESSION_COOKIE_SECURE / CSRF_COOKIE_SECURE enabled. Remove the flag and redeploy." >&2
      exit 1
      ;;
  esac

  report="${DEPLOY_TMP}/django-check-deploy.log"
  echo "Running Django deployment preflight (manage.py check --deploy --fail-level ${DEPLOY_CHECK_FAIL_LEVEL}) inside the built image..."
  if ! docker compose -f "$COMPOSE_FILE" run --rm -T -e RUN_RELEASE_ON_START=false app \
      python manage.py check --deploy --fail-level "$DEPLOY_CHECK_FAIL_LEVEL" >"$report" 2>&1; then
    cat "$report" >&2
    echo "Django deployment preflight FAILED (fail level ${DEPLOY_CHECK_FAIL_LEVEL}); nothing was migrated or restarted." >&2
    exit 1
  fi

  if grep -Eq '\([A-Za-z_.]+\.W[0-9]+\)' "$report"; then
    echo "==================== DJANGO DEPLOY CHECK WARNINGS ====================" >&2
    grep -E '\([A-Za-z_.]+\.W[0-9]+\)' "$report" >&2
    echo "Deploy continues because DEPLOY_CHECK_FAIL_LEVEL=${DEPLOY_CHECK_FAIL_LEVEL}; the default DEPLOY_CHECK_FAIL_LEVEL=WARNING blocks on these (CI does)." >&2
    echo "======================================================================" >&2
  else
    echo "Django deployment preflight passed with no warnings."
  fi
}

preflight_env_consistency() {
  # 2026-09-14 (deployment.md §5.2 A-1/A-3/A-5, audit P3-18): `manage.py check
  # --deploy` Django-nun görmədiyi .env invariantlarını yoxlayır. Hər sətir bir
  # qayda; xəta → deploy dayanır (heç nə qurulmayıb/miqrasiya olunmayıb).
  # Yalnız qeyri-sirr açarlar oxunur (dotenv_value); dəyərlər çap olunmur.
  local failures=0
  local app_user pg_max pgb_max_db pool reserve allowed_hosts redis_max redis_limit enforce
  app_user="$(dotenv_value APP_DATABASE_USER)"
  enforce="$(dotenv_value EMS_DB_ROLE_ENFORCE | tr '[:upper:]' '[:lower:]')"
  pg_max="$(dotenv_value POSTGRES_MAX_CONNECTIONS)"; pg_max="${pg_max:-250}"
  pgb_max_db="$(dotenv_value PGBOUNCER_MAX_DB_CONNECTIONS)"; pgb_max_db="${pgb_max_db:-230}"
  pool="$(dotenv_value PGBOUNCER_DEFAULT_POOL_SIZE)"; pool="${pool:-150}"
  reserve="$(dotenv_value PGBOUNCER_RESERVE_POOL_SIZE)"; reserve="${reserve:-50}"
  allowed_hosts="$(dotenv_value ALLOWED_HOSTS)"
  redis_max="$(dotenv_value REDIS_MAXMEMORY)"; redis_max="${redis_max:-3gb}"
  redis_limit="$(dotenv_value REDIS_MEM_LIMIT)"; redis_limit="${redis_limit:-4096M}"

  # A-1: tətbiq rolu ayrılmalıdır; `error` rejimi olmadan superuser-ə qayıdış səssiz keçər.
  if [ -z "$app_user" ]; then
    echo "ENV: APP_DATABASE_USER is empty — the app would run as the Postgres superuser and bypass RLS (deployment.md §5.2 A-1)." >&2
    failures=$((failures + 1))
  elif [ "$enforce" != "error" ]; then
    echo "ENV: EMS_DB_ROLE_ENFORCE=${enforce:-<unset>} — set it to 'error' once APP_DATABASE_USER is provisioned so a superuser fallback blocks the deploy (A-1). Continuing (warn)." >&2
  fi

  # P3-18: bütün rollar üzrə backend tavanı Postgres limitindən aşağı olmalıdır.
  for v in "$pg_max" "$pgb_max_db" "$pool" "$reserve"; do
    if ! [[ "$v" =~ ^[0-9]+$ ]]; then
      echo "ENV: POSTGRES_MAX_CONNECTIONS / PGBOUNCER_* must be integers (got '${v}')." >&2
      failures=$((failures + 1)); break
    fi
  done
  if [[ "$pg_max" =~ ^[0-9]+$ && "$pgb_max_db" =~ ^[0-9]+$ ]]; then
    if [ "$pgb_max_db" -gt $((pg_max - 20)) ]; then
      echo "ENV: PGBOUNCER_MAX_DB_CONNECTIONS=${pgb_max_db} must be <= POSTGRES_MAX_CONNECTIONS-20 (${pg_max}-20=$((pg_max - 20))): app + owner pools would exhaust Postgres (audit P3-18)." >&2
      failures=$((failures + 1))
    fi
    if [[ "$pool" =~ ^[0-9]+$ && "$reserve" =~ ^[0-9]+$ ]] && [ $((pool + reserve)) -gt "$pgb_max_db" ]; then
      echo "ENV: PGBOUNCER_DEFAULT_POOL_SIZE+RESERVE ($((pool + reserve))) exceeds PGBOUNCER_MAX_DB_CONNECTIONS=${pgb_max_db} — a single pool already hits the cap; lower the pool or raise the cap (with POSTGRES_MAX_CONNECTIONS)." >&2
      failures=$((failures + 1))
    fi
  fi

  # A-3: healthcheck / nginx scrape / Alertmanager webhook `Host: localhost` göndərir.
  if [ -n "$allowed_hosts" ] && [ "$allowed_hosts" != "*" ]; then
    case ",${allowed_hosts// /}," in
      *,localhost,*) ;;
      *)
        echo "ENV: ALLOWED_HOSTS must include 'localhost' (app healthcheck, /metrics/ scrape, Alertmanager webhook) — deployment.md §5.2 A-3." >&2
        failures=$((failures + 1))
        ;;
    esac
  fi

  # A-5: Redis maxmemory konteyner limitindən kiçik olmalıdır (əks halda OOM-kill, noeviction xətası deyil).
  local max_mb limit_mb
  max_mb="$(_to_mb "$redis_max")"; limit_mb="$(_to_mb "$redis_limit")"
  if [ -n "$max_mb" ] && [ -n "$limit_mb" ] && [ "$max_mb" -ge "$limit_mb" ]; then
    echo "ENV: REDIS_MAXMEMORY (${redis_max}) must be below REDIS_MEM_LIMIT (${redis_limit}) — leave ~25% headroom for AOF rewrite and client buffers (§5.2 A-5)." >&2
    failures=$((failures + 1))
  fi

  if [ "$failures" -gt 0 ]; then
    echo "Environment preflight FAILED (${failures} problem(s) in ${APP_DIR}/.env); nothing was built, migrated or restarted." >&2
    exit 1
  fi
  echo "Environment preflight passed (DB role, PgBouncer cap, ALLOWED_HOSTS, Redis memory)."
}

_to_mb() {
  # "3gb" / "512M" / "4096M" / "2G" / "1073741824" → MB (tam ədəd); tanınmayan → boş.
  local raw="$1" num unit
  raw="$(printf '%s' "$raw" | tr '[:upper:]' '[:lower:]')"
  num="${raw%%[a-z]*}"; unit="${raw#"$num"}"
  [[ "$num" =~ ^[0-9]+$ ]] || { printf ''; return 0; }
  case "$unit" in
    g|gb) printf '%s' $((num * 1024)) ;;
    m|mb) printf '%s' "$num" ;;
    k|kb) printf '%s' $((num / 1024)) ;;
    "") printf '%s' $((num / 1024 / 1024)) ;;
    *) printf '' ;;
  esac
}

verify_running_build_sha() {
  # P1-07 (Codex audit, 2026-09-13): /health/ `build.sha` bu deploy-un
  # qurduğu commit ilə eyni olmalıdır — fərq varsa nginx hələ köhnə image-in
  # replikasına yönləndirir və ya `APP_IMAGE` köhnə teqə baxır (image drift).
  local running_sha
  if [ "$BUILD_GIT_SHA" = "unknown" ]; then
    echo "BUILD_GIT_SHA is unknown; skipping image drift verification." >&2
    return 0
  fi
  if command -v python3 >/dev/null 2>&1; then
    running_sha="$(python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print((d.get("build") or {}).get("sha") or "missing")' "$HEALTH_JSON" 2>/dev/null || echo unreadable)"
  else
    running_sha="$(grep -Eo '"sha": *"[^"]*"' "$HEALTH_JSON" | head -n1 | sed -E 's/.*"sha": *"([^"]*)"/\1/')"
    running_sha="${running_sha:-missing}"
  fi
  if [ "$running_sha" != "$BUILD_GIT_SHA" ]; then
    echo "Image drift detected: /health/ reports build.sha=${running_sha}, but this deploy built ${BUILD_GIT_SHA}." >&2
    docker compose -f "$COMPOSE_FILE" ps >&2 || true
    exit 1
  fi
  echo "Running image verified: build.sha=${running_sha}."
}

resolve_release_image() {
  # 2026-09-14 infra auditi P2-5: hər deploy image-i mənbə SHA-sı ilə teqləyir
  # (`emsarena-prod:<sha>`); `latest` yalnız health-gate keçəndən SONRA bu
  # teqə çevrilir (promote_release_image). Beləliklə uğursuz deploy `latest`-i
  # korlamır və əvvəlki release teqi rollback üçün yerində qalır. SHA tapılmayan
  # əl deploy-unda vaxt damğalı teq işlədilir ki, yenə fərqləndirilə bilsin.
  local tag="$BUILD_GIT_SHA"
  if [ "$tag" = "unknown" ]; then
    tag="manual-$(date -u +%Y%m%dT%H%M%SZ)"
  fi
  APP_IMAGE="${APP_IMAGE_REPOSITORY}:${tag}"
  export APP_IMAGE
  echo "Release image: ${APP_IMAGE}"
}

capture_previous_app_image() {
  # 2026-09-14 infra auditi P2-5: yeni image qalxmazdan ƏVVƏL hazırda işləyən
  # app konteynerinin image teqi oxunur — health-gate uğursuz olsa məhz bu teqə
  # geri qayıdılır. Teq mövcud olmalıdır (`docker image inspect`); ilk keçiddə
  # köhnə konteynerlər `emsarena-prod:latest`-dən yaradılıb — o da rollback
  # hədəfi kimi keçərlidir, çünki `latest` yalnız uğurdan sonra dəyişir.
  local container_id image
  PREVIOUS_APP_IMAGE=""
  container_id="$(docker compose -f "$COMPOSE_FILE" ps -q app 2>/dev/null | head -n1 || true)"
  if [ -z "$container_id" ]; then
    echo "No running app container; rollback target is unavailable for this deploy." >&2
    return 0
  fi
  image="$(docker inspect --format '{{.Config.Image}}' "$container_id" 2>/dev/null || true)"
  if ! [[ "$image" =~ ^[A-Za-z0-9._/-]+:[A-Za-z0-9._-]+$ ]]; then
    echo "Running app image reference is not a plain tag (${image:-empty}); rollback target is unavailable." >&2
    return 0
  fi
  if [ "$image" = "$APP_IMAGE" ]; then
    echo "Running app container already uses ${image}; rollback would be a no-op." >&2
    return 0
  fi
  if ! docker image inspect "$image" >/dev/null 2>&1; then
    echo "Previous image ${image} no longer exists locally; rollback target is unavailable." >&2
    return 0
  fi
  PREVIOUS_APP_IMAGE="$image"
  echo "Rollback target captured: ${PREVIOUS_APP_IMAGE}"
}

predeploy_database_backup() {
  # 2026-09-14 infra auditi P2-5 (P2-7 minimal): miqrasiyalardan (release.sh)
  # ƏVVƏL postgres-backup sidecar-ının /backup.sh-ı ilə dump alınır — geri
  # qayıtma yalnız kodu geri alır, miqrasiyanı yox; DB-ni bu dump bərpa edir.
  # Dump uğursuzdursa deploy DAYANIR (fail-closed). Yalnız bilərəkdən
  # SKIP_PREDEPLOY_BACKUP=1 ilə keçilir (məs. sidecar nasazlığında, riski
  # qəbul edərək).
  case "$SKIP_PREDEPLOY_BACKUP" in
    1|true|TRUE|yes|on)
      echo "SKIP_PREDEPLOY_BACKUP=${SKIP_PREDEPLOY_BACKUP}: pre-deploy database dump skipped." >&2
      return 0
      ;;
  esac
  echo "Taking a pre-deploy database dump via postgres-backup (/backup.sh)..."
  if ! docker compose -f "$COMPOSE_FILE" exec -T postgres-backup /backup.sh; then
    echo "Pre-deploy database dump FAILED; nothing was migrated or restarted." >&2
    echo "Fix the postgres-backup sidecar (docker compose logs postgres-backup) or rerun with SKIP_PREDEPLOY_BACKUP=1 to accept the risk." >&2
    exit 1
  fi
  echo "Pre-deploy database dump completed."
}

wait_for_app_and_worker_health() {
  local max_attempts=$((DEPLOY_TIMEOUT_SECONDS / 5))
  local attempt=1
  local health_status

  if [ "$max_attempts" -lt 1 ]; then
    max_attempts=1
  fi

  while true; do
    # §22: app replikaları + celery worker/heavy/beat healthcheck-ləri birlikdə.
    if app_replicas_ready && worker_services_ready; then
      return 0
    fi
    health_status="${APP_HEALTH_SUMMARY}; ${WORKER_HEALTH_SUMMARY:-workers: not checked yet}"

    if [ "$attempt" -ge "$max_attempts" ]; then
      echo "App/worker containers did not become healthy within ${DEPLOY_TIMEOUT_SECONDS}s. Last status: ${health_status}" >&2
      docker compose -f "$COMPOSE_FILE" ps >&2 || true
      docker compose -f "$COMPOSE_FILE" logs --tail=200 app nginx celery_worker celery_worker_heavy celery_beat >&2 || true
      return 1
    fi

    echo "Waiting for app/worker health (${attempt}/${max_attempts})... ${health_status:-unknown}"
    sleep 5
    attempt=$((attempt + 1))
  done
}

rollback_to_previous_image() {
  # 2026-09-14 infra auditi P2-5: health-gate uğursuz olanda image daşıyan
  # servislər (app + celery) əvvəlki teq ilə yenidən yaradılır; miqrasiya
  # geri alınmır (deploy-öncəsi dump ilə bərpa — docs/operations/deployment.md §8).
  # `--no-build`: köhnə teq lokal image-dir, compose onu yenidən qurmasın.
  # Rollback-dan sonra nginx upstream-i təzələnir (yeni konteyner IP-ləri).
  # Nəticədən asılı olmayaraq çağıran `exit 1` edir — deploy uğursuzdur.
  if [ "$DEPLOY_ROLLBACK_ON_FAILURE" != "true" ]; then
    echo "DEPLOY_ROLLBACK_ON_FAILURE=${DEPLOY_ROLLBACK_ON_FAILURE}: leaving the failed release in place." >&2
    return 0
  fi
  if [ -z "${PREVIOUS_APP_IMAGE:-}" ]; then
    echo "No rollback target was captured before this deploy; the failed release stays in place." >&2
    echo "Manual rollback: APP_IMAGE=<previous tag> RUN_RELEASE_ON_START=false docker compose -f ${COMPOSE_FILE} up -d --no-build app celery_worker celery_worker_heavy celery_beat" >&2
    return 0
  fi
  echo "==================== ROLLING BACK TO ${PREVIOUS_APP_IMAGE} ====================" >&2
  if ! APP_IMAGE="$PREVIOUS_APP_IMAGE" RUN_RELEASE_ON_START=false docker compose -f "$COMPOSE_FILE" up -d --no-build \
      --scale app="$APP_REPLICAS" \
      --scale celery_worker="$CELERY_REPLICAS" \
      app celery_worker celery_worker_heavy celery_beat; then
    echo "Rollback 'docker compose up' FAILED; inspect the stack manually (docker compose ps / logs)." >&2
    return 0
  fi
  refresh_nginx_upstream || true
  if wait_for_app_and_worker_health; then
    echo "Rollback to ${PREVIOUS_APP_IMAGE} is healthy; the failed release ${APP_IMAGE} was NOT promoted to latest." >&2
  else
    echo "Rollback to ${PREVIOUS_APP_IMAGE} did not become healthy either; manual intervention required." >&2
  fi
  echo "Database migrations from the failed release were NOT reverted; restore the pre-deploy dump if the schema must go back." >&2
  echo "=======================================================================" >&2
}

promote_release_image() {
  # 2026-09-14 infra auditi P2-5: yalnız health-gate + /ping/ + /health/ +
  # build.sha yoxlaması keçəndən sonra `latest` bu release-ə göstərir. Manual
  # `docker compose up -d` (APP_IMAGE-siz) də həmişə sonuncu SAĞLAM release-i
  # işlədir.
  docker tag "$APP_IMAGE" "${APP_IMAGE_REPOSITORY}:latest"
  echo "Promoted ${APP_IMAGE} to ${APP_IMAGE_REPOSITORY}:latest."
}

prune_old_release_images() {
  # 2026-09-14 infra auditi P2-5: release teqləri yığılmasın — cari və əvvəlki
  # (rollback hədəfi) heç vaxt silinmir; qalan ən yeni DEPLOY_KEEP_RELEASE_IMAGES
  # teq saxlanılır. `docker image ls` yaradılma vaxtına görə (yeni→köhnə)
  # sıralayır. Silinmə uğursuzluğu deploy-u pozmur.
  local tag kept=0
  for tag in $(docker image ls --format '{{.Tag}}' "$APP_IMAGE_REPOSITORY" 2>/dev/null || true); do
    case "$tag" in
      latest|'<none>') continue ;;
    esac
    if [ "${APP_IMAGE_REPOSITORY}:${tag}" = "$APP_IMAGE" ] || [ "${APP_IMAGE_REPOSITORY}:${tag}" = "${PREVIOUS_APP_IMAGE:-}" ]; then
      continue
    fi
    kept=$((kept + 1))
    if [ "$kept" -gt "$DEPLOY_KEEP_RELEASE_IMAGES" ]; then
      echo "Removing old release image ${APP_IMAGE_REPOSITORY}:${tag}"
      docker image rm "${APP_IMAGE_REPOSITORY}:${tag}" >/dev/null 2>&1 || true
    fi
  done
}

docker_deploy() {
  if [ ! -f "$COMPOSE_FILE" ]; then
    echo "Missing ${APP_DIR}/${COMPOSE_FILE}." >&2
    exit 1
  fi

  if ! command -v docker >/dev/null 2>&1; then
    echo "Docker is required for DEPLOY_MODE=docker." >&2
    exit 1
  fi

  docker compose version >/dev/null
  # §5.2 .env invariantları — hər şeydən əvvəl (heç bir konteynerə toxunmadan).
  preflight_env_consistency
  # lan rejimində publik DNS yoxdur — DNS preflight yalnız direct-edge üçündür.
  if [ "$EDGE_PROXY_MODE" = "direct" ]; then
    preflight_direct_dns
  fi
  validate_origin_cert
  remove_legacy_edge_firewall

  resolve_build_git_sha
  # P2-5: compose `image:` bu teqi alır — build, preflight, release və up
  # hamısı eyni `emsarena-prod:<sha>` image-i ilə işləyir; `latest` toxunulmur.
  resolve_release_image
  docker compose -f "$COMPOSE_FILE" config >"$COMPOSE_CONFIG"
  docker compose -f "$COMPOSE_FILE" build
  capture_previous_app_image
  docker compose -f "$COMPOSE_FILE" up -d postgres redis pgbouncer postgres-backup
  # P1-08: konfiqurasiya xətası miqrasiyadan və restart-dan ƏVVƏL tutulur.
  preflight_django_deploy_check
  # P2-5: miqrasiyadan ƏVVƏL dump — rollback yalnız kodu geri alır.
  predeploy_database_backup
  docker compose -f "$COMPOSE_FILE" run --rm -e RUN_RELEASE_ON_START=false app /app/docker/release.sh
  RUN_RELEASE_ON_START=false docker compose -f "$COMPOSE_FILE" up -d --remove-orphans \
    --scale app="$APP_REPLICAS" \
    --scale celery_worker="$CELERY_REPLICAS"

  wait_for_app_and_worker_health || {
    rollback_to_previous_image
    exit 1
  }

  refresh_nginx_upstream
  reload_prometheus_config
  recreate_alertmanager

  wait_for_http "${APP_BASE_URL}${PING_PATH}" "200" "$PING_JSON" || {
    docker compose -f "$COMPOSE_FILE" ps >&2 || true
    docker compose -f "$COMPOSE_FILE" logs --tail=200 app nginx >&2 || true
    rollback_to_previous_image
    exit 1
  }

  wait_for_http "${APP_BASE_URL}${HEALTH_PATH}" "200 207" "$HEALTH_JSON" || {
    docker compose -f "$COMPOSE_FILE" ps >&2 || true
    docker compose -f "$COMPOSE_FILE" logs --tail=200 app nginx >&2 || true
    rollback_to_previous_image
    exit 1
  }

  verify_running_build_sha

  # P2-5: bütün qapılar keçdi — `latest` bu release-ə çevrilir, köhnə teqlər
  # (cari + rollback hədəfi istisna) DEPLOY_KEEP_RELEASE_IMAGES-ə qədər saxlanır.
  promote_release_image
  prune_old_release_images

  docker compose -f "$COMPOSE_FILE" ps
}

case "$DEPLOY_MODE" in
  docker)
    docker_deploy
    ;;
  legacy)
    legacy_deploy
    ;;
  *)
    echo "Unsupported DEPLOY_MODE=${DEPLOY_MODE}. Use 'docker' or 'legacy'." >&2
    exit 1
    ;;
esac

echo "Deployment completed successfully."
