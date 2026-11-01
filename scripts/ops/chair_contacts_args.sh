#!/usr/bin/env bash
# Fixed reviewed scope lives in the command; apply requires a fresh baseline.
# shellcheck disable=SC2154
actor="$(superadmin_actor)"; test -n "$actor" || exit 2
echo "::add-mask::$actor"
args=(--actor "$actor" --safe-summary)
test -z "$ROSTER_TAG" || { echo "unused_source_selector" >&2; exit 2; }
if [ -n "$ROW_GROUP" ]; then
  match "$ROW_GROUP" '^(az_morphology|az_onomastics|tarix_europe|tarix_region)(,(az_morphology|az_onomastics|tarix_europe|tarix_region))*$' || exit 2
  args+=(--selection "$ROW_GROUP")
fi
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
