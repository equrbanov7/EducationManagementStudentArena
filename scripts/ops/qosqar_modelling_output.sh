#!/usr/bin/env bash
# Numeric counts and the opaque baseline only; never print raw source or teacher data.

# args comes from the dispatcher argument helper.
# shellcheck disable=SC2154
docker exec -i "$APP_CONTAINER" python manage.py "$COMMAND" "${args[@]}" > "$RUNNER_TEMP/out.log" 2>&1 || status=$?
grep -E '^qosqar_modelling: ([a-z_]+=[0-9]+|baseline=[a-f0-9]{64})( ([a-z_]+=[0-9]+|baseline=[a-f0-9]{64}))*$' "$RUNNER_TEMP/out.log" > "$RUNNER_TEMP/summary.log" || true
cat "$RUNNER_TEMP/summary.log"
if [ "${status:-0}" != 0 ]; then
  grep -Eo 'CommandError: [a-z_]+' "$RUNNER_TEMP/out.log" | head -n 1 || true
  rm -f "$RUNNER_TEMP/out.log"
  exit "$status"
fi
rm -f "$RUNNER_TEMP/out.log"
