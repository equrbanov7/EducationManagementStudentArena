"""Müəllim birləşdirməsi — istifadəçiyə istinad edən HƏR sahənin AÇIQ siyasəti.

İstifadəçi modelinə yönələn bütün FK / O2O sahələri (M2M ara cədvəlləri də — onlar ``X_y.user`` FK-sı kimi görünür)
Django introspeksiyası ilə tapılır (:func:`relations`). Hər biri :data:`POLICY`-də AÇIQ təsnif olunmalıdır — təsnif
olunmamış sahə tapılsa əmr işləmir (``unclassified_relation``), yəni yeni model əlavə ediləndə səssizcə nəsə qaçmır.

Siyasətlər:

* ``repoint`` — sətir hədəf hesaba keçir (id-lər manifestdədir, ``undo`` geri qaytarır). Sahə unikal məhdudiyyətin
  (``UniqueConstraint`` / ``unique_together``, şərti də) içindədirsə, hədəfdə EYNİ açarlı sətir olan mənbə sətri
  toxunulmur və sayılır (``collision_<açar>``) — heç nə silinmir;
* ``membership`` — üzvlüklər (rollar) hədəfə verilir, mənbədə deaktiv olur (``apply._memberships``);
* ``share`` — bölünmüş jurnal payları birləşdirilir (``shares``);
* ``keep_personal`` — giriş / cihaz / şəxsi log: bloklanmış hesabda qalır, sayılır;
* ``keep_evidence`` — DB-də append-only / dəyişməz sübut (trigger UPDATE-i qadağan edir) və ya tarixi qeyd:
  qalır, sayılır;
* ``keep_student`` — tələbə tərəfi (mənbə tələbə ola bilməz — qapı; olsa belə qalır və sayılır);
* ``guard`` — mənbədə sətir varsa birləşdirmə dayanır (təşkilat sahibi).
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db.models import UniqueConstraint

REPOINT = "repoint"
MEMBERSHIP = "membership"
SHARE = "share"
KEEP_PERSONAL = "keep_personal"
KEEP_EVIDENCE = "keep_evidence"
KEEP_STUDENT = "keep_student"
GUARD = "guard"
KEEP = (KEEP_PERSONAL, KEEP_EVIDENCE, KEEP_STUDENT)

_REPOINT = (
    # accounts — müəllimin akademik profili (CV), aktor sahələri
    "accounts.AcademicProfileItem.user",
    "accounts.RuntimeSetting.updated_by",
    "accounts.UserProfile.blocked_by",
    "accounts.UserProfile.deleted_by",
    "accounts.UserProfile.fin_shared_with",  # eyni FİN-li bağlı hesab (shared_fin) — bağ saxlanılan hesaba keçir
    # announcements
    "announcements.Announcement.created_by",
    "announcements.Announcement.deleted_by",
    "announcements.Announcement.updated_by",
    "announcements.AnnouncementAttachment.uploaded_by",
    "announcements.AnnouncementReceipt.user",
    # appeals — müəllimin qərarları
    "appeals.AnswerKeyCorrection.created_by",
    "appeals.AnswerKeyCorrection.revoked_by",
    "appeals.Appeal.reviewed_by",
    "appeals.AppealDecisionRecord.decided_by_teacher",
    "appeals.AppealDecisionRecord.saved_by",
    "appeals.AppealItem.decided_by_teacher",
    "appeals.AppealItem.resolved_by",
    "appeals.ScoreAdjustment.applied_by",
    # applications (RİM müraciətləri)
    "applications.Application.assigned_to",
    "applications.Application.created_by",
    "applications.Application.deleted_by",
    "applications.ApplicationAttachment.uploaded_by",
    # assignments
    "assignments.Assignment.created_by",
    "assignments.Notification.user",
    "assignments.Submission.graded_by",
    # blog
    "blog.Comment.user",
    "blog.Post.approved_by",
    "blog.Post.author",
    "blog.PostApprovalLog.reviewer",
    "blog.Question.author",
    "blog.Question_visible_users.user",
    "contact.ContactMessage.reply_sent_by",
    # courses
    "courses.Course.owner",
    "courses.CourseGroup.instructor",
    "courses.CourseGroup_members.user",
    "courses.CourseInstructor.user",
    "courses.CourseMembership.user",
    # exams — müəllifliyi, nəzarət, sual bankı
    "exams.BankQuestion.created_by",
    "exams.Exam.author",
    "exams.Exam.journal_teacher",
    "exams.ExamAttempt.graded_by",
    "exams.ExamRoom.created_by",
    "exams.ExamRoom_invigilators.user",
    "exams.ExamRoomComputer.created_by",
    "exams.ExamRoomSession.created_by",
    "exams.ExamRoomSession.ended_by",
    "exams.ExamRoomSession.invigilator",
    "exams.ExamRoomSession.started_by",
    "exams.ExamRoomSession_staff.user",
    "exams.FinalAttemptDevice.change_approved_by",
    "exams.FinalExamTicket.pin_generated_by",
    "exams.FinalExamTicket.removed_by",
    "exams.InvigilatorDuty.assigned_by",
    "exams.InvigilatorDuty.revoked_by",
    "exams.InvigilatorDuty.user",
    "exams.QuestionBank.created_by",
    "exams.QuestionBank.source_teacher",
    "exams.QuestionSubmission.chair_reviewer",
    "exams.QuestionSubmission.reviewer",
    "exams.QuestionSubmission.teacher",
    "exams.StudentExamAttemptGrant.granted_by",
    "exams.StudentGroup.teacher",
    "exams.StudentGroup_teachers.user",
    "exams.TextExtractionJob.user",
    # hr_contracts — kadr qeydi
    "hr_contracts.EmploymentContract.created_by",
    "hr_contracts.EmploymentContract.employee",
    "hr_contracts.EmploymentContract.sent_by",
    # labs
    "labs.Lab.created_by",
    "labs.LabSubmission.graded_by",
    "live_exam.LiveSession.host_user",
    # monitoring
    "monitoring.Incident.acknowledged_by",
    "monitoring.Incident.assigned_to",
    "monitoring.Incident.resolved_by",
    "monitoring.SecurityEvent.resolved_by",
    # notifications
    "notifications.InAppNotification.recipient",
    "notifications.StudentOrganizationRequest.responded_by",
    # organizations
    "organizations.AcademicHoliday.created_by",
    "organizations.AcademicPeriod.locked_by",
    "organizations.Membership.assigned_by",
    "organizations.OrgUnit.head",
    "projects.ProjectSubmission.graded_by",
    # registrar — jurnal, dərslər, xanalar, cədvəl, bal vərəqləri
    "registrar.AssessmentScheme.chair_approved_by",
    "registrar.AssessmentScheme.dean_approved_by",
    "registrar.AssessmentScheme.submitted_by",
    "registrar.ComponentScore.entered_by",
    "registrar.CourseOffering.instructor",
    "registrar.CourseWork.entered_by",
    "registrar.CriterionScore.entered_by",
    "registrar.Curriculum.approved_by",
    "registrar.Curriculum.submitted_by",
    "registrar.Enrollment.added_by",
    "registrar.ExamScoreEntry.entered_by",
    "registrar.ExamScoreSheet.created_by",
    "registrar.ExamScoreSheet.examiner",
    "registrar.ExamScoreSheet.invigilator",
    "registrar.FinalGrade.entered_by",
    "registrar.GroupElectiveChoice.decided_by",
    "registrar.GuestRosterDocument.uploaded_by",
    "registrar.JournalCloseNotice.created_by",
    "registrar.JournalShare.created_by",
    "registrar.KollokviumExtraGrant.granted_by",
    "registrar.KollokviumWindow.created_by",
    "registrar.Lesson.created_by",
    "registrar.Lesson.instructor",
    "registrar.LessonMark.entered_by",
    "registrar.PassiveHour.created_by",
    "registrar.Program.archived_by",
    "registrar.ResitRecord.decided_by",
    "registrar.RetakeApplication.decided_by",
    "registrar.RetakeApplication.payment_verified_by",
    "registrar.RetakeApplication.result_recorded_by",
    "registrar.RetakeTuition.updated_by",
    "registrar.RetakeWindow.closed_by",
    "registrar.RetakeWindow.opened_by",
    "registrar.ScheduleSlot.created_by",
    "registrar.ScheduleSlot.instructor",
    "registrar.ScheduleSlot.parked_by",
    "registrar.SelfWorkMark.entered_by",
    "registrar.Subject.archived_by",
    # subject_folder — müəllimin fənn qovluğu və materialları
    "subject_folder.FolderAssignment.assigned_by",
    "subject_folder.FolderAssignment.unassigned_by",
    "subject_folder.FolderMaterial.created_by",
    "subject_folder.FolderTask.created_by",
    "subject_folder.SimilarityMatch.dismissed_by",
    "subject_folder.SubjectFolder.created_by",
    "subject_folder.SubjectFolder.owner",
    "subject_folder.Submission.reviewed_by",
    "subject_folder.SubmissionFile.uploaded_by",
    "subject_folder.TaskAttachment.uploaded_by",
    "subject_folder.TaskDeadline.set_by",
    # surveys — müəllim haqqında sorğu nəticələri, müəllimin öz iştirakı
    "surveys.Survey.created_by",
    "surveys.SurveyCampaign.created_by",
    "surveys.SurveyDraft.user",
    "surveys.SurveyGateSkip.user",
    "surveys.SurveyParticipation.user",
    "surveys.SurveyReceipt.teacher",
    "surveys.SurveyResponse.teacher",
    "surveys.SurveySubmission.respondent",
    # syllabus — müəlliflik, versiyalar, təsdiqlər
    "syllabus.Syllabus.author",
    "syllabus.SyllabusReview.actor",
    "syllabus.SyllabusSection.updated_by",
    "syllabus.SyllabusShare.created_by",
    "syllabus.SyllabusVersion.approved_by",
    "syllabus.SyllabusVersion.created_by",
    "syllabus.SyllabusVersion.reviewer",
    "syllabus.SyllabusVersion.submitted_by",
    # timetable
    "timetable.GroupTimePolicy.updated_by",
    "timetable.TeacherAvailability.teacher",
    "timetable.TeacherAvailability.updated_by",
    "timetable.TimetableDraftSlot.teacher",
    "timetable.TimetableRun.created_by",
    "timetable.TimetableRun.published_by",
    "trial_exams.TrialExamRequest.reply_sent_by",
    "trial_exams.TrialExamRequest.user",
    # workload — dərs yükü
    "workload.LoadObjection.resolved_by",
    "workload.LoadObjection.teacher",
    "workload.TaskFacultySlice.decided_by",
    "workload.TaskRowReview.coordinator",
    "workload.TeacherAssignment.assigned_by",
    "workload.TeacherAssignment.teacher",
    "workload.TeacherWorkloadProfile.teacher",
    "workload.TeachingTask.created_by",
    "workload.TeachingTask.distributed_by",
    "workload.TeachingTask.submitted_by",
)

_KEEP_PERSONAL = (
    "accounts.EmailOTP.user",
    "accounts.UserProfile.user",
    "admin.LogEntry.user",
    "ai_assistant.AIAssistantLog.user",
    "auth.User_groups.user",
    "auth.User_user_permissions.user",
    "monitoring.SecurityEvent.user",
    "notifications.PushDevice.user",
)

#: DB trigger-i UPDATE-i qadağan edən (append-only / dəyişməz) və ya tarixi «kim etdi» sübutu.
_KEEP_EVIDENCE = (
    "accounts.TeachingPayRate.archived_by",
    "accounts.TeachingPayRate.created_by",
    "applications.ApplicationContentRevision.actor",
    "applications.ApplicationEvent.actor",
    "applications.ApplicationEvent.hidden_by",
    "audit.AuditLog.user",
    "exams.ExamGradeEvent.grader",
    "exams.QuestionSubmissionEvent.actor",
    "hr_contracts.EmploymentContractEvent.actor",
    "legacy_import.LegacyEntityMapVersion.applied_by",
    "legacy_import.LegacyEntityMapVersion.reviewed_by",
    "legacy_import.LegacyImportBatch.recorded_by",
    "legacy_import.LegacyMigrationIssue.reviewed_by",
    "legacy_import.LegacyMigrationRun.initiated_by",
    "registrar.AbsenceCredit.actor",
    "registrar.ComponentScoreCorrection.corrected_by",
    "registrar.CorrectionReversal.reverted_by",
    "registrar.CourseWorkCorrection.corrected_by",
    "registrar.JournalCorrection.corrected_by",
    "registrar.JournalHygieneDecision.decided_by",
    "registrar.JournalHygieneDecision.reverted_by",
    "registrar.JournalRemoval.actor",
    "registrar.LanguageLevelCohort.created_by",
    "registrar.LanguageLevelPlacement.actor",
    "registrar.LegacyGradeReview.reviewed_by",
    "registrar.LessonCorrection.corrected_by",
    "registrar.LessonCorrection.new_instructor",
    "registrar.LessonCorrection.old_instructor",
    "registrar.RetakeApplicationEvent.actor",
    "registrar.SelfWorkCorrection.corrected_by",
    "registrar.StudentMovement.actor",
    "registrar.SubgroupPlacementEvent.actor",
    "registrar.TeachingHandover.from_instructor",
    "registrar.TeachingHandover.performed_by",
    "registrar.TeachingHandover.reverted_by",
    "registrar.TeachingHandover.to_instructor",
    "subject_folder.SubmissionEvent.actor",
    "registrar.ExamChanceGrant.granted_by",
    "registrar.ExternalCreditRecognition.created_by",
    "registrar.ExternalCreditRecognition.revoked_by",
    "registrar.RetakeApplication.refund_decided_by",
    "registrar.RetakeApplication.refunded_by",
    "registrar.RetakeReceipt.uploaded_by",
    "workload.WorkloadAmendment.made_by",
    "verification.DocumentSeal.issued_by",
    "verification.DocumentSeal.revoked_by",
    "verification.DocumentSeal.subject_user",
)

_KEEP_STUDENT = (
    "appeals.Appeal.student",
    "assignments.Assignment_assigned_students.user",
    "assignments.Submission.user",
    "exams.CodingSubmission.student",
    "exams.ExamAttempt.user",
    "exams.ExamStudentPin.student",
    "exams.Exam_allowed_users.user",
    "exams.Exam_excluded_users.user",
    "exams.FinalExamTicket.student",
    "exams.StudentExamAttemptGrant.student",
    "exams.StudentGroup_students.user",
    "exams.SupervisionIncident.student",
    "labs.LabAnswer.student",
    "labs.LabAssignment.student",
    "labs.Lab_allowed_students.user",
    "notifications.StudentOrganizationRequest.user",
    "projects.ProjectSubmission.student",
    "projects.Project_assigned_students.user",
    "registrar.Enrollment.student",
    "registrar.ExamChanceGrant.student",
    "registrar.ExternalCreditRecognition.student",
    "registrar.LanguageLevelPlacement.student",
    "registrar.LegacyExcuseDocument.student",
    "registrar.RetakeApplication.student",
    "registrar.StudentAcademicRecord.student",
    "registrar.SubgroupPlacementEvent.student",
    "subject_folder.Submission.student",
    "surveys.SurveyReceipt.student",
)

POLICY: dict = {
    **{key: REPOINT for key in _REPOINT},
    **{key: KEEP_PERSONAL for key in _KEEP_PERSONAL},
    **{key: KEEP_EVIDENCE for key in _KEEP_EVIDENCE},
    **{key: KEEP_STUDENT for key in _KEEP_STUDENT},
    "organizations.Membership.user": MEMBERSHIP,
    "registrar.JournalShare.teacher": SHARE,
    "organizations.Organization.owner": GUARD,
}

#: 2 saat DB qoruyucusu (``trg_journal_mark_guard``) olan cədvəllər — yazı ``journal_unlock`` ilə.
JOURNAL_LOCKED = frozenset({"registrar.LessonMark", "registrar.ComponentScore"})


class Relation:
    """İstifadəçiyə istinad edən bir sahə (model + sahə adı)."""

    __slots__ = ("field", "key", "model")

    def __init__(self, model, field):
        self.model, self.field = model, field
        self.key = f"{model._meta.label}.{field.name}"

    @property
    def attname(self) -> str:
        return self.field.attname

    @property
    def short(self) -> str:
        """Stdout açarı üçün: ``registrar_lesson_instructor`` (yalnız ``[a-z_]``)."""
        return f"{self.model._meta.app_label}_{self.model._meta.model_name}_{self.field.name}".lower()

    def unique_keys(self) -> list:
        """Sahəni ehtiva edən unikal məhdudiyyətlər: ``[(digər sahələr, şərt Q və ya None), …]``."""
        meta, found = self.model._meta, []
        for together in meta.unique_together:
            if self.field.name in together:
                found.append((tuple(name for name in together if name != self.field.name), None))
        for constraint in meta.constraints:
            if isinstance(constraint, UniqueConstraint) and self.field.name in (constraint.fields or ()):
                others = tuple(name for name in constraint.fields if name != self.field.name)
                found.append((others, constraint.condition))
        return found


def relations() -> list:
    """İstifadəçi modelinə yönələn bütün FK / O2O sahələri (gizli ``related_name='+'`` və M2M ara cədvəlləri də)."""
    found, seen = [], set()
    for rel in get_user_model()._meta.get_fields(include_hidden=True):
        if not rel.auto_created or rel.concrete or rel.many_to_many or rel.related_model is None:
            continue
        relation = Relation(rel.related_model, rel.field)
        if relation.key in seen:
            continue
        seen.add(relation.key)
        found.append(relation)
    return sorted(found, key=lambda item: item.key)


def unclassified() -> list:
    return [relation.key for relation in relations() if relation.key not in POLICY]


def stale() -> list:
    """POLICY-də olub artıq mövcud olmayan sahələr (testdə yoxlanılır)."""
    live = {relation.key for relation in relations()}
    return sorted(key for key in POLICY if key not in live)


__all__ = [
    "GUARD",
    "JOURNAL_LOCKED",
    "KEEP",
    "KEEP_EVIDENCE",
    "KEEP_PERSONAL",
    "KEEP_STUDENT",
    "MEMBERSHIP",
    "POLICY",
    "REPOINT",
    "SHARE",
    "Relation",
    "relations",
    "stale",
    "unclassified",
]
