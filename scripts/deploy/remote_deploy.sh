#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/emsarena/app}"
VENV_DIR="${VENV_DIR:-/opt/emsarena/venv}"
SERVICE_NAME="${SERVICE_NAME:-emsarena.service}"
APP_BASE_URL="${APP_BASE_URL:-http://127.0.0.1}"
HEALTHCHECK_HOST="${HEALTHCHECK_HOST:-emsarena.com}"
PING_PATH="${PING_PATH:-/ping/}"
HEALTH_PATH="${HEALTH_PATH:-/health/}"
DISABLE_LEGACY_DAPHNE_SERVICE="${DISABLE_LEGACY_DAPHNE_SERVICE:-true}"
DEPLOY_TIMEOUT_SECONDS="${DEPLOY_TIMEOUT_SECONDS:-300}"
DEPLOY_MODE="${DEPLOY_MODE:-docker}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"

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
  -H "X-Forwarded-Proto: https"
)

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
    status="$(curl -s -o "$body_file" -w '%{http_code}' "${curl_headers[@]}" "$url" || true)"
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

  wait_for_http "${APP_BASE_URL}${PING_PATH}" "200" "/tmp/emsarena-ping.json" || {
    $SUDO systemctl status "$SERVICE_NAME" --no-pager || true
    journalctl -u "$SERVICE_NAME" -n 200 --no-pager || true
    exit 1
  }

  wait_for_http "${APP_BASE_URL}${HEALTH_PATH}" "200 207" "/tmp/emsarena-health.json" || {
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

  docker compose -f "$COMPOSE_FILE" config >/tmp/emsarena-compose-config.yml
  docker compose -f "$COMPOSE_FILE" up -d --build

  local max_attempts=$((DEPLOY_TIMEOUT_SECONDS / 5))
  local attempt=1
  local health_status

  if [ "$max_attempts" -lt 1 ]; then
    max_attempts=1
  fi

  while true; do
    health_status="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' emsarena-app 2>/dev/null || true)"
    if [ "$health_status" = "healthy" ] || [ "$health_status" = "running" ]; then
      break
    fi

    if [ "$attempt" -ge "$max_attempts" ]; then
      echo "emsarena-app did not become healthy within ${DEPLOY_TIMEOUT_SECONDS}s. Last status: ${health_status}" >&2
      docker compose -f "$COMPOSE_FILE" ps >&2 || true
      docker compose -f "$COMPOSE_FILE" logs --tail=200 app nginx >&2 || true
      exit 1
    fi

    echo "Waiting for emsarena-app health (${attempt}/${max_attempts})... ${health_status:-unknown}"
    sleep 5
    attempt=$((attempt + 1))
  done

  wait_for_http "${APP_BASE_URL}${PING_PATH}" "200" "/tmp/emsarena-ping.json" || {
    docker compose -f "$COMPOSE_FILE" ps >&2 || true
    docker compose -f "$COMPOSE_FILE" logs --tail=200 app nginx >&2 || true
    exit 1
  }

  wait_for_http "${APP_BASE_URL}${HEALTH_PATH}" "200 207" "/tmp/emsarena-health.json" || {
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
