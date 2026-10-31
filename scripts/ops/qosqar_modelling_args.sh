#!/usr/bin/env bash
# Sourced by production ops; roster_tag always identifies the encrypted evidence.
actor="$(superadmin_actor)"; test -n "$actor" || { echo "active_superadmin_required" >&2; exit 1; }
echo "::add-mask::$actor"
match "$BATCH" '^de8001e6a3a31bb3bc98762959c5f8106aa49fc4b667a8102a9e0c442d58e055$' || { echo "pinned_source_sha256_required" >&2; exit 2; }
args=(--org "$ORG" --actor "$actor" --source-evidence "/tmp/qosqar_modelling_${GITHUB_RUN_ID}.json")
if [ -n "$ROW_SUBJECT" ]; then
  match "$ROW_SUBJECT" '^[0-9a-f]{64}$' || { echo "baseline_sha256_required" >&2; exit 2; }
  args+=(--expected-baseline "$ROW_SUBJECT")
fi
if [ "$APPLY" = "true" ] && [ -z "$ROW_SUBJECT" ]; then
  echo "fresh_live_baseline_required" >&2; exit 2
fi
case "${ROW_GROUP:-}" in
  "") ;;
  undo)
    test "$APPLY" = "true" || { echo "undo_requires_apply" >&2; exit 2; }
    args+=(--undo) ;;
  *) echo "row_group_must_be_empty_or_undo" >&2; exit 2 ;;
esac
