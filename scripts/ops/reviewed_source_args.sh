#!/usr/bin/env bash
# Sourced API for guarded encrypted source manifests.
# shellcheck disable=SC2154
if [ "${COMMAND:-}" = repair_reviewed_journal_content ]; then
  source scripts/ops/reviewed_content_args.sh
  return
fi
if [[ "$COMMAND" = repair_tspx_legacy_roster || "$COMMAND" = repair_si135_legacy_roster || "$COMMAND" = repair_bi_mu536_legacy_roster ]]; then
  case "$COMMAND" in
    repair_tspx_legacy_roster) roster_prefix=tspx-roster; roster_file=tspx_roster ;;
    repair_si135_legacy_roster) roster_prefix=si135-roster; roster_file=si135_roster ;;
    repair_bi_mu536_legacy_roster) roster_prefix=bimu536-roster; roster_file=bi_mu536_roster ;;
  esac
  match "$ROSTER_TAG" "^${roster_prefix}-[0-9a-z-]+$" || exit 2
  match "$BATCH" '^[0-9a-f]{64}$' || exit 2
  args=(--org "$ORG" --actor "$actor" --manifest "/tmp/${roster_file}_${GITHUB_RUN_ID}.json" --manifest-sha256 "$BATCH")
  undo_prefix="$roster_prefix"
else
match "$ROSTER_TAG" '^reviewed-workload-[0-9a-z-]+$' || exit 2
match "$BATCH" '^[0-9a-f]{64}$' || exit 2
match "$ROW_GROUP" '^[1-9][0-9]*(,[1-9][0-9]*)*$' || { echo "explicit_source_lines_required" >&2; exit 2; }
IFS=, read -r -a source_lines <<< "$ROW_GROUP"
args=(--org "$ORG" --actor "$actor" --manifest "/tmp/reviewed_source_${GITHUB_RUN_ID}.json" --manifest-sha256 "$BATCH" --lines "${source_lines[@]}")
  undo_prefix=source
fi
if [[ "$ROW_SUBJECT" == "$undo_prefix"-* ]]; then
  undo_batch="${ROW_SUBJECT%%:*}"
  match "$undo_batch" "^${undo_prefix}-[0-9]{8}-[0-9]{6}-[0-9a-f]{8}$" || exit 2
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
