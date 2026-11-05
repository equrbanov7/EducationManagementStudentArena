"""Read-only final/appeal evidence, including historical finals, for the fixed audit.

The caller owns the tenant-scoped repeatable-read transaction and encryption.
No result calculation is allowed here: some result helpers expire old attempts.
"""


def collect_scores(*, read, model, data, organization_id, current_offering_ids):
    finals = read(
        "registrar.FinalGrade",
        "id enrollment_id exam_score bonus is_published entered_by_id created_at updated_at",
    )
    resits = read(
        "registrar.ResitRecord",
        "id enrollment_id reason status resit_score decided_by_id created_at updated_at",
    )
    entries = read(
        "registrar.ExamScoreEntry",
        "id enrollment_id kind assessment old_score new_score reason note evidence entered_by_id sheet_id question_scores created_at",
    )
    legacy = read(
        "registrar.LegacyGradeFact",
        "id enrollment_id source_system source_table source_pk source_snapshot_sha256 source_row_hash "
        "evidence_kind score_code is_archive mapping_status mapping_issue_code "
        "entry_score exam_score resit_score final_score legacy_kesr legacy_level legacy_attempt_type "
        "legacy_recorded_at_text requires_exam_center_review created_at",
    )
    read(
        "registrar.LegacyGradeReview",
        "id fact_id decision reason_code category_codes evidence_digest reviewed_by_id created_at",
    )
    history = read(
        "registrar.Enrollment",
        "id student_id offering_id status kind superseded_by_id absence_hours legacy_qb_fail created_at updated_at",
        key="final_enrollments",
        id__in={row["enrollment_id"] for row in finals + resits + entries + legacy if row["enrollment_id"]},
    )
    all_offerings = set(current_offering_ids) | {row["offering_id"] for row in history}
    read(
        "registrar.CourseOffering",
        "id subject_id period_id group_id instructor_id lesson_hours is_active course_format created_at updated_at",
        key="final_offerings",
        id__in=all_offerings,
    )
    read(
        "registrar.ExamScoreSheet",
        "id offering_id assessment source exam_kind exam_date checked_on "
        "question_count question_max question_maxes evidence created_at updated_at",
        id__in={row["sheet_id"] for row in entries if row["sheet_id"]},
    )
    read(
        "registrar.AssessmentScheme",
        "id offering_id entry_score_max pass_threshold min_final_exam_score is_published approval_status",
        offering_id__in=all_offerings,
    )
    read("registrar.AssessmentComponent", "id offering_id kind max_score name", offering_id__in=all_offerings)
    read(
        "registrar.ComponentScore",
        "id component_id enrollment_id score created_at updated_at",
        component__offering_id__in=all_offerings,
    )
    read("exams.Exam", "id title subject_id exam_type exam_type_extended created_at")
    data["exam_offerings"] = list(
        model("exams.Exam")
        .objects.filter(organization_id=organization_id)
        .order_by("id", "journal_offerings__id")
        .values("id", "journal_offerings__id")
    )
    read(
        "exams.ExamAttempt",
        "id user_id exam_id attempt_number is_trial status started_at finished_at correct_count wrong_count teacher_score teacher_checked_at",
        tenant_field="exam__organization_id",
    )
    read("appeals.Appeal", "id attempt_id exam_id student_id status reviewed_by_id reviewed_at created_at updated_at")
    read(
        "appeals.AppealItem",
        "id appeal_id question_id answer_id status resolved_by_id resolved_at decided_by_teacher_id",
        tenant_field="appeal__organization_id",
    )
    read(
        "appeals.ScoreAdjustment",
        "id appeal_item_id attempt_id question_id delta_points previous_score new_score applied_by_id applied_at reverted",
        tenant_field="attempt__exam__organization_id",
    )
    read(
        "appeals.AppealDecisionRecord",
        "id appeal_id decided_by_teacher_id saved_by_id item_ids accepted_count rejected_count score_before score_after document created_at",
    )
    read(
        "appeals.AnswerKeyCorrection",
        "id exam_id question_id source_item_id previous_option_ids corrected_option_ids created_by_id created_at affected_count credited_count revoked_at",
    )
    read(
        "appeals.KeyCorrectionCredit",
        "id correction_id attempt_id question_id delta_points previous_score new_score reverted created_at",
        tenant_field="correction__organization_id",
    )
    answers = read(
        "exams.ExamAnswer",
        "id attempt_id question_id is_correct teacher_score question_snapshot selected_option_ids_snapshot updated_at",
        tenant_field="attempt__exam__organization_id",
        limit=2000000,
    )
    question_ids = {row["question_id"] for row in answers}
    read(
        "exams.ExamQuestion",
        "id exam_id points",
        id__in=question_ids,
        tenant_field=("exam__organization_id", "bank__organization_id"),
    )
    read(
        "exams.ExamQuestionOption",
        "id question_id is_correct",
        tenant_field=("question__exam__organization_id", "question__bank__organization_id"),
        question_id__in=question_ids,
    )
    # None means the frozen selection does not exist; retain the live M2M fallback.
    data["legacy_answer_selections"] = list(
        model("exams.ExamAnswer")
        .objects.filter(
            attempt__exam__organization_id=organization_id,
            selected_option_ids_snapshot__isnull=True,
        )
        .order_by("id", "selected_options__id")
        .values("id", "selected_options__id")
    )
