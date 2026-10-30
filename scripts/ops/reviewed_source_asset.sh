#!/usr/bin/env bash
# Sourced API: asset and target are returned to the download step.
# shellcheck disable=SC2034
# Sourced inside the encrypted download step; emits no plaintext or secret.
case "$COMMAND" in
  recover_mr46_syllabus)
    tag_prefix=mr46-syllabus; asset=mr46-syllabus.json.enc; target="/tmp/mr46_syllabus_${GITHUB_RUN_ID}.json" ;;
  recover_mr27_journal)
    tag_prefix=mr27-recovery; asset=mr27-recovery.json.enc; target="/tmp/mr27_recovery_${GITHUB_RUN_ID}.json" ;;
  recover_workload_syllabi)
    tag_prefix=workload-syllabi; asset=workload-syllabi.json.enc; target="/tmp/workload_syllabi_${GITHUB_RUN_ID}.json" ;;
  repair_bi_mu536_legacy_roster)
    tag_prefix=bimu536-roster; asset=bimu536-roster.json.enc; target="/tmp/bi_mu536_roster_${GITHUB_RUN_ID}.json" ;;
  repair_si135_legacy_roster)
    tag_prefix=si135-roster; asset=si135-roster.json.enc; target="/tmp/si135_roster_${GITHUB_RUN_ID}.json" ;;
  repair_tspx_legacy_roster)
    tag_prefix=tspx-roster; asset=tspx-roster.json.enc; target="/tmp/tspx_roster_${GITHUB_RUN_ID}.json" ;;
  repair_reviewed_journal_content)
    tag_prefix=reviewed-content; asset=reviewed-content.json.enc; target="/tmp/reviewed_content_${GITHUB_RUN_ID}.json" ;;
  repair_reviewed_workload_batch)
    tag_prefix=reviewed-workload; asset=reviewed-workload.json.enc; target="/tmp/reviewed_source_${GITHUB_RUN_ID}.json" ;;
  *) echo "encrypted_source_command_not_allowed" >&2; exit 2 ;;
esac
match "$ROSTER_TAG" "^${tag_prefix}-[0-9a-z-]+$" || { echo "encrypted_source_tag_invalid" >&2; exit 2; }
match "$BATCH" '^[0-9a-f]{64}$' || { echo "plaintext_manifest_sha256_required" >&2; exit 2; }
