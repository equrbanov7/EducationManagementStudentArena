#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/emsarena/app}"
VENV_DIR="${VENV_DIR:-/opt/emsarena/venv}"
SERVICE_NAME="${SERVICE_NAME:-emsarena.service}"
DEPLOY_MODE="${DEPLOY_MODE:-docker}"
if [ -z "${APP_BASE_URL:-}" ]; then
  if [ "$DEPLOY_MODE" = "docker" ]; then
    APP_BASE_URL="https://127.0.0.1"
  else
    APP_BASE_URL="http://127.0.0.1"
  fi
fi
HEALTHCHECK_HOST="${HEALTHCHECK_HOST:-emsarena.com}"
ORIGIN_HEALTHCHECK_INSECURE_TLS="${ORIGIN_HEALTHCHECK_INSECURE_TLS:-true}"
EDGE_PROXY_MODE="${EDGE_PROXY_MODE:-cloudflare}"
PING_PATH="${PING_PATH:-/ping/}"
HEALTH_PATH="${HEALTH_PATH:-/health/}"
DISABLE_LEGACY_DAPHNE_SERVICE="${DISABLE_LEGACY_DAPHNE_SERVICE:-true}"
DEPLOY_TIMEOUT_SECONDS="${DEPLOY_TIMEOUT_SECONDS:-300}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
APP_REPLICAS="${APP_REPLICAS:-1}"
CELERY_REPLICAS="${CELERY_REPLICAS:-1}"
CLOUDFLARE_REALIP_FILE="${APP_DIR}/docker/nginx/cloudflare-realip.conf"

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

if [ "$EDGE_PROXY_MODE" != "cloudflare" ] && [ "$EDGE_PROXY_MODE" != "direct" ]; then
  echo "EDGE_PROXY_MODE must be 'cloudflare' or 'direct'." >&2
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

ensure_origin_cert() {
  local cert_dir="${APP_DIR}/docker/nginx/certs"
  local cert_file="${cert_dir}/origin.crt"
  local key_file="${cert_dir}/origin.key"

  mkdir -p "$cert_dir"
  chmod 700 "$cert_dir"

  if [ -s "$cert_file" ] && [ -s "$key_file" ]; then
    return 0
  fi

  if ! command -v openssl >/dev/null 2>&1; then
    echo "openssl is required to create the nginx origin certificate." >&2
    exit 1
  fi

  openssl req -x509 -nodes -newkey rsa:2048 -days 825 \
    -keyout "$key_file" \
    -out "$cert_file" \
    -subj '/CN=emsarena.com' \
    -addext 'subjectAltName=DNS:emsarena.com,DNS:www.emsarena.com' >/dev/null 2>&1
  chmod 600 "$key_file"
  chmod 644 "$cert_file"
}

sync_cloudflare_networks() {
  if ! command -v python3 >/dev/null 2>&1; then
    echo "python3 is required to validate Cloudflare network ranges." >&2
    exit 1
  fi
  python3 "${APP_DIR}/scripts/deploy/sync_cloudflare_networks.py" \
    --output "$CLOUDFLARE_REALIP_FILE"
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

configure_cloudflare_firewall_family() {
  local tool="$1"
  local chain="$2"
  local iface="$3"
  local family="$4"
  local cidr
  local port

  command -v "$tool" >/dev/null 2>&1 || return 0
  $SUDO "$tool" -S DOCKER-USER >/dev/null 2>&1 || return 0

  remove_edge_firewall_family "$tool" "$chain" "$iface"
  $SUDO "$tool" -N "$chain"
  while read -r cidr; do
    [ -n "$cidr" ] || continue
    if { [ "$family" = "4" ] && [[ "$cidr" != *:* ]]; } || \
       { [ "$family" = "6" ] && [[ "$cidr" == *:* ]]; }; then
      $SUDO "$tool" -A "$chain" -s "$cidr" -j ACCEPT
    fi
  done < <(awk '/^set_real_ip_from / {gsub(/;/, "", $2); print $2}' "$CLOUDFLARE_REALIP_FILE")
  $SUDO "$tool" -A "$chain" -j DROP

  for port in 80 443; do
    $SUDO "$tool" -I DOCKER-USER 1 -i "$iface" -p tcp -m conntrack \
      --ctstate NEW --ctorigdstport "$port" -j "$chain"
  done
}

configure_edge_firewall() {
  local iface
  iface="$(ip -4 route show default 2>/dev/null | awk '{print $5; exit}')"
  if [ -z "$iface" ]; then
    echo "Unable to determine the public network interface." >&2
    exit 1
  fi

  if [ "$EDGE_PROXY_MODE" = "direct" ]; then
    remove_edge_firewall_family iptables EMSARENA-CF-WEB "$iface"
    remove_edge_firewall_family ip6tables EMSARENA-CF-WEB6 "$iface"
    return 0
  fi

  sync_cloudflare_networks
  configure_cloudflare_firewall_family iptables EMSARENA-CF-WEB "$iface" 4
  configure_cloudflare_firewall_family ip6tables EMSARENA-CF-WEB6 "$iface" 6
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
  ensure_origin_cert
  configure_edge_firewall

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
