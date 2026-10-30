#!/usr/bin/env bash
# Pinned file SHA, exact source line IDs, then fresh baseline/receipt selection.
match "$ROSTER_TAG" '^reviewed-workload-[0-9a-z-]+$' || exit 2
match "$BATCH" '^[0-9a-f]{64}$' || exit 2
match "$ROW_GROUP" '^[1-9][0-9]*(,[1-9][0-9]*)*$' || { echo "explicit_source_lines_required" >&2; exit 2; }
IFS=, read -r -a source_lines <<< "$ROW_GROUP"
args=(--org "$ORG" --actor "$actor" --manifest "/tmp/reviewed_source_${GITHUB_RUN_ID}.json" --manifest-sha256 "$BATCH" --lines "${source_lines[@]}")
if [[ "$ROW_SUBJECT" == source-* ]]; then
  undo_batch="${ROW_SUBJECT%%:*}"
  match "$undo_batch" '^source-[0-9]{8}-[0-9]{6}-[0-9a-f]{8}$' || exit 2
  args+=(--undo "$undo_batch")
  if [[ "$ROW_SUBJECT" == *:* ]]; then
    baseline="${ROW_SUBJECT#*:}"
    match "$baseline" '^[0-9a-f]{64}$' || exit 2
    args+=(--expected-baseline "$baseline")
  else
    test "$APPLY" != "true" || { echo "undo_apply_fresh_baseline_required" >&2; exit 2; }
  fi
elif [ -n "$ROW_SUBJECT" ]; then
  match "$ROW_SUBJECT" '^[0-9a-f]{64}$' || exit 2
  args+=(--expected-baseline "$ROW_SUBJECT")
else
  test "$APPLY" != "true" || { echo "apply_fresh_baseline_required" >&2; exit 2; }
fi
