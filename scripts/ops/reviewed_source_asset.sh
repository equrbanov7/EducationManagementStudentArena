#!/usr/bin/env bash
# Sourced API: asset and target are returned to the download step.
# shellcheck disable=SC2034
# Sourced inside the encrypted download step; emits no plaintext or secret.
case "$COMMAND" in
  recover_mr46_syllabus)
    tag_prefix=mr46-syllabus; asset=mr46-syllabus.json.enc; target="/tmp/mr46_syllabus_${GITHUB_RUN_ID}.json" ;;
  recover_mr27_journal)
    tag_prefix=mr27-recovery; asset=mr27-recovery.json.enc; target="/tmp/mr27_recovery_${GITHUB_RUN_ID}.json" ;;
  repair_qosqar_modelling|repair_qosqar_journals)
    tag_prefix=qosqar-modelling; asset=source-evidence.json.enc; target="/tmp/qosqar_modelling_${GITHUB_RUN_ID}.json" ;;
  repair_biostat_seminar_share)
    tag_prefix=biostat-kind-share; asset=biostat.xlsx.enc; target="/tmp/biostat_source_${GITHUB_RUN_ID}.xlsx" ;;
  repair_it8179_load)
    tag_prefix=it8179-source; asset=official-source.docx.enc; target="/tmp/it8179_source_${GITHUB_RUN_ID}.docx" ;;
  repair_applied_math_journal)
    tag_prefix=applied-math-source; asset=applied-math-source.json.enc; target="/tmp/applied_math_source_${GITHUB_RUN_ID}.json" ;;
  recover_named_workload_syllabi)
    tag_prefix=named-workload-syllabi; asset=named-workload-syllabi.json.enc; target="/tmp/named_workload_syllabi_${GITHUB_RUN_ID}.json" ;;
  recover_genetics_workload_syllabus)
    tag_prefix=genetics-workload-syllabus; asset=genetics-workload-syllabus.json.enc; target="/tmp/genetics_workload_syllabus_${GITHUB_RUN_ID}.json" ;;
  recover_empty_workload_syllabi)
    tag_prefix=empty-workload-syllabi; asset=empty-workload-syllabi.json.enc; target="/tmp/empty_workload_syllabi_${GITHUB_RUN_ID}.json" ;;
  recover_six_workload_syllabi)
    tag_prefix=six-workload-syllabi; asset=six-workload-syllabi.json.enc; target="/tmp/six_workload_syllabi_${GITHUB_RUN_ID}.json" ;;
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

if [ "$COMMAND" = "repair_biostat_seminar_share" ]; then
  test "$BATCH" = "209dfa543720f11421a5aab910318e193e49799b2cf98b8fc27f5ed885fb5b16" || { echo "pinned_source_sha_required" >&2; exit 2; }
fi
