"""Profil "question-submissions" bölməsi üçün context-fragment qurucusu.

Müəllim: öz göndərişləri + "Yeni göndəriş" düyməsi.
İmtahan mərkəzi: təşkilatın gözləyən göndəriş qutusu (inbox) + tarixçə.
"""

from django.urls import reverse


def _inactive_defaults() -> dict:
    return {
        "question_submissions_items": [],
        "question_submissions_is_reviewer": False,
        "question_submissions_pending_count": 0,
        "question_submissions_create_url": "",
        "question_submissions_inbox_url": "",
    }


def build_question_submissions_context(request, *, allowed_sections, active_section) -> dict:
    if not (active_section == "question-submissions" and "question-submissions" in allowed_sections):
        return _inactive_defaults()

    from apps.exams.models import QuestionSubmission
    from apps.exams.public import is_exam_center_user
    from core.tenancy import get_request_organization

    organization = get_request_organization(request)
    if organization is None:
        return _inactive_defaults()

    is_reviewer = is_exam_center_user(request.user)
    if is_reviewer:
        # Mərkəz: bütün təşkilat üzrə (gözləyənlər yuxarıda).
        items = list(
            QuestionSubmission.objects.filter(organization=organization)
            .select_related("teacher", "accepted_bank")
            .order_by("-created_at")[:30]
        )
        pending_count = QuestionSubmission.objects.filter(
            organization=organization, status=QuestionSubmission.STATUS_PENDING
        ).count()
    else:
        items = list(
            QuestionSubmission.objects.filter(organization=organization, teacher=request.user)
            .select_related("accepted_bank")
            .order_by("-created_at")[:30]
        )
        pending_count = sum(1 for item in items if item.status == QuestionSubmission.STATUS_PENDING)

    return {
        "question_submissions_items": items,
        "question_submissions_is_reviewer": is_reviewer,
        "question_submissions_pending_count": pending_count,
        "question_submissions_create_url": reverse("exams:question_submission_create"),
        "question_submissions_inbox_url": reverse("exams:question_submission_inbox"),
    }
