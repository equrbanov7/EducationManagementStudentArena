"""Fixed metadata-only structure diagnostics; importable by the host without Django.

Model/table pairs are pinned from the app registry. Runtime SQL text and params
are never retained or emitted. Model means the most recent recognized SELECT,
not proof that a later Python failure was caused by that model.
"""

import re

FORMAT = "reaudit-structure-error/1"
PREFIX = "reaudit_structure_error: "
MODEL_TABLES = {
    "accounts.AcademicProfileItem": "accounts_academicprofileitem",
    "accounts.AccountActivationEvidence": "accounts_accountactivationevidence",
    "accounts.AccountRestoreEvidence": "accounts_accountrestoreevidence",
    "accounts.EmailOTP": "accounts_emailotp",
    "accounts.RuntimeSetting": "accounts_runtimesetting",
    "accounts.TeachingPayRate": "accounts_teachingpayrate",
    "accounts.UserProfile": "accounts_userprofile",
    "admin.LogEntry": "django_admin_log",
    "ai_assistant.AIAssistantLog": "ai_assistant_aiassistantlog",
    "announcements.Announcement": "announcements_announcement",
    "announcements.AnnouncementAttachment": "announcements_announcementattachment",
    "announcements.AnnouncementReceipt": "announcements_announcementreceipt",
    "appeals.AnswerKeyCorrection": "appeals_answerkeycorrection",
    "appeals.Appeal": "appeals_appeal",
    "appeals.AppealDecisionRecord": "appeals_appealdecisionrecord",
    "appeals.AppealItem": "appeals_appealitem",
    "appeals.KeyCorrectionCredit": "appeals_keycorrectioncredit",
    "appeals.ScoreAdjustment": "appeals_scoreadjustment",
    "applications.Application": "applications_application",
    "applications.ApplicationAttachment": "applications_applicationattachment",
    "applications.ApplicationContentRevision": "applications_applicationcontentrevision",
    "applications.ApplicationCounter": "applications_applicationcounter",
    "applications.ApplicationEvent": "applications_applicationevent",
    "applications.ApplicationKind": "applications_applicationkind",
    "applications.ApplicationUnit": "applications_applicationunit",
    "applications.ApplicationWatch": "applications_applicationwatch",
    "assignments.Assignment": "assignments_assignment",
    "assignments.Assignment_assigned_students": "assignments_assignment_assigned_students",
    "assignments.Notification": "assignments_notification",
    "assignments.Submission": "assignments_submission",
    "audit.AuditLog": "audit_auditlog",
    "auth.Group": "auth_group",
    "auth.Group_permissions": "auth_group_permissions",
    "auth.Permission": "auth_permission",
    "auth.User": "auth_user",
    "auth.User_groups": "auth_user_groups",
    "auth.User_user_permissions": "auth_user_user_permissions",
    "blog.Category": "blog_category",
    "blog.Comment": "blog_comment",
    "blog.Post": "blog_post",
    "blog.PostApprovalLog": "blog_postapprovallog",
    "blog.Question": "blog_question",
    "blog.Question_visible_users": "blog_question_visible_users",
    "blog.Subscriber": "blog_subscriber",
    "contact.ContactMessage": "contact_contactmessage",
    "contenttypes.ContentType": "django_content_type",
    "courses.Course": "courses_course",
    "courses.CourseGroup": "courses_coursegroup",
    "courses.CourseGroup_members": "courses_coursegroup_members",
    "courses.CourseInstructor": "courses_courseinstructor",
    "courses.CourseMembership": "courses_coursemembership",
    "courses.CourseResource": "courses_courseresource",
    "courses.CourseTopic": "courses_coursetopic",
    "exams.AIConfiguration": "exams_aiconfiguration",
    "exams.BankQuestion": "exams_bankquestion",
    "exams.BankQuestionOption": "exams_bankquestionoption",
    "exams.CodingExamQuestion": "exams_codingexamquestion",
    "exams.CodingFile": "exams_codingfile",
    "exams.CodingSubmission": "exams_codingsubmission",
    "exams.CodingTestCase": "exams_codingtestcase",
    "exams.Exam": "exams_exam",
    "exams.ExamAnswer": "exams_examanswer",
    "exams.ExamAnswerFile": "exams_examanswerfile",
    "exams.ExamAnswer_selected_options": "exams_examanswer_selected_options",
    "exams.ExamAttempt": "exams_examattempt",
    "exams.ExamGradeEvent": "exams_examgradeevent",
    "exams.ExamLanguageVariant": "exams_examlanguagevariant",
    "exams.ExamQuestion": "exams_examquestion",
    "exams.ExamQuestionOption": "exams_examquestionoption",
    "exams.ExamRoom": "exams_examroom",
    "exams.ExamRoomComputer": "exams_examroomcomputer",
    "exams.ExamRoomSession": "exams_examroomsession",
    "exams.ExamRoomSession_staff": "exams_examroomsession_staff",
    "exams.ExamRoom_invigilators": "exams_examroom_invigilators",
    "exams.ExamStudentPin": "exams_examstudentpin",
    "exams.ExamSupervisionConfig": "exams_examsupervisionconfig",
    "exams.Exam_allowed_groups": "exams_exam_allowed_groups",
    "exams.Exam_allowed_units": "exams_exam_allowed_units",
    "exams.Exam_allowed_users": "exams_exam_allowed_users",
    "exams.Exam_excluded_users": "exams_exam_excluded_users",
    "exams.Exam_journal_offerings": "exams_exam_journal_offerings",
    "exams.FinalAttemptDevice": "exams_finalattemptdevice",
    "exams.FinalExamTicket": "exams_finalexamticket",
    "exams.InvigilatorDuty": "exams_invigilatorduty",
    "exams.ProctoringLog": "exams_proctoringlog",
    "exams.QuestionBank": "exams_questionbank",
    "exams.QuestionBlock": "exams_questionblock",
    "exams.QuestionSubmission": "exams_questionsubmission",
    "exams.QuestionSubmissionEvent": "exams_questionsubmissionevent",
    "exams.QuestionSubmission_registry_groups": "exams_questionsubmission_registry_groups",
    "exams.QuestionSubmission_student_groups": "exams_questionsubmission_student_groups",
    "exams.StudentExamAttemptGrant": "exams_studentexamattemptgrant",
    "exams.StudentGroup": "exams_studentgroup",
    "exams.StudentGroup_students": "exams_studentgroup_students",
    "exams.StudentGroup_subjects": "exams_studentgroup_subjects",
    "exams.StudentGroup_teachers": "exams_studentgroup_teachers",
    "exams.SupervisionIncident": "exams_supervisionincident",
    "exams.TextExtractionJob": "exams_textextractionjob",
    "hr_contracts.EmploymentContract": "hr_contracts_employmentcontract",
    "hr_contracts.EmploymentContractEvent": "hr_contracts_employmentcontractevent",
    "labs.Lab": "labs_lab",
    "labs.LabAnswer": "labs_labanswer",
    "labs.LabAssignment": "labs_labassignment",
    "labs.LabAssignment_assigned_questions": "labs_labassignment_assigned_questions",
    "labs.LabBlock": "labs_labblock",
    "labs.LabQuestion": "labs_labquestion",
    "labs.LabSubmission": "labs_labsubmission",
    "labs.Lab_allowed_students": "labs_lab_allowed_students",
    "legacy_import.LegacyEntityMap": "legacy_import_legacyentitymap",
    "legacy_import.LegacyEntityMapVersion": "legacy_import_legacyentitymapversion",
    "legacy_import.LegacyEntityObservation": "legacy_import_legacyentityobservation",
    "legacy_import.LegacyImportBatch": "legacy_import_legacyimportbatch",
    "legacy_import.LegacyMigrationIssue": "legacy_import_legacymigrationissue",
    "legacy_import.LegacyMigrationRun": "legacy_import_legacymigrationrun",
    "live_exam.LiveAnswer": "live_exam_liveanswer",
    "live_exam.LivePlayer": "live_exam_liveplayer",
    "live_exam.LiveSession": "live_exam_livesession",
    "monitoring.Incident": "monitoring_incident",
    "monitoring.SecurityEvent": "monitoring_securityevent",
    "notifications.InAppNotification": "notifications_inappnotification",
    "notifications.PushDevice": "notifications_pushdevice",
    "notifications.StudentOrganizationRequest": "notifications_studentorganizationrequest",
    "organizations.AcademicHoliday": "organizations_academicholiday",
    "organizations.AcademicPeriod": "organizations_academicperiod",
    "organizations.Country": "organizations_country",
    "organizations.Institution": "organizations_institution",
    "organizations.Membership": "organizations_membership",
    "organizations.OrgUnit": "organizations_orgunit",
    "organizations.Organization": "organizations_organization",
    "organizations.Role": "organizations_role",
    "projects.Project": "projects_project",
    "projects.ProjectSubmission": "projects_projectsubmission",
    "projects.Project_assigned_students": "projects_project_assigned_students",
    "registrar.AbsenceCredit": "registrar_absencecredit",
    "registrar.AssessmentComponent": "registrar_assessmentcomponent",
    "registrar.AssessmentScheme": "registrar_assessmentscheme",
    "registrar.ComponentScore": "registrar_componentscore",
    "registrar.ComponentScoreCorrection": "registrar_componentscorecorrection",
    "registrar.CorrectionReversal": "registrar_correctionreversal",
    "registrar.CourseOffering": "registrar_courseoffering",
    "registrar.CourseWork": "registrar_coursework",
    "registrar.CourseWorkCorrection": "registrar_courseworkcorrection",
    "registrar.CriterionScore": "registrar_criterionscore",
    "registrar.Curriculum": "registrar_curriculum",
    "registrar.CurriculumSubject": "registrar_curriculumsubject",
    "registrar.Enrollment": "registrar_enrollment",
    "registrar.ExamChanceGrant": "registrar_examchancegrant",
    "registrar.ExamScoreEntry": "registrar_examscoreentry",
    "registrar.ExamScoreSheet": "registrar_examscoresheet",
    "registrar.ExternalCreditRecognition": "registrar_externalcreditrecognition",
    "registrar.FinalGrade": "registrar_finalgrade",
    "registrar.GroupElectiveChoice": "registrar_groupelectivechoice",
    "registrar.GroupTransferEvidence": "registrar_grouptransferevidence",
    "registrar.GuestRosterDocument": "registrar_guestrosterdocument",
    "registrar.JournalCloseNotice": "registrar_journalclosenotice",
    "registrar.JournalCorrection": "registrar_journalcorrection",
    "registrar.JournalHygieneDecision": "registrar_journalhygienedecision",
    "registrar.JournalRemoval": "registrar_journalremoval",
    "registrar.JournalShare": "registrar_journalshare",
    "registrar.JournalShare_enrollments": "registrar_journalshare_enrollments",
    "registrar.KollokviumExtraGrant": "registrar_kollokviumextragrant",
    "registrar.KollokviumWindow": "registrar_kollokviumwindow",
    "registrar.LabGroup": "registrar_labgroup",
    "registrar.LanguageLevelCohort": "registrar_languagelevelcohort",
    "registrar.LanguageLevelPlacement": "registrar_languagelevelplacement",
    "registrar.LegacyExcuseDocument": "registrar_legacyexcusedocument",
    "registrar.LegacyGradeArtifact": "registrar_legacygradeartifact",
    "registrar.LegacyGradeFact": "registrar_legacygradefact",
    "registrar.LegacyGradeReview": "registrar_legacygradereview",
    "registrar.Lesson": "registrar_lesson",
    "registrar.LessonCorrection": "registrar_lessoncorrection",
    "registrar.LessonMark": "registrar_lessonmark",
    "registrar.Program": "registrar_program",
    "registrar.ResitRecord": "registrar_resitrecord",
    "registrar.RetakeApplication": "registrar_retakeapplication",
    "registrar.RetakeApplicationEvent": "registrar_retakeapplicationevent",
    "registrar.RetakeReceipt": "registrar_retakereceipt",
    "registrar.RetakeTuition": "registrar_retaketuition",
    "registrar.RetakeWindow": "registrar_retakewindow",
    "registrar.Rubric": "registrar_rubric",
    "registrar.RubricCriterion": "registrar_rubriccriterion",
    "registrar.ScheduleSlot": "registrar_scheduleslot",
    "registrar.SelfWorkCorrection": "registrar_selfworkcorrection",
    "registrar.SelfWorkMark": "registrar_selfworkmark",
    "registrar.SelfWorkTopic": "registrar_selfworktopic",
    "registrar.SeminarGroup": "registrar_seminargroup",
    "registrar.StudentAcademicRecord": "registrar_studentacademicrecord",
    "registrar.StudentMovement": "registrar_studentmovement",
    "registrar.SubgroupPlacementEvent": "registrar_subgroupplacementevent",
    "registrar.Subject": "registrar_subject",
    "registrar.TeachingHandover": "registrar_teachinghandover",
    "sessions.Session": "django_session",
    "subject_folder.FolderAssignment": "subject_folder_folderassignment",
    "subject_folder.FolderMaterial": "subject_folder_foldermaterial",
    "subject_folder.FolderTask": "subject_folder_foldertask",
    "subject_folder.FolderTopic": "subject_folder_foldertopic",
    "subject_folder.SimilarityMatch": "subject_folder_similaritymatch",
    "subject_folder.SubjectFolder": "subject_folder_subjectfolder",
    "subject_folder.Submission": "subject_folder_submission",
    "subject_folder.SubmissionEvent": "subject_folder_submissionevent",
    "subject_folder.SubmissionFile": "subject_folder_submissionfile",
    "subject_folder.SubmissionFingerprint": "subject_folder_submissionfingerprint",
    "subject_folder.TaskAttachment": "subject_folder_taskattachment",
    "subject_folder.TaskDeadline": "subject_folder_taskdeadline",
    "surveys.Survey": "surveys_survey",
    "surveys.SurveyAnswer": "surveys_surveyanswer",
    "surveys.SurveyCampaign": "surveys_surveycampaign",
    "surveys.SurveyDraft": "surveys_surveydraft",
    "surveys.SurveyGateSkip": "surveys_surveygateskip",
    "surveys.SurveyPage": "surveys_surveypage",
    "surveys.SurveyParticipation": "surveys_surveyparticipation",
    "surveys.SurveyPendingResponse": "surveys_surveypendingresponse",
    "surveys.SurveyPendingSubmission": "surveys_surveypendingsubmission",
    "surveys.SurveyQuestion": "surveys_surveyquestion",
    "surveys.SurveyReceipt": "surveys_surveyreceipt",
    "surveys.SurveyResponse": "surveys_surveyresponse",
    "surveys.SurveySubmission": "surveys_surveysubmission",
    "surveys.SurveySubmissionAnswer": "surveys_surveysubmissionanswer",
    "surveys.SurveyTemplate": "surveys_surveytemplate",
    "syllabus.Syllabus": "syllabus_syllabus",
    "syllabus.SyllabusReview": "syllabus_syllabusreview",
    "syllabus.SyllabusSection": "syllabus_syllabussection",
    "syllabus.SyllabusShare": "syllabus_syllabusshare",
    "syllabus.SyllabusVersion": "syllabus_syllabusversion",
    "timetable.GroupTimePolicy": "timetable_grouptimepolicy",
    "timetable.TeacherAvailability": "timetable_teacheravailability",
    "timetable.TimetableDraftSlot": "timetable_timetabledraftslot",
    "timetable.TimetableRun": "timetable_timetablerun",
    "trial_exams.TrialExamRequest": "trial_exams_trialexamrequest",
    "verification.DocumentSeal": "verification_documentseal",
    "workload.LoadObjection": "workload_loadobjection",
    "workload.TaskFacultySlice": "workload_taskfacultyslice",
    "workload.TaskRowReview": "workload_taskrowreview",
    "workload.TeacherAssignment": "workload_teacherassignment",
    "workload.TeacherWorkloadProfile": "workload_teacherworkloadprofile",
    "workload.TeachingTask": "workload_teachingtask",
    "workload.TeachingTaskRow": "workload_teachingtaskrow",
    "workload.TeachingTaskRow_groups": "workload_teachingtaskrow_groups",
    "workload.WorkloadAmendment": "workload_workloadamendment",
}
CODES = frozenset(
    {
        "reviewed_graph_budget",
        "reviewed_graph_postgresql_required",
        "reviewed_graph_tenant_changed",
        "structure_active_courses",
        "structure_active_superuser",
        "structure_active_tenant",
        "structure_actor_profile",
        "structure_actor_tenant",
        "structure_authority_required",
        "structure_cache_reaches_active_target",
        "structure_cache_target_now_active",
        "structure_cache_undo_count",
        "structure_canonical_counter_mismatch",
        "structure_course_budget",
        "structure_course_period",
        "structure_current_unlocked_period",
        "structure_duplicate_candidate_changed",
        "structure_duplicate_reference_changed",
        "structure_exact_parking_receipt_required",
        "structure_exact_receipt_required",
        "structure_existing_lesson_correction_review",
        "structure_explicit_apply",
        "structure_family_budget",
        "structure_file_changed",
        "structure_file_sha_required",
        "structure_fresh_baseline_required",
        "structure_graph_cross_course_history",
        "structure_half_pair_fixed_source",
        "structure_conflict_authority",
        "structure_conflict_map_budget",
        "structure_conflict_mark_changed",
        "structure_conflict_grade_or_attendance",
        "structure_conflict_scope",
        "structure_conflict_source",
        "structure_conflict_mapping",
        "structure_conflict_target_changed",
        "structure_conflict_formal_history",
        "structure_conflict_reversal",
        "structure_conflict_postcondition",
        "structure_conflict_counter_forecast",
        "structure_half_pair_hours_changed",
        "structure_half_pair_identity_changed",
        "structure_half_pair_missing",
        "structure_half_pair_reviewed_marks_changed",
        "structure_history_outside_family",
        "structure_incoming_history_outside_family",
        "structure_invalid_history",
        "structure_lesson_reversal_refused",
        "structure_manifest_schema",
        "structure_manifest_tenant_period",
        "structure_mark_enrollment_tenant",
        "structure_mark_reference_conflict",
        "structure_operation",
        "structure_parking_geometry_changed",
        "structure_parking_offering_now_active_or_deleted",
        "structure_parking_slot_missing",
        "structure_parking_state_changed",
        "structure_parking_write_count",
        "structure_post_apply_graph_changed",
        "structure_private_file_required",
        "structure_protected_graph_changed",
        "structure_refused",
        "structure_reviewed_source_authority_required",
        "structure_scope_changed",
        "structure_target_budget",
        "structure_target_ids",
        "structure_target_missing",
        "structure_timetable_fact_budget",
        "structure_timetable_off_schedule_requires_review",
        "structure_timetable_slot_budget",
        "structure_undone_requires_review",
        "structure_unreviewed_cache_target",
        "structure_unreviewed_slot_target",
    }
)
PHASES = frozenset({"manifest", "authority", "actor", "rls", "organization", "repair", "reset_rls"})
OPERATIONS = frozenset({"half_pair", "inactive_cache", "timetable", "park_inactive_slots", "owner_present_conflict"})
EXCEPTIONS = frozenset(
    {
        "Exception",
        "ValueError",
        "TypeError",
        "RuntimeError",
        "OSError",
        "FileNotFoundError",
        "PermissionError",
        "MemoryError",
        "OverflowError",
        "DatabaseError",
        "OperationalError",
        "ProgrammingError",
        "IntegrityError",
        "DataError",
        "InterfaceError",
        "NotSupportedError",
        "InternalError",
        "TransactionManagementError",
        "ImproperlyConfigured",
        "ValidationError",
    }
)
KEYS = frozenset({"format", "phase", "operation", "model", "table", "code", "exception", "sqlstate"})
_SQLSTATE = re.compile(r"[0-9A-Z]{5}")
_TABLE = re.compile(r'\b(?:FROM|JOIN)\s+(?:"?public"?\.)?"?([a-zA-Z_][a-zA-Z0-9_]*)"?', re.IGNORECASE)
_TABLE_MODELS = {table: label for label, table in sorted(MODEL_TABLES.items(), reverse=True)}


def _sqlstate(exc):
    seen = set()
    for _ in range(4):
        if not isinstance(exc, BaseException) or id(exc) in seen:
            break
        seen.add(id(exc))
        for name in ("sqlstate", "pgcode"):
            try:
                value = getattr(exc, name, None)
            except Exception:
                continue
            if isinstance(value, str) and _SQLSTATE.fullmatch(value):
                return value
        exc = exc.__cause__
    return None


def validate(value):
    """Host must reject unknown fields/values, including a mismatched registry pair."""
    if not (
        isinstance(value, dict)
        and set(value) == KEYS
        and value["format"] == FORMAT
        and isinstance(value["phase"], str)
        and value["phase"] in PHASES
        and (value["operation"] is None or isinstance(value["operation"], str) and value["operation"] in OPERATIONS)
        and (
            (value["model"] is None and value["table"] is None)
            or isinstance(value["model"], str)
            and isinstance(value["table"], str)
            and MODEL_TABLES.get(value["model"]) == value["table"]
        )
        and isinstance(value["code"], str)
        and value["code"] in CODES
        and isinstance(value["exception"], str)
        and value["exception"] in EXCEPTIONS
        and (
            value["sqlstate"] is None
            or isinstance(value["sqlstate"], str)
            and bool(_SQLSTATE.fullmatch(value["sqlstate"]))
        )
    ):
        raise ValueError("structure_diagnostic_invalid")
    return {
        key: value[key] for key in ("format", "phase", "operation", "model", "table", "code", "exception", "sqlstate")
    }


class QueryTrace:
    def __init__(self):
        self.phase = "manifest"
        self.operation = None
        self.model = self.table = None
        self.first_failure = None
        self.query_failure = None
        self.query_failure_ids = set()
        self._query_exception = None  # Keep identity alive; never inspect/render its text.

    def __call__(self, execute, sql, params, many, context):
        # Only known SELECT identifiers enter state. Never retain sql or params.
        if isinstance(sql, str) and sql.lstrip().upper().startswith(("SELECT", "WITH")):
            self.model = self.table = None
            for match in _TABLE.finditer(sql):
                table = match.group(1)
                if table in _TABLE_MODELS:
                    self.table, self.model = table, _TABLE_MODELS[table]
                    break
        try:
            return execute(sql, params, many, context)
        except Exception as exc:
            self._query_exception = exc
            self.query_failure = self._payload(exc)
            self.query_failure_ids = self._exception_ids(exc)
            raise

    @staticmethod
    def _exception_ids(exc):
        ids = set()
        for _ in range(4):
            if not isinstance(exc, BaseException) or id(exc) in ids:
                break
            ids.add(id(exc))
            exc = exc.__cause__
        return ids

    def _payload(self, exc):
        raw_code = exc.args[0] if len(exc.args) == 1 and isinstance(exc.args[0], str) else None
        name = type(exc).__name__
        result = {
            "format": FORMAT,
            "phase": self.phase if self.phase in PHASES else "manifest",
            "operation": self.operation if self.operation in OPERATIONS else None,
            "model": self.model,
            "table": self.table,
            "code": raw_code if raw_code in CODES else "structure_refused",
            "exception": name if name in EXCEPTIONS else "Exception",
            "sqlstate": _sqlstate(exc),
        }
        return validate(result)

    def capture(self, exc):
        if self.first_failure is not None:
            return self.first_failure
        self.first_failure = (
            self.query_failure if self._exception_ids(exc) & self.query_failure_ids else self._payload(exc)
        )
        return self.first_failure
