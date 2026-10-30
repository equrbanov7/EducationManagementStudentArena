#!/usr/bin/env bash
# Sourced by the Prod Data Ops allowlist after the active actor is selected.
args=(--org "$ORG" --actor "$actor" --source-sha256 c41ed24dde58360c1f9925ec50b355c14230a36add34a1480d416590c6caab56)
test -z "$ROSTER_TAG" || { echo "sabit scope üçün roster_tag boş olmalıdır" >&2; exit 2; }
if [[ "$BATCH" == ke233-* ]]; then
  undo_batch="${BATCH%%:*}"
  match "$undo_batch" '^ke233-[0-9]{8}-[0-9]{6}-[0-9a-f]{4}$' || exit 2
  args+=(--undo "$undo_batch")
  if [[ "$BATCH" == *:* ]]; then
    baseline="${BATCH#*:}"
    match "$baseline" '^[0-9a-f]{64}$' || exit 2
    args+=(--expected-baseline "$baseline")
  else
    test "$APPLY" != "true" || { echo "undo apply üçün batch=undoID:baselineSHA verin" >&2; exit 2; }
  fi
elif [ -n "$BATCH" ]; then
  match "$BATCH" '^[0-9a-f]{64}$' || exit 2
  args+=(--expected-baseline "$BATCH")
else
  test "$APPLY" != "true" || { echo "apply üçün batch=dry-run baselineSHA verin" >&2; exit 2; }
fi
