#!/usr/bin/env bash
# Sourced by the ops dispatcher; only pinned encrypted evidence and fresh hashes.
# shellcheck disable=SC2154
match "$BATCH" '^[0-9a-f]{64}$' || { echo "source_sha_required" >&2; exit 2; }
actor="$(superadmin_actor)"; test -n "$actor" || exit 2
echo "::add-mask::$actor"
args=(--org "$ORG" --actor "$actor" --file "/tmp/it8179_source_${GITHUB_RUN_ID}.docx" --sha256 "$BATCH")
case "$ROW_GROUP" in
  "") ;;
  undo) args+=(--undo) ;;
  *) echo "undo_selector_invalid" >&2; exit 2 ;;
esac
if [ -n "$ROW_SUBJECT" ]; then
  match "$ROW_SUBJECT" '^[0-9a-f]{64}$' || exit 2
  args+=(--baseline "$ROW_SUBJECT")
else
  test "$APPLY" != "true" || { echo "fresh_baseline_required" >&2; exit 2; }
fi
