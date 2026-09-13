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
# preflight-ının səviyyəsi. ERROR → xətada deploy dayanır, xəbərdarlıqlar
# (security.W004/W008/W012/W016 …) ucadan çap olunur; WARNING → onlar da
# dayandırır (CI-nin _security.yml qapısı ilə eyni sərtlik).
DEPLOY_CHECK_FAIL_LEVEL="${DEPLOY_CHECK_FAIL_LEVEL:-ERROR}"

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
  # alertmanager.tmpl.yml is rendered by `sed` in the container ENTRYPOINT into
  # /tmp/alertmanager.yml, so neither a bind-mount content change nor SIGHUP
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
    echo "Deploy continues (DEPLOY_CHECK_FAIL_LEVEL=${DEPLOY_CHECK_FAIL_LEVEL}); set DEPLOY_CHECK_FAIL_LEVEL=WARNING to block on these." >&2
    echo "======================================================================" >&2
  else
    echo "Django deployment preflight passed with no warnings."
  fi
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
  # lan rejimində publik DNS yoxdur — DNS preflight yalnız direct-edge üçündür.
  if [ "$EDGE_PROXY_MODE" = "direct" ]; then
    preflight_direct_dns
  fi
  validate_origin_cert
  remove_legacy_edge_firewall

  resolve_build_git_sha
  docker compose -f "$COMPOSE_FILE" config >"$COMPOSE_CONFIG"
  docker compose -f "$COMPOSE_FILE" build
  docker compose -f "$COMPOSE_FILE" up -d postgres redis pgbouncer
  # P1-08: konfiqurasiya xətası miqrasiyadan və restart-dan ƏVVƏL tutulur.
  preflight_django_deploy_check
  docker compose -f "$COMPOSE_FILE" run --rm -e RUN_RELEASE_ON_START=false app /app/docker/release.sh
  RUN_RELEASE_ON_START=false docker compose -f "$COMPOSE_FILE" up -d --remove-orphans \
    --scale app="$APP_REPLICAS" \
    --scale celery_worker="$CELERY_REPLICAS"

  local max_attempts=$((DEPLOY_TIMEOUT_SECONDS / 5))
  local attempt=1
  local health_status

  if [ "$max_attempts" -lt 1 ]; then
    max_attempts=1
  fi

  while true; do
    # §22: app replikaları + celery worker/heavy/beat healthcheck-ləri birlikdə.
    if app_replicas_ready && worker_services_ready; then
      break
    fi
    health_status="${APP_HEALTH_SUMMARY}; ${WORKER_HEALTH_SUMMARY:-workers: not checked yet}"

    if [ "$attempt" -ge "$max_attempts" ]; then
      echo "App/worker containers did not become healthy within ${DEPLOY_TIMEOUT_SECONDS}s. Last status: ${health_status}" >&2
      docker compose -f "$COMPOSE_FILE" ps >&2 || true
      docker compose -f "$COMPOSE_FILE" logs --tail=200 app nginx celery_worker celery_worker_heavy celery_beat >&2 || true
      exit 1
    fi

    echo "Waiting for app/worker health (${attempt}/${max_attempts})... ${health_status:-unknown}"
    sleep 5
    attempt=$((attempt + 1))
  done

  refresh_nginx_upstream
  reload_prometheus_config
  recreate_alertmanager

  wait_for_http "${APP_BASE_URL}${PING_PATH}" "200" "$PING_JSON" || {
    docker compose -f "$COMPOSE_FILE" ps >&2 || true
    docker compose -f "$COMPOSE_FILE" logs --tail=200 app nginx >&2 || true
    exit 1
  }

  wait_for_http "${APP_BASE_URL}${HEALTH_PATH}" "200 207" "$HEALTH_JSON" || {
    docker compose -f "$COMPOSE_FILE" ps >&2 || true
    docker compose -f "$COMPOSE_FILE" logs --tail=200 app nginx >&2 || true
    exit 1
  }

  verify_running_build_sha

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
