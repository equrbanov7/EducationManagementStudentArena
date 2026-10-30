#!/usr/bin/env bash
# No raw command output reaches the public log; backup and apply confirmation stay in the caller.
set -euo pipefail
umask 077
case "$COMMAND" in
  repair_sbio235_workload) prefix=sbio_repair; batch_prefix=sbio235 ;;
  repair_233ke_group_alias) prefix=ke233_alias; batch_prefix=ke233 ;;
  repair_cavid_source_batch) prefix=cavid3536; batch_prefix=cavid3536 ;;
  repair_reviewed_workload_batch) prefix=reviewed_source; batch_prefix=source ;;
  *) echo "fixed_repair_command_not_allowed" >&2; exit 2 ;;
esac
batch_length=4
if [ "$COMMAND" = "repair_reviewed_workload_batch" ]; then batch_length=8; fi
output="$RUNNER_TEMP/out.log"
summary="$RUNNER_TEMP/summary.log"
status=0
docker exec -i "$APP_CONTAINER" python manage.py "$COMMAND" "$@" > "$output" 2>&1 || status=$?
grep -E "^${prefix}: mode=(dry_run|apply|undo)( (baseline=[0-9a-f]{64}|batch=${batch_prefix}-[0-9]{8}-[0-9]{6}-[0-9a-f]{${batch_length}}|[a-z_]+=[0-9]+))+$" "$output" > "$summary" || true
cat "$summary"
if [ "$status" != 0 ]; then
  grep -E '^CommandError: [a-z_]+$' "$output" | head -n 1 || true
fi
rm -f "$output"
exit "$status"
