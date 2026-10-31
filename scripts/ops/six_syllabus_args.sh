#!/usr/bin/env bash
# Sourced by the production ops dispatcher. No plaintext content output.
actor="$(superadmin_actor)"; test -n "$actor" || { echo "aktiv superadmin tapılmadı" >&2; exit 1; }
echo "::add-mask::$actor"
args=(--org "$ORG" --actor "$actor")
if [[ "$BATCH" == sixsyl-* ]]; then
  match "$BATCH" '^sixsyl-[0-9]{8}-[0-9]{6}-[0-9a-f]{4}$' || { echo "batch formatı: sixsyl-YYYYMMDD-HHMMSS-xxxx" >&2; exit 2; }
  test "$APPLY" = "true" || { echo "undo yazır — apply=true + confirm=APPLY verin" >&2; exit 2; }
  test -z "$ROSTER_TAG" || { echo "undo üçün roster_tag boş olmalıdır" >&2; exit 2; }
  args+=(--undo "$BATCH")
else
  match "$BATCH" '^[0-9a-f]{64}$' || { echo "batch = plaintext faylın sha256-sı (64 hex)" >&2; exit 2; }
  args+=(--file "/tmp/six_workload_syllabi_${GITHUB_RUN_ID}.json" --sha256 "$BATCH")
fi
