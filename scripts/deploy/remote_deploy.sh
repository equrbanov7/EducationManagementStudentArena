#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/emsarena/app}"
VENV_DIR="${VENV_DIR:-/opt/emsarena/venv}"
SERVICE_NAME="${SERVICE_NAME:-emsarena.service}"
APP_BASE_URL="${APP_BASE_URL:-http://127.0.0.1:8001}"
HEALTHCHECK_HOST="${HEALTHCHECK_HOST:-emsarena.com}"
PING_PATH="${PING_PATH:-/ping/}"
HEALTH_PATH="${HEALTH_PATH:-/health/}"
DISABLE_LEGACY_DAPHNE_SERVICE="${DISABLE_LEGACY_DAPHNE_SERVICE:-true}"
DEPLOY_TIMEOUT_SECONDS="${DEPLOY_TIMEOUT_SECONDS:-180}"

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

max_attempts=$((DEPLOY_TIMEOUT_SECONDS / 5))
attempt=1
ping_url="${APP_BASE_URL}${PING_PATH}"
health_url="${APP_BASE_URL}${HEALTH_PATH}"

until curl -fsS -H "Host: ${HEALTHCHECK_HOST}" "$ping_url" >/dev/null 2>&1; do
  if [ "$attempt" -ge "$max_attempts" ]; then
    echo "Application did not become ready within ${DEPLOY_TIMEOUT_SECONDS}s." >&2
    $SUDO systemctl status "$SERVICE_NAME" --no-pager || true
    journalctl -u "$SERVICE_NAME" -n 200 --no-pager || true
    exit 1
  fi

  echo "Waiting for ${ping_url} (${attempt}/${max_attempts})..."
  sleep 5
  attempt=$((attempt + 1))
done

health_status="$(curl -s -o /tmp/emsarena-health.json -w '%{http_code}' -H "Host: ${HEALTHCHECK_HOST}" "$health_url" || true)"
if [ "$health_status" != "200" ] && [ "$health_status" != "207" ]; then
  echo "Health check failed with HTTP ${health_status}." >&2
  cat /tmp/emsarena-health.json >&2 || true
  $SUDO systemctl status "$SERVICE_NAME" --no-pager || true
  journalctl -u "$SERVICE_NAME" -n 200 --no-pager || true
  exit 1
fi

$SUDO systemctl status "$SERVICE_NAME" --no-pager | sed -n '1,20p'
echo "Deployment completed successfully."
