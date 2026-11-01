#!/usr/bin/env bash
# Fixed-four receipt only. No selector can expand the two journals or four points.
# shellcheck disable=SC2154
match "$ROSTER_TAG" '^reviewed-content-[0-9a-z-]+$' || exit 2
test "$BATCH" = 00fd00569b1a1af9460c57db647313622a70b0026d06716cf3843311d490ba1f || exit 2
match "$ROW_GROUP" '^content-[0-9]{8}-[0-9]{6}-[0-9a-f]{8}$' || exit 2
args=(--org "$ORG" --actor "$actor" --manifest "/tmp/reviewed_content_${GITHUB_RUN_ID}.json" --batch "$ROW_GROUP")
if [ -n "$ROW_SUBJECT" ]; then
  match "$ROW_SUBJECT" '^[0-9a-f]{64}$' || exit 2
  args+=(--expected-baseline "$ROW_SUBJECT")
else
  test "$APPLY" != true || { echo 'four_undo_apply_fresh_baseline_required' >&2; exit 2; }
fi
