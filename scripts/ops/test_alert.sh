#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
# EMSArena — fire a test alert through Alertmanager to verify email delivery.
#   sudo scripts/ops/test_alert.sh
# Sends a "critical" test alert to the configured receiver (email → the address
# in ALERT_EMAIL_TO). Check that inbox afterwards; check delivery in the logs:
#   docker logs --since 2m emsarena-alertmanager | grep -i notify
# ═══════════════════════════════════════════════════════════════════════════
set -euo pipefail
AM_CONTAINER="${AM_CONTAINER:-emsarena-alertmanager}"

payload='[{"labels":{"alertname":"EMSArenaTestAlert","severity":"critical","job":"ops-test"},"annotations":{"summary":"TEST alert — please ignore","description":"Verifying Alertmanager -> email delivery"}}]'

docker exec "$AM_CONTAINER" wget -qO- \
  --header="Content-Type: application/json" \
  --post-data="$payload" \
  http://127.0.0.1:9093/api/v2/alerts >/dev/null && echo "Test alert posted."

echo "Waiting for delivery..."; sleep 38
echo "--- Alertmanager notify result ---"
docker logs --since 2m "$AM_CONTAINER" 2>&1 | grep -iE "notify|smtp|EMSArenaTestAlert" | tail -6
