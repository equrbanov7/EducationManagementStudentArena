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
APP_REPLICAS="${APP_REPLICAS:-$(dotenv_value APP_REPLICAS)}"
APP_REPLICAS="${APP_REPLICAS:-1}"
CELERY_REPLICAS="${CELERY_REPLICAS:-$(dotenv_value CELERY_REPLICAS)}"
CELERY_REPLICAS="${CELERY_REPLICAS:-1}"

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

  docker compose -f "$COMPOSE_FILE" config >"$COMPOSE_CONFIG"
  docker compose -f "$COMPOSE_FILE" build
  docker compose -f "$COMPOSE_FILE" up -d postgres redis pgbouncer
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
    if app_replicas_ready; then
      break
    fi
    health_status="$APP_HEALTH_SUMMARY"

    if [ "$attempt" -ge "$max_attempts" ]; then
      echo "App replicas did not become healthy within ${DEPLOY_TIMEOUT_SECONDS}s. Last status: ${health_status}" >&2
      docker compose -f "$COMPOSE_FILE" ps >&2 || true
      docker compose -f "$COMPOSE_FILE" logs --tail=200 app nginx >&2 || true
      exit 1
    fi

    echo "Waiting for app replica health (${attempt}/${max_attempts})... ${health_status:-unknown}"
    sleep 5
    attempt=$((attempt + 1))
  done

  refresh_nginx_upstream

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
