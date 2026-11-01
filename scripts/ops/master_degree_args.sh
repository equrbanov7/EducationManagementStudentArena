#!/usr/bin/env bash
# Fixed reviewed scope lives in the command; apply requires a fresh baseline.
# shellcheck disable=SC2154
actor="$(superadmin_actor)"; test -n "$actor" || exit 2
echo "::add-mask::$actor"
args=(--actor "$actor" --safe-summary)
test -z "$ROSTER_TAG" || { echo "unused_source_selector" >&2; exit 2; }
test -z "$ROW_GROUP" || { echo "unused_group_selector" >&2; exit 2; }
if [ -n "$BATCH" ]; then
  match "$BATCH" '^[0-9a-f]{64}$' || exit 2
  args+=(--expected-baseline "$BATCH")
else
  test "$APPLY" != "true" || { echo "fresh_baseline_required" >&2; exit 2; }
fi
if [ -n "$ROW_SUBJECT" ]; then
  match "$ROW_SUBJECT" '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$' || exit 2
  args+=(--undo "$ROW_SUBJECT")
fi
