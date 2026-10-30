#!/usr/bin/env bash
# No raw command output reaches the public log; backup and apply confirmation stay in the caller.
set -euo pipefail
umask 077
case "$COMMAND" in
  repair_sbio235_workload) prefix=sbio_repair; batch_prefix=sbio235 ;;
  repair_233ke_group_alias) prefix=ke233_alias; batch_prefix=ke233 ;;
  *) echo "fixed_repair_command_not_allowed" >&2; exit 2 ;;
esac
output="$RUNNER_TEMP/out.log"
summary="$RUNNER_TEMP/summary.log"
status=0
docker exec -i "$APP_CONTAINER" python manage.py "$COMMAND" "$@" > "$output" 2>&1 || status=$?
grep -E "^${prefix}: mode=(dry_run|apply|undo)( (baseline=[0-9a-f]{64}|batch=${batch_prefix}-[0-9]{8}-[0-9]{6}-[0-9a-f]{4}|[a-z_]+=[0-9]+))+$" "$output" > "$summary" || true
cat "$summary"
if [ "$status" != 0 ]; then
  grep -E '^CommandError: [a-z_]+$' "$output" | head -n 1 || true
fi
rm -f "$output"
exit "$status"
