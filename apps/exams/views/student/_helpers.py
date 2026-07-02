from django.utils import timezone

# Faza 5 (audit 2026-07-02): URL/redirect köməkçiləri apps/exams/navigation-a
# köçürüldü (servis qatı ilə ortaq istifadə). Aşağıdakı re-exportlar mövcud
# `from ._helpers import ...` çağırışlarının import səthini qoruyur.
from apps.exams.navigation import (  # noqa: F401
    append_query_params,
    append_return_to,
    build_exam_history_url,
    build_exam_result_url,
    current_return_to,
    safe_same_origin_redirect_path,
)
from core.helpers import REVIEW_EDIT_LOCK_WINDOW
from core.tenancy import request_has_active_organization_context, restore_request_organization_from_profile


def ensure_student_exam_tenant_context(request):
    if request_has_active_organization_context(request):
        return True
    return restore_request_organization_from_profile(request, profile=getattr(request.user, "profile", None))


def are_exam_results_hidden_from_student(exam):
    return bool(getattr(exam, "results_hidden_from_students", False))


def annotate_attempt_result_visibility(attempts, *, current_time=None):
    now = current_time or timezone.now()
    prepared_attempts = []

    for attempt in attempts:
        result_hidden_by_teacher = are_exam_results_hidden_from_student(attempt.exam)
        can_view_result = not result_hidden_by_teacher and attempt.exam.exam_type in {"test", "coding"}
        review_available_in_seconds = 0

        if result_hidden_by_teacher:
            can_view_result = False
        elif attempt.exam.exam_type not in {"test", "coding"}:
            if attempt.checked_by_teacher:
                if attempt.teacher_checked_at:
                    reveal_at = attempt.teacher_checked_at + REVIEW_EDIT_LOCK_WINDOW
                    can_view_result = now >= reveal_at
                    if not can_view_result:
                        review_available_in_seconds = max(0, int((reveal_at - now).total_seconds()))
                else:
                    can_view_result = True
            else:
                can_view_result = True

        attempt.can_view_result = can_view_result
        attempt.review_available_in_seconds = review_available_in_seconds
        attempt.result_hidden_by_teacher = result_hidden_by_teacher
        prepared_attempts.append(attempt)

    return prepared_attempts
