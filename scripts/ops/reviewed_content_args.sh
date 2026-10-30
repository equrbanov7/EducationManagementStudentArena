#!/usr/bin/env bash
# Sourced API: actor and workflow inputs belong to the caller.
# shellcheck disable=SC2154
match "$ROSTER_TAG" '^reviewed-content-[0-9a-z-]+$' || exit 2
match "$BATCH" '^[0-9a-f]{64}$' || exit 2
uuid_pattern='[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}'
match "$ROW_GROUP" "^${uuid_pattern}(,${uuid_pattern})*$" || { echo "explicit_content_targets_required" >&2; exit 2; }
IFS=, read -r -a content_targets <<< "$ROW_GROUP"
args=(--org "$ORG" --actor "$actor" --manifest "/tmp/reviewed_content_${GITHUB_RUN_ID}.json" --manifest-sha256 "$BATCH" --targets "${content_targets[@]}")
if [ -n "$ROW_SUBJECT" ]; then
  match "$ROW_SUBJECT" '^[0-9a-f]{64}$' || exit 2
  args+=(--expected-baseline "$ROW_SUBJECT")
else
  test "$APPLY" != "true" || { echo "content_apply_fresh_baseline_required" >&2; exit 2; }
fi
