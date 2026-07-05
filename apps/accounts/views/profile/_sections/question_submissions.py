"""Profil "question-submissions" bölməsi üçün context-fragment qurucusu.

Müəllim: öz göndərişləri + "Yeni göndəriş" düyməsi.
İmtahan mərkəzi: təşkilatın gözləyən göndəriş qutusu (inbox) + tarixçə.
"""

from django.urls import reverse


def _inactive_defaults() -> dict:
    return {
        "question_submissions_items": [],
        "question_submissions_is_reviewer": False,
        "question_submissions_total_count": 0,
        "question_submissions_pending_count": 0,
        "question_submissions_accepted_count": 0,
        "question_submissions_rejected_count": 0,
        "question_submissions_create_url": "",
        "question_submissions_inbox_url": "",
    }


def build_question_submissions_context(request, *, allowed_sections, active_section) -> dict:
    if not (active_section == "question-submissions" and "question-submissions" in allowed_sections):
        return _inactive_defaults()

    from django.db.models import Count, Q

    from apps.exams.models import QuestionSubmission
    from apps.exams.public import is_exam_center_user
    from core.tenancy import get_request_organization

    organization = get_request_organization(request)
    if organization is None:
        return _inactive_defaults()

    is_reviewer = is_exam_center_user(request.user)
    scoped = QuestionSubmission.objects.filter(organization=organization)
    if not is_reviewer:
        scoped = scoped.filter(teacher=request.user)

    items = list(scoped.select_related("teacher", "accepted_bank").order_by("-created_at")[:30])
    # Stat kartlar üçün saylar — TƏK aqreqat sorğu.
    counts = scoped.aggregate(
        total=Count("id"),
        pending=Count("id", filter=Q(status=QuestionSubmission.STATUS_PENDING)),
        accepted=Count("id", filter=Q(status=QuestionSubmission.STATUS_ACCEPTED)),
        rejected=Count("id", filter=Q(status=QuestionSubmission.STATUS_REJECTED)),
    )

    return {
        "question_submissions_items": items,
        "question_submissions_is_reviewer": is_reviewer,
        "question_submissions_total_count": counts["total"] or 0,
        "question_submissions_pending_count": counts["pending"] or 0,
        "question_submissions_accepted_count": counts["accepted"] or 0,
        # Müəllim üçün "düzəliş gözləyən", mərkəz üçün "rədd edilmiş" mənasında.
        "question_submissions_rejected_count": counts["rejected"] or 0,
        "question_submissions_create_url": reverse("exams:question_submission_create"),
        "question_submissions_inbox_url": reverse("exams:question_submission_inbox"),
    }
