#!/usr/bin/env bash
# Fixed official source, tenant, semester and target; no caller IDs or SQL.
# shellcheck disable=SC2154
case "$ORG" in qku|526cfa63-4f80-4bba-a7a7-61c8fbb3d918) ;; *) echo "fixed_tenant_required" >&2; exit 2 ;; esac
test "$YEAR" = "2026/2027" || { echo "fixed_year_required" >&2; exit 2; }
match "$ROSTER_TAG" '^biostat-kind-share-[0-9a-z-]+$' || { echo "reviewed_source_tag_required" >&2; exit 2; }
test "$BATCH" = "209dfa543720f11421a5aab910318e193e49799b2cf98b8fc27f5ed885fb5b16" || { echo "pinned_source_sha_required" >&2; exit 2; }
actor="$(superadmin_actor)"; test -n "$actor" || { echo "active_superadmin_required" >&2; exit 2; }
echo "::add-mask::$actor"
args=(--org "$ORG" --actor "$actor" --file "/tmp/biostat_source_${GITHUB_RUN_ID}.xlsx" --sha256 "$BATCH")
case "$ROW_GROUP" in
  "") ;;
  undo) args+=(--undo) ;;
  *) echo "undo_selector_invalid" >&2; exit 2 ;;
esac
if [ -n "$ROW_SUBJECT" ]; then
  match "$ROW_SUBJECT" '^[0-9a-f]{64}$' || { echo "baseline_sha_required" >&2; exit 2; }
  args+=(--baseline "$ROW_SUBJECT")
else
  test "$APPLY" != "true" || { echo "fresh_baseline_required" >&2; exit 2; }
fi
