#!/usr/bin/env bash
# Approved fixed five-assignment identity bridge; no assets or scope selectors.
# shellcheck disable=SC2154
case "$ORG" in qku|526cfa63-4f80-4bba-a7a7-61c8fbb3d918) ;; *) echo "fixed_tenant_required" >&2; exit 2 ;; esac
test "$YEAR" = "2026/2027" || { echo "fixed_year_required" >&2; exit 2; }
test -z "$ROSTER_TAG" || { echo "unused_source_selector" >&2; exit 2; }
test -z "$ROW_GROUP" || { echo "unused_group_selector" >&2; exit 2; }
actor="$(superadmin_actor)"; test -n "$actor" || { echo "active_superadmin_required" >&2; exit 2; }
echo "::add-mask::$actor"
args=(--actor "$actor")
if [ -n "$BATCH" ]; then
  match "$BATCH" '^[0-9a-f]{64}$' || { echo "baseline_sha_required" >&2; exit 2; }
  args+=(--expected-baseline "$BATCH")
else
  test "$APPLY" != "true" || { echo "fresh_baseline_required" >&2; exit 2; }
fi
if [ -n "$ROW_SUBJECT" ]; then
  match "$ROW_SUBJECT" '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$' || { echo "undo_receipt_uuid_required" >&2; exit 2; }
  args+=(--undo "$ROW_SUBJECT")
fi
