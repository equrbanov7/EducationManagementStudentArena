#!/usr/bin/env bash
# Sourced dispatcher: log only a strict numeric/hash summary and fixed error code.
# shellcheck disable=SC2154
umask 077
status=0
docker exec -i "$APP_CONTAINER" python manage.py "$COMMAND" "${args[@]}" > "$RUNNER_TEMP/out.log" 2>&1 || status=$?
summary_status=0
case "$COMMAND" in
  repair_biostat_seminar_share)
    grep -E '^biostat_kind_share: mode=(dry_run|apply)( (already_present=[01]|owner_unchanged=1|roster=[1-9][0-9]*|seminar_hours=15|shares_to_create=[01]|shares_to_remove=1|baseline=[0-9a-f]{64}))*$' "$RUNNER_TEMP/out.log" > "$RUNNER_TEMP/summary.log" || summary_status=2
    test "$(wc -l < "$RUNNER_TEMP/summary.log")" -eq 1 || summary_status=2
    grep -Eq ' baseline=[0-9a-f]{64}( |$)' "$RUNNER_TEMP/summary.log" || summary_status=2
    grep -Eq ' owner_unchanged=1( |$)' "$RUNNER_TEMP/summary.log" || summary_status=2 ;;
  repair_mr34_teacher_load)
    python3 scripts/ops/mr34_teacher_summary.py "$RUNNER_TEMP/out.log" > "$RUNNER_TEMP/summary.log" || summary_status=2 ;;
  *) echo "fixed_access_command_required" >&2; rm -f "$RUNNER_TEMP/out.log"; exit 2 ;;
esac
if [ "$status" != 0 ]; then
  grep -Eo 'CommandError: [a-z0-9_]+$' "$RUNNER_TEMP/out.log" | head -n 1 || true
  rm -f "$RUNNER_TEMP/out.log" "$RUNNER_TEMP/summary.log"
  exit "$status"
fi
if [ "$summary_status" != 0 ]; then
  echo "safe_summary_missing_or_invalid" >&2
  rm -f "$RUNNER_TEMP/out.log" "$RUNNER_TEMP/summary.log"
  exit 2
fi
cat "$RUNNER_TEMP/summary.log"
rm -f "$RUNNER_TEMP/out.log"
