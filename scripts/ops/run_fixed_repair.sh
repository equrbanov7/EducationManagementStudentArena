#!/usr/bin/env bash
# No raw command output reaches the public log; backup and apply confirmation stay in the caller.
set -euo pipefail
umask 077
case "$COMMAND" in
  repair_sbio235_workload) prefix=sbio_repair; batch_prefix=sbio235 ;;
  repair_233ke_group_alias) prefix=ke233_alias; batch_prefix=ke233 ;;
  repair_cavid_source_batch) prefix=cavid3536; batch_prefix=cavid3536 ;;
  repair_bi_mu536_legacy_roster) prefix=bi_mu536_roster; batch_prefix=bimu536-roster ;;
  repair_si135_legacy_roster) prefix=si135_roster; batch_prefix=si135-roster ;;
  repair_tspx_legacy_roster) prefix=tspx_roster; batch_prefix=tspx-roster ;;
  repair_reviewed_workload_batch) prefix=reviewed_source; batch_prefix=source ;;
  repair_reviewed_journal_content) prefix=reviewed_content; batch_prefix=content ;;
  *) echo "fixed_repair_command_not_allowed" >&2; exit 2 ;;
esac
batch_length=4
if [[ "$COMMAND" = repair_reviewed_workload_batch || "$COMMAND" = repair_reviewed_journal_content || "$COMMAND" = repair_tspx_legacy_roster || "$COMMAND" = repair_si135_legacy_roster || "$COMMAND" = repair_bi_mu536_legacy_roster ]]; then batch_length=8; fi
output="$RUNNER_TEMP/out.log"
summary="$RUNNER_TEMP/summary.log"
status=0
# The Python wrapper configures only this invocation and verifies its actual
# transaction view before dispatch, including through PgBouncer.
docker exec -i "$APP_CONTAINER" python - "$COMMAND" "$@" < scripts/ops/run_guarded_repair.py > "$output" 2>&1 || status=$?
grep -E '^fixed_repair: transaction_isolation=repeatable_read$' "$output" || true
grep -E "^${prefix}: mode=(dry_run|apply|undo)( (baseline=[0-9a-f]{64}|batch=${batch_prefix}-[0-9]{8}-[0-9]{6}-[0-9a-f]{${batch_length}}|[a-z_]+=[0-9]+))+$" "$output" > "$summary" || true
cat "$summary"
if [ "$status" != 0 ]; then
  model='registrar[.](CourseOffering|Lesson|Enrollment|LessonMark|JournalShare|TeachingHandover|StudentAcademicRecord)|organizations[.](Membership|Role)|syllabus[.](Syllabus|SyllabusVersion|SyllabusSection|SyllabusReview)|SelfWorkTopic|SelfWorkMark|ComponentScore|CriterionScore|CourseWork|FinalGrade|ResitRecord|AssessmentScheme|AssessmentComponent|ScheduleSlot|outside_subjects|outside_workload_rows|outside_workload_assignments|outside_elective_choices'
  grep -E "^CommandError: ([a-z_]+|outside_academic_work_or_access_changed:($model)(,($model))*)$" "$output" | head -n 1 || true
fi
rm -f "$output"
exit "$status"
