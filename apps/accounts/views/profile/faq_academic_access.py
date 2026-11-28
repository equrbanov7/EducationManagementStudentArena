"""Audience of an academic tutorial follows the operation shown in its media."""

from apps.accounts.services import runtime_settings_admin
from apps.accounts.services.learning_action_access import (
    can_create_personal_course,
    can_create_personal_exam,
    can_send_personal_questions,
)
from apps.appeals.public import PERM_APPEAL_CREATE, PERM_APPEAL_DECIDE
from apps.exams.public import (
    can_create_question_bank,
    can_designate_exam_halls,
    can_enter_supervision_surface,
    can_manage_exam_rooms,
    can_view_attempt_results,
    chair_queue_filter,
    is_exam_center_user,
    is_teacher_user,
)
from apps.organizations.public import can_manage_groups, can_view_groups, group_manage_scope, group_scope
from apps.registrar.public import (
    exam_score_entry,
    is_authorized_instructor,
    journal_scope,
    retake_access,
    retake_window,
)
from core.permissions import request_has_permission

from ..journal_hygiene import resolve_actor as hygiene_actor
from ..legacy_review import resolve_actor as legacy_actor

# All keys reusing one recording inherit that recording's deepest operation,
# including aliases whose default playback starts in the middle of the clip.
MEDIA_FLAGS = {
    "paper": ("faq_enter_paper_scores",),
    "journal-entry": ("faq_write_own_journal",),
    "laborant-journal": ("faq_write_own_journal",),
    "laborant-components": ("faq_write_own_journal",),
    "grades": ("can_view_student_assignments",),
    "quiz": ("can_view_student_assignments",),
    "pin": ("can_view_student_assignments",),
    "appeal": ("can_view_student_assignments", "faq_lodge_appeal"),
    "request-transcript": ("can_view_student_assignments",),
    "student-syllabus": ("can_view_student_assignments",),
    "section-pending-answers": ("can_view_student_assignments",),
    "room-monitor": ("faq_supervise_rooms",),
    "section-legacy-grade-review": ("faq_correct_legacy_score",),
    "section-journal-hygiene": ("faq_apply_journal_hygiene",),
    "section-journal-close": ("faq_close_journals",),
    "section-remote-journal-access": ("faq_grant_remote_journal",),
    "section-my-exams": ("faq_create_quiz",),
    "section-question-bank": ("faq_create_question_bank",),
    "section-question-submissions": ("faq_submit_own_questions",),
    "section-question-chair-review": ("faq_review_chair_questions",),
    "section-exam-center-pins": ("faq_exam_center",),
    "section-exam-center-stats": ("faq_exam_center",),
    "section-manage-appeals": ("faq_decide_appeal",),
    "section-superadmin-exam-rooms": ("faq_manage_exam_rooms",),
    "section-retake-desk": ("faq_verify_retake_payment",),
    "section-retake-windows": ("faq_manage_retake_window",),
    "section-pending-review": ("can_review_submissions",),
    "section-review-results": ("faq_view_review_results",),
}

# Keep the specific subject of an entry protected even if a tenant replaces its video.
GUIDE_FLAGS = {
    "exam-import": ("faq_enter_paper_scores",),
    "published-paper-score": ("faq_enter_paper_scores",),
    "section-exam-score-entry": ("faq_enter_paper_scores",),
}


def academic_flags(guide):
    return tuple(dict.fromkeys((*GUIDE_FLAGS.get(guide.key, ()), *MEDIA_FLAGS.get(guide.video, ()))))


def academic_capabilities(request, capabilities, required=None):
    """A media range request evaluates only the gates of the requested guide."""
    user, org = request.user, getattr(request, "organization", None)
    if not getattr(user, "is_active", False) or not org or not org.is_active or org.status != "active":
        return {}
    sections = capabilities["allowed_sections"]
    write = not getattr(request, "is_view_as", False)
    checks = {
        "faq_exam_center": lambda: is_exam_center_user(user),
        "faq_view_review_results": lambda: can_view_attempt_results(user),
        # The personal (outgoing) form and the centre's inbox share a URL.
        "faq_submit_own_questions": lambda: can_send_personal_questions(request),
        "faq_create_question_bank": lambda: write and is_teacher_user(user) and can_create_question_bank(user),
        "faq_create_quiz": lambda: can_create_personal_exam(request),
        "faq_create_course": lambda: can_create_personal_course(request),
        "faq_manage_exam_rooms": lambda: write and can_manage_exam_rooms(user),
        "faq_designate_exam_halls": lambda: write and can_designate_exam_halls(user),
        "faq_manage_academic_groups": lambda: write
        and "groups-registry" in sections
        and can_view_groups(request)
        and can_manage_groups(request)
        and group_scope(request, org).has_structure_access
        and group_manage_scope(request, org).has_structure_access,
        "faq_lodge_appeal": lambda: write and request_has_permission(request, PERM_APPEAL_CREATE),
        "faq_decide_appeal": lambda: write
        and is_exam_center_user(user)
        and request_has_permission(request, PERM_APPEAL_DECIDE),
        "faq_write_own_journal": lambda: write
        and capabilities.get("is_teacher", False)
        and is_authorized_instructor(organization=org, instructor=user),
        "faq_enter_paper_scores": lambda: write
        and "exam-score-entry" in sections
        and exam_score_entry.can_enter_exam_scores(user, org),
        "faq_close_journals": lambda: write
        and "journal-close" in sections
        and journal_scope.can_close_journals(user, org),
        "faq_supervise_rooms": lambda: can_enter_supervision_surface(user, org),
        "faq_correct_legacy_score": lambda: write
        and "legacy-grade-review" in sections
        and legacy_actor(request).can_review,
        "faq_apply_journal_hygiene": lambda: write
        and "journal-hygiene" in sections
        and hygiene_actor(request).can_apply,
        "faq_grant_remote_journal": lambda: write
        and "remote-journal-access" in sections
        and runtime_settings_admin.can_manage(user, request),
        "faq_review_chair_questions": lambda: write
        and "question-chair-review" in sections
        and chair_queue_filter(user, org) is not None,
        "faq_verify_retake_payment": lambda: write
        and "retake-desk" in sections
        and retake_access.can_verify_payments(user, org),
        "faq_manage_retake_window": lambda: write
        and "retake-windows" in sections
        and retake_window.can_manage(user, org),
    }
    names = checks if required is None else checks.keys() & required
    return {name: checks[name]() for name in names}
